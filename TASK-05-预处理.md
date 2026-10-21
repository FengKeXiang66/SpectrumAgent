# TASK-05 光谱预处理（B 域）任务卡

> 里程碑 **#05 光谱预处理（配方 Pipeline + 效果对比）**。事实源：需求 v2.7（B 域 FR-B01~B11、场景 S1、第 8 章路线图）+ UI ui-v2.3（S06 预处理配方，必做）+ 技术选型定稿 v1.1。
> 本卡由备卡 Agent 起草并经 R2 审订轮（2026-10-21），**待科祥最后确认 §9 第 4 项后转 codex**。修订记录见 §12。

## 1. 范围裁定

**做（阶段一）**：

| 项 | 内容 | 依据 |
|---|---|---|
| B01 | 反射率转换，**三支**（见 §2.1） | FR-B01 P0；plastic 现状 |
| B02 | Savitzky-Golay 平滑（窗口/阶数可配，偶数窗口报错） | FR-B02 P0 |
| B03 | SG 一阶/二阶导数（可选差分窗口） | FR-B03 P0 |
| B04 | 散射校正：SNV / MSC / EMSC 三法可选，MSC 参考谱显式指定并记录 | FR-B04 P0 |
| B05 | 标准化/归一化：StandardScaler / MinMax / 面积归一 / 向量归一，**fit-on-apply**（见 §2.4） | FR-B05 P0 |
| B06 | 波段裁剪与重采样（线性/样条，FWHM 变化 >5% 提示，见 §2.6） | FR-B06 P0 |
| B07 | 配方 Pipeline：算子串联为命名配方，全局库、可复用，**只新建版本**（见 §2.3） | FR-B07 P0 |
| B08 | 降维：PCA / MNF / ICA，输出载荷/得分/累积方差解释率；确定性约定见 §2.6 | FR-B08 P0（B 域域表）；**UI 全文无 B08/PCA/MNF 任何字样（grep 实证）**——需求-UI 覆盖缺口，按域归属+P0 权威留在 #05；UI 缺项，S06 只做最小触发与指标展示 |
| B09 | 连续统去除，**二方法**：`convex_hull`（凸包+端点半自动）/ `linear`（端点连线，即 UI"去背景"的落点） | FR-B09 P1；**UI S06 必做交付表原文引 "FR-B01~B06 · B09 · B10"（UI 767 行）**——提前进阶段一；UI 579 行"去背景"三字无 FR 正文，**不单列算子**，降级为 B09 `method='linear'`（R2，防第二套口径） |
| **B10** | **预处理效果对比（提前）**：输入=**逐像素谱**（见 §2.5），指标口径钉死 | FR-B10 P1；§3.2 明写"配方选型靠 B10 评价"（需求 581 行）；场景 S1（418 行）依赖；UI S06 必做表（767 行） |

**不做（阶段二/三）**：B11 高级去噪（小波/BM3D，P2，可插拔算子位预留）；配方市场与跨组织共享、自动配方推荐（UI 581 行明示阶段二）；PLS/指标域算子（下一里程碑）；建模域任何内容；B08 完整载荷/得分分析 UI（UI 无定义，最小展示为止）。

**输入前提**：本里程碑的输入是 **#04 产出的带标签样本光谱集**（`sample_spectrum` + 快照）所对应的**逐像素谱**（label_map + cube 现算，见 §2.5——算子必须作用在逐像素谱上）。没有标注数据的场景降级：B10 仅展示信噪比等无监督指标并**明确标注局限**（FR-B10 原文）。工作流顺序"标注→预处理"为 v2.5 定版，不得回退。

## 2. 业务口径（全部钉死，codex 不得自行发挥）

### 2.1 B01 三分支

| 分支 | 公式 | 判据 |
|---|---|---|
| ① reference | `R = (I − D) / (W − D)` | hdr 有关联白板/暗电流文件 |
| ② scale | `R = DN / scale_factor` | hdr 有 `reflectance scale factor`（plastic 走此支） |
| ③ passthrough | `R = I` | data type 为 float 且值域 ⊆ [0,1] |

除零与负值处理策略可配置并记录（FR-B01 原文）。**产物必须记录本次用了哪支**；无任何判据命中 → 结构化错误，不得猜分支。
- **多判据命中 = 结构化错误（R6）**：reference/scale/passthrough 多判据同时命中 → `AMBIGUOUS_REFLECTANCE_INPUT`（message 列全部命中判据），不得按优先级猜——与"无判据命中不得猜"对称，优先级链无文档依据。**无判据命中 → `UNKNOWN_REFLECTANCE_INPUT`**（R6 补：原卡只说"结构化错误"未给码）。
- **白/暗参考关联（R6）**：ENVI 头无标准字段，实现层约定 hdr 自定义标签 `white reference = <path>` / `dark reference = <path>`（多文件=路径列表）；**文件解析在 11.2 run 层，算子只收已解析参考谱**（纯函数不变）。FR-B01"按行/列参考校正"属空间操作、与逐谱算子模型不合，**阶段一缓建**（§12 记账，需业务确认用法再排期）。
- **guard 枚举（R6）**：B01 params `guard ∈ {"clip"(默认),"keep","error"}`：clip=负值→0.0、零/非有限分母波段→NaN、非有限输入→NaN；keep=原样保留仅计数；error=任一负值或零分母 → `REFLECTANCE_GUARD_VIOLATION`。产物记录 branch+guard+negative_clipped+nan_bands。
  - **NaN 的下游处置（R6 补）**：clip 产生的 NaN **原样传播**给后续算子（不得静默插值/剔除，那会改变波长轴）；含 NaN 的谱在 B10 指标计算中**整条跳过并计数**（`nan_spectra_skipped`），报告中标注——不得用 0 填充参与统计。

### 2.2 算子与配方

- 算子 = 纯函数 `(张量/谱, params) -> 结果`，参数经 **JSON Schema** 校验（选型红线：算子同步建 Schema + 复现性测试）；注册表集中一处，新增算子 ≤ 0.5 人日（需求 340 行验收口径）。
- 配方 = 有序算子链 + 每算子参数 + **算子版本**（算子实现变了结果会变——R2 勘误：勿沿用 #04"特征口径版本"术语）。配方为**全局资产**（FR-B07"保存于库中，可一键复用于新数据集"），**项目选用记录是只读关联，不是副本**（禁同一配方在项目间各存一份，防第二真源）。
- **算子版本机制（R3 钉死，11.1 必做，不定义无法开工）**：算子注册项含 `{name, version:int, params_schema, impl}`；**算子实现变更必须递增 `version`**，不得静默改实现（否则旧配方结果不可复现）；配方 `pipeline` 每步记录 `{op, version, params}`；run 执行前校验配方声明的版本。
- **注册表多版本共存（R4 钉死，11.1 架构，与上条配套）**：注册表结构为 **`{name: {version: entry}}`**——同一算子名的多个 version 实现**必须同时驻留**，run 按配方声明的 `version` 取对应 `impl`。这是"旧 version 仍可复现旧结果"的**唯一实现方式**（单版本结构下 version 递增即覆盖旧实现，旧配方必然不可复现）。
  - **`OPERATOR_VERSION_STALE`（409）的精确触发条件**：仅当"配方声明的 version 在注册表中**不存在**"时抛出（即旧实现已被删除）；**version 存在时必须正常执行，不得误报**。删除旧实现属显式破坏性操作，须在报告中标注"该 version 已退役，旧配方不可复现"。
- **`pipeline` JSON 结构（R3 钉死，示例）**：
  ```json
  {"steps": [
    {"op": "reflectance",   "version": 1, "params": {"branch": "scale"}},
    {"op": "snv",           "version": 1, "params": {}},
    {"op": "sg_derivative", "version": 1, "params": {"order": 1, "window": 15, "polyorder": 2}}
  ]}
  ```
  字段名固定为 `steps` / `op` / `version` / `params`；`params` 由该算子的 `params_schema` 校验，未知键拒绝（对齐 `deny_unknown_fields` 纪律）。
- 内置默认配方一条：**`snv → sg_derivative(order=1, window=15, polyorder=2)`**，`code=plastic-snv-sg1`（S1 418 行逐字），标注"**场景示例默认值、可改**"。
  - **不含 `reflectance`（R8 裁定，两重理由）**：①算子名勘误——原卡写 `reflectance_scale`，**11.1 注册名是 `reflectance`**（`preprocess/__init__.py:9`），照字面建配方会 `OPERATOR_VERSION_STALE`；②**更硬的理由**——`ReflectanceParams.hdr` 是**必填字段**（schema:25，无默认值），而 hdr 是**数据集特定参数**；把 hdr 写进全局配方，同一配方就无法跨数据集复用（每换一个数据集就得改配方），直接违背 FR-B07"一键复用于新数据集"。plastic 数据 `reflectance scale factor=65535` 已是反射率，B01 在默认配方里本就是 no-op；需要反射率转换时**单独跑 B01**（run 层记 `b01_branch`）。
  - **若将来要"含反射率转换"的配方**：须先把 `hdr` 从算子 params 移出（改由 run 层 context 注入），属架构变更，走卡修订，**不得在 11.2 私自改 11.1 已过闸的 schema**。
  - **B01 与 run 的接缝（R8 记账，11.3 实现）**：反射率转换不进配方；**11.3 run 层负责从数据集读 hdr → 构造 B01 前置步（hdr 由 run 层注入、不经配方）→ 执行并记录 `b01_branch`**（该列的唯一供值路径，否则 `preprocess_run.b01_branch` 是孤儿列）。把 `hdr` 改为算子 params 之外（schema 可选化 + run 注入）属架构变更，须走卡修订。

### 2.2.1 B02/B03/B04 数值口径与算子返回结构（R6 钉死）

- **B02**：窗口/阶数可配，**偶数窗口报错**（FR-B02 原文），`polyorder ≤ window` 校验；scipy `savgol_filter`，`mode` 默认 `'interp'` 可配（实测 scipy 默认即 `interp`）。
- **B03**：一阶/二阶，`params={order, window, polyorder, mode}`；**导数按波段序号计算（scipy per-index 语义），不按波长单位归一**（SG 全局卷积，非均匀波长栅下无精确解）；产物记 `unit="band_index"`；同波长轴+标注导数阶（FR-B03 原文）；window 须奇数。
  - **"可选差分窗口"的落点（R6 补，防歧义）**：= `window_length`（拟合窗口），**不是** scipy 的 `delta`；`delta` 固定 `1.0`（波段序号步长），**不暴露**——暴露会引入"每 nm vs 每波段"第二套口径。
- **B04**：
  - **SNV** = `(x-mean)/std`，**std 用 population（ddof=0）**；零方差谱 `zero_std ∈ {"zeros"(默认),"nan","error"}`，zeros=输出全零并计数。
  - **MSC**：参考谱**显式指定**（FR-B04 原文）；**11.1 的算子只收 `reference: ndarray`（已解析参考谱）**，meta 记 `reference_sha256` + `reference_len`；**来源（训练集均值/指定样品）由 11.2 run 层记录并回填**——算子层无从得知来源，**不得在 meta 里编造 `reference_source`**（R6 补：科祥原稿的 meta 键把层次混了）。
  - **EMSC**：`x_i ≈ a·ref + b + Σ_{k=1..p} c_k·t^k`（`t` = 波段序号归一化到 `[0,1]` 防病态），`polynomial_order` 默认 2，参考谱规则同 MSC；每谱 `np.linalg.lstsq` 确定性拟合；校正 = `(x_i − 基线项)/a_i`；per-spectrum 系数随 meta 记录。
- **算子返回结构（R6）**：impl 主返回仍为谱矩阵；**允许返回 `(spectra, meta: dict)` 二元组**，registry 两种形态均接受，meta 合并进 run step 记录（**必须 JSON-safe**：np.float64→float、ndarray→list 或省略）。meta 键：B01={branch,matched_criteria,guard,negative_clipped,nan_bands}；B03={order,window,polyorder,mode,unit}；B04={method,reference_sha256,reference_len,std_ddof,zero_std_count,emsc_order?}。

### 2.3 配方版本化

- **只允许新建版本**（`version_no = max+1`）；历史版本不可改；**阶段一不做覆写路径**（无 409 分支，"不可静默变更"靠只增不改保证）。
- 改动配方 = 新版本；旧版本的 run 不受影响（run 引用 recipe_version_id，快照式）。

### 2.4 B05 标定参数（fit-on-apply）

- **每次套用按当前输入现算**标定参数；参数值+标定来源（数据集 id + 输入指纹 + 样本数）**随 run 落库**，不写进配方（配方只存算子声明）。
- 复现口径：**以本次 run 的输入数据指纹为准**——数据集重导入/源替换（含同路径换文件）→ 参数必须重算，并记录指纹对比结果；"同输入同结果"只对同指纹成立。
- **`input_fingerprint` 算法（R3 钉死）**：`sha256( dataset_id | 源文件相对路径排序后逐项 sha256 | annotation_version_id | 样本像素数 )`——**必须含标注版本 id**（重新标注后样本集变了，指纹必须变，否则"同指纹"会掩盖样本变化）；**源文件哈希由 run 预检时一次性流式计算（R12 修订）**——登记 payload 无源文件内容哈希（实证 `model.as_dict()` 只含元数据），原"复用 payload、不重新读盘"前提不成立，详见 §2.6 R12。
- FR-B05"随模型保存"留到建模里程碑：同算子届时改用"从模型取参数"，衔接点记入 §12。
- **B05 四法公式（R8 钉死）**：①**StandardScaler** = 逐波段 `(x-mean)/std`（**ddof=0**）；②**MinMax** = 逐波段 `(x-min)/(max-min)`；③**面积归一** = 逐谱除梯形积分，**积分变量为波段序号（`np.trapezoid(x, dx=1.0)`，非波长值）**——波长非等距时按波长积分会随数据集变化，口径不稳；④**向量归一** = 逐谱除 L2 范数。前两法 `fitted`=逐波段参数列表；后两法 `fitted` 为空、逐谱量不落库（`n_spectra` 进 meta）。
- **B05 零分母护栏（R8）**：四法统一 `zero_std ∈ {"zeros"(默认),"nan","error"}`（与 SNV 同族同默认）；`error` → **`NORMALIZATION_DEGENERATE`(400)** 带 `zero_scale_count`。**不回改 SNV 已发货的 `SCATTER_MODEL_DEGENERATE`**（不为一致性破坏 11.1 已过闸测试）。

### 2.5 B10 效果对比（输入粒度与指标口径）

- **输入 = 逐像素谱，不得用 `sample_spectrum` 聚合谱**（R2 裁定，本卡最致命缺口）：按当前 `label_map` 筛选、有界行块读原谱（复用 #04 `ReadableRows`/`row_blocks` 有界读模式），算子对**逐像素谱**施加后统计。
  - **逐像素谱的取值口径（R11 补）**：= **B01 前置后的反射率**，与 run 算子链的输入一致；**不是原始 DN**——否则 SNR 的分子分母被 scale factor 整体缩放、跨数据集不可比（Fisher 比虽尺度不变，但 SNR 与类间距离原值会失真）。理由：SNV/导数/标准化都是**逐谱非线性算子**，"先聚合再预处理" ≠ "先预处理再聚合"（SNV 对均值谱归一化与各像素 SNV 后取均值结果不同）——用聚合谱比的是假东西。成本承认：每个配方一次全图有界 pass，耗时进 11.7 性能记录，不设阈值。
- **信噪比**：`SNR = 谱幅度均值 / 相邻波段一阶差分的 RMS`，**逐像素谱各自算、报告取均值并同时披露中位数与 P10/P90**（R3 钉死计算粒度）；**禁止对"全图均值谱"算 SNR**——不同类谱相互抵消会让幅度均值趋零、SNR 失真。
- **类间距离**：**两两类均值谱欧氏距离的均值**（C(k,2) 对，**非**"到全局均值"），类均值谱 = 该 label 全部像素经同一配方处理后的均值谱。
- **类内方差**：pooled——各类内方差（逐像素对处理后类均值的偏差）按**类内像素数**加权平均，与类间距离同空间。
- **选优主排序 = Fisher 比（类间距离 / 类内方差）**；SNR 与三指标原值并列披露、不参排。
- **边界 1**：SNR 只适合同类算子间相对比较；**跨算子类型（平滑 vs 导数）不可比**（导数谱均值趋零、分子塌缩），报告须显式标注。
- **边界 2**：类内方差为 0 的类（单样本/谱完全一致）**排除出 Fisher 计算并标注"该类样本不足，未参与选优"**；禁止加 epsilon 粉饰。
- **边界 3**：类间距离原值**不可跨配方比**（StandardScaler 后量级全变）；**只有 Fisher 比尺度不变、可跨**——这正是选它做主排序的理由。
- 未标注数据：仅 SNR，显式标注局限（FR-B10 原文）。
- **"选优"是确定性计算，LLM 不得参与数值判断**（总红线）；LLM 至多转述报告结论。

### 2.6 确定性与降维约定（R2 新增）

- **所有降维算子固定 `random_state=0`**（ICA 随机初始化必须锁死）。
- **载荷符号约定：每个成分按"绝对值最大处取正"定向**——消除特征向量正负号翻转，保证两次跑逐元素相等（复现验收的前提）。
- **MNF 噪声协方差估计 = 相邻波段差分协方差**（最小假设），估计方法随产物记录；无噪声参考时不得静默退化。
- **B06 FWHM 变化提示**：以 `wavelengths` **相邻间隔作为 FWHM 的代理值**（R3 标注：实现层近似，非仪器真值），重采样后重算并对比，**变化 >5% 触发提示**；报告中须写明"FWHM 为间隔代理值，非实测分辨率"。**代理值取相邻间隔的中位数**（R8 钉死单一口径，防中位/均值混算重演）。
- **B06 轴来源契约（R8 钉死）**：算子签名不变（`(spectra, params)`），**波长轴一律经 `params` 显式传入**（`source` / `target` 有限向量）；`run()` 的 wavelengths **不注入算子**——配方必须自包含，否则同一配方配不同 wavelengths 出不同结果，复现性破产。
- **B06 裁剪/重采样（R8）**：裁剪 `params={source, range:[lo,hi]}` **闭区间**，0 波段命中 → `INVALID_OPERATOR_PARAMS`；重采样 `params={source, target, method: linear|spline}`（`linear=np.interp`，`spline=scipy.interpolate.CubicSpline`），source/target 均须**严格递增**；**target 越出源范围 → NaN（禁 clamp/外插）** + `out_of_range_bands` 计数；FWHM before=source、after=target，>5% → `fwhm_warning:true` + before/after。
- **变轴算子契约（R9 钉死）**：算子可改变 bands（**第二维**），**不可改变谱条数（第一维，label_map 对齐的地基）**。输出波长轴经 meta 保留键 **`axis`** 回传（全有限、严格递增、长度=输出 bands），框架校验通过即**替换工作轴**，最终 `PipelineResult.wavelengths` 随之更新（输入无轴而算子声明了轴时同样返回）；算子改变 bands 但**未声明 `axis`** → `INVALID_OPERATOR_RESULT`（无论输入有没有给 wavelengths——给过是留陈旧轴污染，没给是审计缺失，一律拒）。
  - **`axis` 不进审计记录（R9 补）**：校验通过后从 meta 中**移除** `axis`，records 只留摘要 `axis_len` + `axis_sha256`（否则每个 crop/resample step 都存一份 200 元素数组，多步配方 records 膨胀且不可读）；完整轴只在 `PipelineResult.wavelengths` 里。
- **B05/B06 算子命名（R9 钉死）**：`standardize`（method ∈ `standard`/`minmax`/`area`/`vector`，零分母统一 `zero_std`）；`crop`；`resample`。`CropParams.range` 为**两元素元组且 lo < hi**（类型与校验都钉死）。
- **B08/B09/B10 与 run 的实现口径（R11 钉死）**：
  - **ICA = `sklearn.decomposition.FastICA`**（`requirements-lock.txt:41` 已声明 scikit-learn 1.9.1，**非新增依赖**）；`random_state` **走 params**（schema 字段、默认 0、随配方记录），`registry.run()` 的 `random_state` 形参保持预留**不传**（impl 签名不动）；实测同输入两次 **max diff = 0.0**，1e-12 验收可达。
  - **降维算子无波长轴**：`pca`/`mnf`/`ica` 输出 bands=分量数，轴无意义——用 **`meta["axis"] = null` 显式声明"无轴"**（R9 落地：框架置工作轴 None；**省略 `axis` 仍拒**，不立新规则）。
  - **B01 前置输入 = 原始 DN（R11 最关键）**：run 层 `registry.readable(cube_id, raw=True)`（实测 raw=True = DN 未除 scale）+ **run 层自建有界读封装**（内部 `read_region` 分块、块用完即释），**禁止改 #04 的 `ReadableRows`（硬编码 `raw=False`，superpixels.py:88）/ session**；`b01_branch` 记**真实分支**（plastic 应为 `'scale'`，不得说谎记 passthrough）；**11.3 仅做 scale/passthrough 两支**，reference 支的白/暗文件解析后置，缺参考 → 结构化错误。
  - **MNF 噪声协方差** = 相邻波段差分协方差，**`np.linalg.pinv` 防奇异**（退化数据不裸抛 LinAlgError），估计方法随产物记录。
  - **B09 凸包口径**：上凸包在 **(band_index, reflectance) 空间**（与 area 按序号同口径，波长栅非均匀不引入差异）；**端点=首尾波段固定，中间顶点由上凸包自动识别**（不引入吸收峰检测）；`linear` = 首尾两点连线；输出**同形不变轴**，meta 记 `method` + hull 顶点数。
  - **`scaler_params` 供值**：run 执行时若配方含 `standardize`，取其 step meta 的 `fitted` 落 `run.scaler_params` JSON（**DDL 该列唯一供值路径**，防孤儿列）。
  - **artifacts 收敛**：11.3 只落两类——`sample_spectra`（每 label 处理后 mean/std，npz）与 `report`（metrics + 排序 + 不适用标注）；**不落 `processed_cube`/`overlay`**（禁全量物化）；`failed` 不登记半份；路径 `<preprocessed>/<cube_id>/<run_id>/`，`relative_path` POSIX 相对。
  - **compare 引擎**：收**显式 `recipe_version_id` 列表**（≥1，不自动选），**复用 run 单次执行**（不第二套执行路径）。
  - **SNR 收集**：逐像素 SNR 值允许常驻收集（~1.2 MB 派生标量；红线 4 禁的是原始立方体全量物化）；类均值/方差跨块 `sum`/`sumsq` 累加，**禁对全图均值谱算**。
  - **`run.error`** = `DataError.as_dict()` 的 JSON 摘要（code/detail/context）。
  - **同步执行**：11.3 无后台任务——pending→running→succeeded/failed 行内完成，11.4 只做查询/触发。
- **变轴参数的长度下限（R10 钉死）**：`ResampleParams.source` / `.target` 与 `CropParams.source` 一律 **`min_length=2`**——`CubicSpline` 至少需 2 点，1 波段轴会**裸抛 `ValueError`**（11.2 实测坐实），属未结构化错误；裁剪 1 波段无意义，一并收紧。违规在 **schema 层**就报 `INVALID_OPERATOR_PARAMS`，不得落到 scipy。
  - **实现方式**：新增 `AxisVector = Annotated[list[FiniteFloat], BeforeValidator(vector), Field(min_length=2)]` 供上述三个字段使用；**`FiniteVector` 保持 `min_length=1` 不动**（11.1 已过闸的 `reflectance.white_reference/dark_reference`、`msc/emsc.reference` 用它，不为一致性动旧模型）。
- **run 预检前置与源哈希来源（R12 钉死）**：
  - **源文件哈希由 run 预检时一次性流式计算**（分块读文件、流式 sha256、不整块载入）——登记 payload **不含源文件内容哈希**（实证 `model.py:138` `as_dict()` 只 dump 元数据、全仓无 hash 字段），§2.4 原"复用 payload"前提不成立；且登记期快照在源文件替换后反而漏变，run 时现算更硬（换文件必变）。**禁用 stat/路径/元数据冒充内容哈希**；已有数据集零回填。
  - **预检全部前置于落库**：验源（`readable`，SOURCE_CHANGED 短路）→ 源哈希 → `annotation_version` 存在 → `recipe_version` 存在且每步 `name@version` 可解析（`OPERATOR_VERSION_STALE` 409）→ B01 分支判定（hdr+dtype 定 scale/reference；float 值域首块确认、后续块分歧 → failed 不静默）。**全部 NOT NULL 供值齐才建 pending 行**；任何预检失败 = 结构化错误直抛调用方、**不建 run**（DDL 永不面对半份行）。
- **全局拟合与暂存例外（R12 钉死）**：逐块独立拟合会改变结果，禁止。分两类：
  - **可流式精确、不暂存**：StandardScaler = 跨块 `sum`/`sumsq` 充分统计量；PCA/MNF = **两遍块读**（pass1 累加均值 → pass2 累加中心化外积得协方差 → eigh/pinv），O(B²) 内存，**结果与分块边界无关**（验收锚点：换 block_size 结果逐元素相等）。
  - **必须全量数据**：ICA（FastICA 迭代）——**允许暂存**选中+B01 后像素矩阵至 `<preprocessed>/<cube_id>/<run_id>/.tmp/` 临时 memmap：随 run `finally` 必删、禁注册为 artifact、fit 后逐块流式读出（禁双副本）、**暂存字节数与峰值 RSS 进 report**。红线 4 禁的是**原始立方体**全量物化；派生选中集暂存为记账例外、仅 ICA 路径触发。
- **MNF 数学口径（R12 钉死，维度对齐公式；实现层口径，卡 R2 只写了"相邻波段差分协方差"）**：设输入 X 为 (n, B)：
  - 差分矩阵 Δ = `X[:, 1:] − X[:, :-1]`（n × B−1），Σ_Δ = `ΔᵀΔ/(n−1)`（**ddof=1**）；
  - 重构 B×B 噪声协方差 Σ_N：对角 σ_i²（内部波段 i=1..B−2 取 `(Σ_Δ[i-1,i-1] + Σ_Δ[i,i])/2`，边界波段取唯一侧差分方差/2）；次对角 `(Σ_N)[i, i+1] = (σ_i² + σ_{i+1}² − Σ_Δ[i, i])/2`（i=0..B−2）；其余元素为 0；
  - 白化 `W = Σ_N^(−1/2)`（eigh 分解、特征值 **pinv 防奇异**）；信号协方差 Σ_S = `(X−μ)ᵀ(X−μ)/(n−1)`（两遍流式计算）；
  - `C = W·Σ_S·W`；对 C 做 eigh 降序：**MNF 特征值即解释方差**（解释占比 = 特征值/特征值总和）；载荷 = `W·V`（符号按"绝对值最大处取正"定向）；得分 = `(X−μ)·W·V`（n × k）。
- **数值边界（R12 钉死）**：①`n_components` **必填、无默认**（无出处即禁默认），schema ≥1，运行时 ≤ bands（PCA/MNF/ICA 同）；②**含 NaN 谱不参与拟合**（显式检出、计 `nan_spectra`），变换时这些行输出**全 NaN**（与 resample spline/MSC 同族）；③连续统分母为 0（hull/linear 在某波段值为 0）→ 该波段输出 **NaN** + `zero_continuum_bands` 计数（禁 inf/clamp）；④SNR 差分 RMS=0（恒等谱）→ 该像素 SNR 记 **NaN** + `snr_nan_count`（inf 无合法 JSON 表示且恒谱不携带类信息），聚合统计跳过 NaN。

## 3. 数据模型（DDL 草稿，待 codex 实现时复核）

```sql
CREATE TABLE IF NOT EXISTS preprocess_recipe (
  id           TEXT PRIMARY KEY,
  code         TEXT NOT NULL,                -- 唯一标识，如 plastic-snv-sg1
  name         TEXT NOT NULL,
  description  TEXT,
  builtin      INTEGER NOT NULL DEFAULT 0,   -- 1=内置默认配方
  created_at   TEXT NOT NULL,
  UNIQUE (code)
);
CREATE TABLE IF NOT EXISTS preprocess_recipe_version (
  id           TEXT PRIMARY KEY,
  recipe_id    TEXT NOT NULL REFERENCES preprocess_recipe(id),
  version_no   INTEGER NOT NULL,
  pipeline     TEXT NOT NULL,                -- JSON：有序算子链+参数+算子版本
  note         TEXT,                         -- 变更说明（用户备注，非事件JSON）
  created_at   TEXT NOT NULL,
  UNIQUE (recipe_id, version_no)
);
-- 项目选用：只读关联，不是副本
CREATE TABLE IF NOT EXISTS project_recipe (
  project_id   TEXT NOT NULL REFERENCES project(id),   -- R2 补 FK，对齐 #04
  recipe_id    TEXT NOT NULL REFERENCES preprocess_recipe(id),
  selected_at  TEXT NOT NULL,
  PRIMARY KEY (project_id, recipe_id)
);
-- 一次"配方×数据集"套用 = 一个 run（含状态机，R2 补）
CREATE TABLE IF NOT EXISTS preprocess_run (
  id           TEXT PRIMARY KEY,
  cube_id      TEXT NOT NULL,                -- 输入数据集（dataset_registry.id）
  annotation_version_id TEXT NOT NULL REFERENCES annotation_version(id),  -- R7：B10 输入逐像素谱依赖的标注版本（跨里程碑 FK，#04 迁移先跑）
  recipe_version_id TEXT NOT NULL REFERENCES preprocess_recipe_version(id),
  b01_branch   TEXT NOT NULL CHECK (b01_branch IN ('reference','scale','passthrough')),
  input_fingerprint TEXT NOT NULL,           -- sha256(dataset_id|源文件哈希|annotation_version_id|样本像素数)，见 §2.4 R3（R7 修正：原注释写成 JSON 且漏标注版本）
  scaler_params TEXT,                        -- JSON：fit-on-apply 标定结果（B05）
  metrics      TEXT,                         -- JSON：B10 指标快照
  status       TEXT NOT NULL CHECK (status IN ('pending','running','succeeded','failed')),
  error        TEXT,                         -- status='failed' 时的结构化错误摘要
  finished_at  TEXT,
  note         TEXT,
  created_at   TEXT NOT NULL
);
-- 产物登记（大数组不进 DB，路径相对 preprocessed 根）
CREATE TABLE IF NOT EXISTS preprocess_artifact (
  id           TEXT PRIMARY KEY,
  run_id       TEXT NOT NULL REFERENCES preprocess_run(id),
  kind         TEXT NOT NULL CHECK (kind IN ('processed_cube','sample_spectra','overlay','report')),
  relative_path TEXT NOT NULL,               -- POSIX 相对路径（对齐 #04 snapshot_ref 纪律）
  sha256       TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  UNIQUE (run_id, kind, relative_path)       -- R2 补
);
```

产物物理路径：`AppPaths.preprocessed/<cube_id>/<run_id>/`（paths.py 新增 property，与 snapshots 平级；NAS 输出根属部署层，不在本里程碑）。

## 4. 开发任务（子阶段，一次只开一个）

- **11.1 算子框架 + B01/B02/B03/B04**：算子注册接口+JSON Schema+复现性测试骨架；反射率三分支；SG 平滑/导数；SNV/MSC/EMSC。产物=engine 层+单测。
- **11.2 B05/B06/B07**：标准化家族（fit-on-apply+指纹+FWHM >5% 规则）；裁剪/重采样；配方库+版本化（只增不改）+项目选用+内置默认。产物=recipe 存储+单测。
- **11.3 B08/B09/B10**：降维三法（random_state=0+载荷符号约定+MNF 差分协方差）；连续统去除二方法；**对比引擎**（逐像素输入+指标口径+三边界+未标注降级）。产物=compare+单测。
- **11.4 FastAPI 路由**：配方 CRUD（版本只增）/项目选用（含取消）/run 提交与进度（**状态机四态**）/指标报告/产物下载/**run 列表（R13 恢复路径：run_id 服务端生成，IPC 超时后前端凭 cube 维度列表找回真实状态）**。错误信封沿用 #02；禁 LLM 产数值。
- **11.5 Rust IPC**：`preprocess_forward`（**第七条命令，2026-10-21 科祥已批准**）；连锁成本：`audit_boundary.py` 六→七、build.rs commands、capabilities permissions 三处同步改；**超时 ≥300s（R13，禁照抄现有 30s）**。
- **11.6 前端 S06**：算子链编排+参数面板+处理后对比视图（含 B08 最小展示）+配方命名保存与复用（UI S06 必做表逐条对位）；预计剩余类本地估算不进验收。**R15 已把本条展开为可验收条目（§5.1 共 13 条）**；**D1 已于 2026-10-21 由科祥裁定走方案 A（run.py 补 `curves`），可开工**。
- **11.7 集成+验收+性能实测**：e2e（真实 sidecar 全链路：选样本→套配方→对比→存配方→复用）+验收映射+性能记录（含逐像素对比成本）+本机冒烟归科祥。

## 5. 验收标准（Checklist 草案）

- [ ] B01 三分支各跑通一次；分支判据命中与产物记录；无判据→结构化错误；除零负值策略可配置
- [ ] B02 偶数窗口明确报错；窗口/阶数可复现
- [ ] B03 一/二阶导数波长轴不变、阶数标注
- [ ] B04 SNV/MSC/EMSC 各一次；MSC 参考谱来源（训练集均值/指定样品）显式记录
- [ ] B05 四法各一次；标定参数随 run 落库、指纹变化触发重算并记录
- [ ] B06 裁剪/重采样后 FWHM 变化 >5% 提示（间隔估算法）
- [ ] B07 配方新建版本（version_no+1）、历史不可改、无覆写路径；项目选用为只读关联；内置默认配方与 S1 逐字一致（**R8 限定：S1 的"白板校正/反射率转换"步由 run 层 B01 前置施加并记 `b01_branch`，不入配方——hdr 为数据集特定参数，进配方破坏 FR-B07 跨数据集复用；内置链的 SNV+SG1 部分与 S1 逐字一致**）
- [ ] B08 PCA/MNF/ICA 输出载荷/得分/累积方差；**random_state=0 与载荷符号约定下，同输入两次跑逐元素相等**
- [ ] B09 两方法各一次；凸包端点识别；linear 支即 UI"去背景"落点
- [ ] B10：**输入为逐像素谱（测试断言禁用 sample_spectrum 读取路径）**；三指标+Fisher 主排序；三类边界标注全出现；未标注降级仅 SNR+局限标注；**报告无任何 LLM 生成数值**
- [ ] 复现：同输入指纹两次套用，处理后谱逐元素相等（容差 1e-12，含载荷符号）；换指纹重算
- [ ] run 状态机：pending→running→succeeded/failed 迁移与 failed 的 error 记录
- [ ] 性能：单样本集全链+逐配方对比耗时记录（不预设阈值）；产物字节数与峰值 RSS 回报
- [ ] run→recipe_version→recipe 与 #04 样本谱血缘可串联（cube→annotation_version→sample_spectrum→preprocess_run）
- [ ] **算子框架全链（R5，11.1 核心链路）**：注册（含 `params_schema`）→ `pipeline` 解析 → 逐算子执行 → 参数校验失败结构化报错（`INVALID_OPERATOR_PARAMS` + 字段级 message），闭环可跑
- [ ] **算子级确定性（R5）**：同一算子同输入两次执行逐元素相等（容差 1e-12）；随机算子（11.3 ICA）不在本条范围，另验
- [ ] **算子版本（R4）**：同一 `name` 的 v1/v2 同时驻留；声明 v1 的配方走 v1 实现、v2 走 v2，结果各自可复现；**删除 v1 后**声明 v1 的配方 → `OPERATOR_VERSION_STALE`(409)，声明 v2 仍正常——证明 STALE 只在"版本不存在"时触发，不误报
- [ ] 新增算子演示：实现一个注册算子 ≤ 0.5 人日口径的自证测试（接口可插拔）
- [ ] **B01 补充（R6）**：多判据命中 → `AMBIGUOUS_REFLECTANCE_INPUT`；无判据 → `UNKNOWN_REFLECTANCE_INPUT`；guard 三枚举各验 + 默认 clip 行为 + 计数；clip 产生的 NaN **原样传播**且 B10 统计整条跳过并计数
- [ ] **B02 补充（R6）**：偶数窗口报错 + `polyorder ≤ window` 校验 + `mode` 可配（默认 interp）
- [ ] **B03 补充（R6）**：`unit="band_index"` 记录；奇数窗口校验；`delta` 固定 1.0 且不暴露
- [ ] **B04 补充（R6）**：SNV ddof=0 + 零方差三策略；EMSC 默认阶数 2 + 显式参考谱 + lstsq 确定性；MSC meta 只记 reference 指纹、来源留 11.2
- [ ] **算子返回结构（R6）**：纯矩阵与 `(spectra, meta)` 两形态均被 registry 接受；B01/B03/B04 meta 键齐全且 JSON-safe
- [ ] **B05 补充（R8）**：四法公式逐一对拍（含面积归一 `np.trapezoid(dx=1.0)`）+ 零分母三策略 + `NORMALIZATION_DEGENERATE`(400)
- [ ] **B06 补充（R8）**：轴经 `params` 显式传入（不注入 wavelengths）；闭区间裁剪 0 命中报错；样条/越界 NaN+计数；FWHM 中位代理 + >5% 提示
- [ ] **B07 补充（R8）**：内置配方 = `snv → sg_derivative(1,15,2)`、`code=plastic-snv-sg1`、**不含 reflectance**（hdr 数据集特定，进配方破坏复用）；算子名必须是注册表名；迁移双跑幂等（schema 不变、内置不重复）
- [ ] **变轴契约（R9）**：crop→resample 全链后 `PipelineResult.wavelengths` = 最后轴、step meta 含 `axis`；改谱条数的算子被拒；改 bands 未声明 axis 被拒；axis 非递增/长度不符/含非有限被拒；**records 内不含完整 axis（只有 axis_len/axis_sha256）**；11.1 既有 94 测试不回改、全绿
- [ ] **变轴参数下限（R10）**：`resample` 的 source/target 与 `crop` 的 source 长度 1 → `INVALID_OPERATOR_PARAMS`（schema 层拒绝，不落到 scipy 裸 ValueError）；`FiniteVector` 原语义（min_length=1）不受影响
- [ ] **run 与 B08/B09/B10 补充（R11）**：**B01 前置真读 raw**——`b01_branch='scale'` 且产物是反射率（不是 DN/scale² 双重归一）；`scaler_params` 落值；artifacts 只两类且 failed 无半份；B08 三法 `meta["axis"]=null`（省略仍拒）；MNF `pinv` 防奇异；B09 凸包端点固定+顶点自动；compare 收显式列表且复用 run；SNR 逐像素收集；`run.error` 为 DataError JSON
- [ ] **run 预检与拟合口径（R12）**：预检失败不建 run（坏源/缺标注版本/STALE/坏 B01 分支各一次）；源哈希为内容 sha256（换文件必变）；**换 block_size 拟合结果逐元素相等**（StandardScaler/PCA/MNF 流式路径；ICA 暂存路径同一口径）；MNF 按 R12 公式对拍（独立手算 Σ_Δ→Σ_N→C→特征值）；`n_components` 缺省即拒、越界拒；NaN 谱排除+变换全 NaN；零分母/零 RMS → NaN+计数

### 5.1 11.6 前端 S06（R15 展开，逐条可验）

- [ ] **算子链可编排且只发合法配方**：链上每一步产出 `{op,version,params}`；**`reflectance` 不出现在可选算子列表**（run 预检 `run.py:152` 硬拒，选它必失败）；步序可上下移动、可删除、可重复（同算子多步合法）；空链拒绝提交
- [ ] **参数面板按 13 个注册算子中开放的 11 个建模**：`sg_smooth`/`sg_derivative`（window 奇数、polyorder<window、derivative order 1|2）、`snv`（zero_std）、`standardize`（method 四值+zero_std）、`crop`（lo<hi，source 自动）、`resample`（linear|spline，target 由起/止/点数生成）、`pca`/`mnf`/`ica`（n_components 必填、≤bands）、`continuum`（convex_hull|linear）；**`msc`/`emsc` 不开放（D2：reference 无来源）**；前端校验必须与后端 schema 同向（奇数窗、polyorder<window、lo<hi、n_components≥1），非法值不发请求
- [ ] **变轴链的轴维护**：前端纯函数维护"当前轴"（初始=`dataset.wavelengths`），crop 后按闭区间筛选、resample 后=target；后续算子的 `source` 一律取当前轴；**`dataset.wavelengths` 为空时 `crop`/`resample` 禁用并说明原因**（实测样例 report `wavelengths` 长度可为 0）
- [ ] **处理前后对比图（D1 落地后）**：读 `report.curves`，同一画布上下两栏（上=配方前 B01 反射率、下=配方后），按类别着色、图例用 `label_index→label_id→labels()` 映射出的 code；NaN 段断线不插值；x 轴优先波长、无轴退化为 band index 并明示；**前端不做任何谱数值计算**（只画后端给的数组）
- [ ] **指标展示只用后端字段**：SNR 四统计量（mean/median/p10/p90）+ `snr_nan_count`/`nan_spectra_skipped`、类间距离、类内方差、Fisher、`excluded_classes`、`boundaries` 原文、`limitations` 原文；**不得前端自算或改写边界文案**；未标注降级时只显示 SNR + 局限说明
- [ ] **B08 最小展示**：`pca`/`mnf`/`ica` 的 `explained_variance_ratio`+`cumulative_explained_variance` 以列表/条形呈现；**ICA 必须原样带出 `variance_definition`（非 PCA 方差分解）**，不得把 ICA 能量占比标成"解释方差"
- [ ] **配方命名保存与复用**：新建配方（code/name/description/note）→ 201；改参数后"保存为新版本"走 `add_version`（version_no 只增）；**无任何覆写入口**；配方库列表按 code 排序；code 重复报 `INVALID_REQUEST` 并给出可读提示
- [ ] **项目选用**：`select_recipe`/`deselect_recipe`/`list_project_recipes` 三路可用；project_id 取 `projects()[0]`（阶段一单项目，D8），界面显示项目名；取消选用只删关联、不删配方
- [ ] **run 提交与状态**：提交体 `{annotation_version_id, recipe_version_id}`（`block_size`/`guard` 不暴露，D5）；`annotation_version_id` 来自 `annotations.versions(cube)` 的版本下拉；成功后展示四态真实状态与 metrics；**失败展示 `error.error`/`error.detail` 而非"运行失败"**
- [ ] **超时恢复（R13 前端侧）**：提交遇 `TRANSPORT`/超时/网络异常时**不得直接报失败**，必须自动 `list_runs(dataset)` 拉最近 run，若出现同配方版本的新 succeeded 行则提示"任务可能已完成"并展示；同时保留手动刷新入口
- [ ] **配方对比**：多选配方版本 → `compare` → 按 `ranking`（Fisher 降序）展示表，附 `boundaries` 与 `selection` 原文；Fisher 为 null 的 run 不进排名并注明原因
- [ ] **前端出口唯一**：所有预处理请求经 `preprocess_forward` 单命令（`invoke` 仅出现在 api 层一处），无 URL/port/token 参数；组件内不出现 `fetch`/`http://`
- [ ] **测试与构建基线（实测，2026-10-21）**：`node 22.22.2 --test src/components/preprocess/*.test.ts src/components/datasets/*.test.ts src/components/annotation/*.test.ts` 全绿（**既有 31 passed 不回改**）；`tsc --noEmit` exit 0；新增纯逻辑测试覆盖请求投影 12 destination、参数校验同向、轴模拟、错误映射、超时恢复分支

## 6. 红线

1. LLM 只编排不产数值——B10 选优是确定性计算；对话只转述。
2. 算子同步建 JSON Schema + 复现性测试（选型定稿红线原样）。
3. 产物写独立输出区（本里程碑=data root/preprocessed），禁写源目录。
4. 配方历史不可静默变更（只增不改）；run 快照式引用。
5. "选优/指标"数值必须有口径定义与出处标注；无文档公式的一律标"实现层口径"。
6. 标注前置于预处理不得回退（v2.5 顺序）；无标注场景的降级路径须显式。

## 7. 排期（1 人全职，codex 执行，按实测调整）

| 阶段 | 内容 | 估算 |
|---|---|---|
| 11.1 | 算子框架 + B01–B04 | 2 天 |
| 11.2 | B05–B07 | 2 天 |
| 11.3 | B08–B10 | 2.5 天 |
| 11.4 | 路由 | 1 天 |
| 11.5 | Rust IPC（待批准） | 0.5 天 |
| 11.6 | S06 前端 | 2.5 天 |
| 11.7 | 集成+验收+性能 | 1.5 天 |
| **合计** | | **约 12 工作日** |

## 8. 风险

1. **B10 逐像素输入的成本**：每配方一次全图有界 pass；多配方对比=线性叠加。已计入 11.7 性能记录；不设阈值，但若实测过慢（>30s/配方）须回来重议采样策略——**不得静默改用聚合谱**。
2. **指标口径无文档公式**：§2.5/§2.6 全部为实现层裁定，验收锚点=三条边界标注齐全+可复现，不锚定具体数值。
3. **B08 UI 缺口**：UI 全文无 B08；S06 只做最小展示，若实机觉得不够属需求变更不是缺陷。
4. **B09/B10 提前的排期后果**：+2.5 天已含；评审重点核 UI 767 行证据。
5. B05 指纹机制与 #04 SOURCE_CHANGED 分层：源替换走 readable 校验链，指纹只判"标定输入是否变化"，两层不失真。

## 9. 待科祥确认项（本稿门口）

1. ~~B09 提前~~ → 已定（UI 767 硬证据）。
2. ~~baseline_remove 单列~~ → 已定：降级为 B09 `method='linear'`，不单列算子。
3. ~~B08 归属~~ → 已定：留在 #05（B 域 P0+域归属权威；UI 全文 grep 无 B08，需求-UI 覆盖缺口，最小 UI）。
4. ~~`preprocess_forward` 第七条命令~~ → **已批准（2026-10-21 科祥）**：S06 前端无 IPC 通道即残废，B 域独立域，第七条比塞变体干净；连锁成本三项（audit_boundary/build.rs/capabilities）由 11.5 同步落实。

## 12. 修订记录

| # | 内容 | 来源 |
|---|---|---|
| R1 | 初稿：范围（B09/B10 提前）、B01 三分支、配方全局库+只读关联+只增不改、fit-on-apply+指纹、B10 指标口径+三边界、DDL、子阶段 11.1–11.7、验收、红线、排期 | 备卡 Agent 起草 |
| R2 | 科祥审订轮：①**B10 输入钉死逐像素谱**（禁 sample_spectrum；逐谱非线性算子，聚合谱=假对比）；②run 加状态机四态+error/finished_at；③降维确定性（random_state=0+载荷 max-abs 定向+MNF 相邻波段差分协方差记录）；④B08 留在 #05（UI 全文 grep 无 B08，需求-UI 覆盖缺口，以域归属+P0 为准，最小 UI）；⑤"去背景"降级为 B09 method='linear' 不单列；次要：project_recipe 补 FK、artifact 补 UNIQUE、"特征口径版本"更正为"算子版本"、B06 FWHM >5% 钉死 | 科祥审订 + agent 取证（UI grep） |
| R3 | Agent 终读补 5 处（R2 之后新发现，2 条阻塞 11.1）：①**算子版本机制**（注册项含 version；实现变更须递增；配方每步记 `{op,version,params}`；run 前校验不一致 → `OPERATOR_VERSION_STALE` 409，不得静默用新实现重算）；②**`pipeline` JSON 结构钉死**（`steps`/`op`/`version`/`params`，未知键拒绝）；③**SNR 计算粒度**（逐像素各自算、报告均值+中位数+P10/P90；禁对全图均值谱算，防类间抵消致分子塌缩）；④**`input_fingerprint` 算法**（sha256 含 dataset_id+源文件哈希+**annotation_version_id**+样本像素数；重新标注必须变指纹）；⑤**FWHM 代理值标注**（相邻间隔是近似非真值，报告须写明） | Agent 终读（R2 落卡后自查） |
| R4 | **注册表多版本共存（11.1 架构，科祥 11.1 草稿的"旧 version 复现旧结果"验收暴露的缺口）**：R3 的注册项 `{name, version, params_schema, impl}` 是**单版本结构**——version 递增即覆盖旧 impl，旧配方必然不可复现，与"版本递增后旧 version 仍可复现旧结果"直接矛盾。改为 **`{name: {version: entry}}` 多版本共存**，run 按配方声明的 version 取 impl；`OPERATOR_VERSION_STALE` 精确触发条件改为"**声明版本在注册表中不存在**"（旧实现被删），version 存在时必须正常执行、不得误报。§5 加一条验收（v1/v2 共存 + 删 v1 后 STALE + v2 仍正常）。**勘误：科祥称"卡 §5 有这条验收"不实**——grep 仅命中第 58 行配方版本，算子版本验收为本轮新增 | Agent 核查 11.1 草稿（grep 实证 + 架构推演） |
| R5 | **补 11.1 两条验收（卡 §5 原本缺失）**：①**算子框架全链**（注册→pipeline 解析→逐算子执行→参数校验失败结构化报错）；②**算子级确定性**（同算子同输入两次执行逐元素相等 1e-12，随机算子 11.3 另验）。成因：11.1 开工令第 8 条自称"全部出自卡 §5"，但这两条 grep 实证不在卡内（§5 只有"新增算子演示"，第 155 行"复现"是 run 级指纹复现、11.1 尚无 run）——**同一类错误第二次**（验收凭印象加），按纪律补进卡而非从开工令删 | Agent 核 11.1 终版开工令（grep 实证） |
| R6 | **codex 11.1 六触即停：B01/B03/B04 数值口径与结果结构未定义**：多判据命中→`AMBIGUOUS_REFLECTANCE_INPUT`（对称 fail-closed）；参考=hdr 自定义标签+run 层解析+按行/列校正缓建；guard 三枚举默认 clip；B03 按波段序号；SG `mode=interp`+奇数窗口；SNV `ddof=0`+零方差三策略；EMSC=`[ref,1,t^1..t^p]`（t∈[0,1]）+lstsq+显式参考谱；impl 允许 `(spectra,meta)` 承载分支/阶数/参考谱记录。出处 FR-B01/B03/B04 原文+实现层口径标注。**agent 复核补 4 处**：①无判据命中补错误码 **`UNKNOWN_REFLECTANCE_INPUT`**（原稿只说"结构化错误"未给码）；②**"差分窗口"澄清为 `window_length` 非 scipy `delta`**，delta 固定 1.0 不暴露（防"每 nm vs 每波段"第二套口径）；③**clip 产生 NaN 的下游处置**（原样传播、B10 整条跳过并计数、禁 0 填充）；④**MSC meta 的 `reference_source` 层次错误**——11.1 算子只收 reference 数组、无从得知来源，改为记 `reference_sha256`+`reference_len`，来源由 11.2 run 层回填 | 11.1 数值缺口 + agent 复核（scipy 签名探针/测试签名核实） |
| R7 | **11.2 开工前 DDL 补两处（agent 核卡发现）**：①`preprocess_run` **缺 `annotation_version_id`**——B10 输入是逐像素谱（依赖 label_map + annotation_version），而 `input_fingerprint` 是 sha256 **无法反查**"这个 run 用的哪版标注"；加 `annotation_version_id TEXT NOT NULL REFERENCES annotation_version(id)`（**跨里程碑 FK**，依赖 #04 迁移先跑；#04 的 annotation_version 只增不改，FK 安全）。②`input_fingerprint` 注释"JSON：数据集id+源清单hash+样本数"与 R3 钉死的算法**双重不一致**（类型写成 JSON 实为 sha256 串、且漏 annotation_version_id），按 R3 修正 | agent 核 11.2 范围（DDL 对读 §2.4） |
| R8 | **11.2 开工前五处口径（科祥取证 + agent 复核改一处）**：①**卡 59 行算子名勘误**——原写 `reflectance_scale`，11.1 注册名是 **`reflectance`**（`preprocess/__init__.py:9`），照字面建配方会 `OPERATOR_VERSION_STALE`；②**内置配方最终不含 reflectance**（agent 改科祥原稿的"`params={}`"）——实测 `ReflectanceParams.hdr` **必填无默认**（schema:25）、算子内部 `params["hdr"]` 硬取，`params={}` 必炸；更根本的是 hdr 为**数据集特定参数**，进全局配方即破坏 FR-B07 跨数据集复用；plastic 已是反射率（scale=65535）B01 本为 no-op，需转换时单独跑并记 `b01_branch`；③**B05 四法公式**（逐波段 StandardScaler/MinMax、逐谱面积 `np.trapezoid(dx=1.0)`/L2；**numpy 2.5.4 实测已无 `np.trapz`**）+ 零分母三策略 + `NORMALIZATION_DEGENERATE`(400)，不回改 SNV 已发货错误码；④**B06 轴来源契约**——轴经 `params` 显式传入、run 的 wavelengths 不注入（配方自包含）；裁剪闭区间、重采样 `np.interp`/`CubicSpline`（scipy 1.18.1 实测在位）、越界 NaN 禁 clamp/外插、FWHM 取相邻间隔**中位数**；⑤**11.1 证据补档**——`milestone05/` 不存在需 mkdir，README **移动**（git rm）非复制、pytest-full 从 `.runtime/m05-11.1/` 入档 | 科祥取证（S1 418 行/DDL b01_branch/numpy-scipy 实测）+ agent 复核（schema:25 必填性实证） |
| R9 | **codex 11.2 即停：变轴契约未定义（B06 连框架都过不去）**：11.1 的 `registry.py:130` 硬校验 `output.shape != result.shape`（完全同形），crop/resample 改 bands 必被拒；轴只在循环外定义（138 行 return 用旧 axis）。裁定：①**授权最小修改**——`registry.py` 只改形状校验 + 轴传递（130 行 + 循环内 + 138 行 return），`resolve`/`parse_pipeline`/`json_safe`/多版本/确定性一律不碰；`schema/__init__.py` **纯新增**三模型（既有六个一字不动）；`preprocess/__init__.py` **纯新增**三行注册。**已实证 11.1 测试零 `INVALID_OPERATOR_RESULT` 断言（grep 零命中），放宽无连带**。②**轴回传 = meta 保留键 `axis`**（不新增返回形态）：形状校验改为"**第一维（谱条数）不变、第二维（bands）可变**"；meta 含 axis → 校验全有限+严格递增+长度=输出 bands → 替换工作轴；改 bands 未声明 axis → `INVALID_OPERATOR_RESULT`（给过 wavelengths 是陈旧轴污染、没给是审计缺失，一律拒）。③命名 `standardize`（method ∈ standard/minmax/area/vector）+ `crop` + `resample`。**agent 补两点**：①`axis` 校验后**从 meta 移除**、records 只留 `axis_len`+`axis_sha256`（否则每个 crop/resample step 存一份 200 元素数组，多步配方 records 膨胀）；②`CropParams.range` 钉死**两元素元组且 lo<hi**（原稿只写"tuple/列表两元"） | codex 11.2 即停 + agent 取证（grep 零命中 / registry:130 / json_safe 行为） |
| R10 | **变轴参数长度下限（11.2 复核挂账 2）**：`FiniteVector` 现为 `min_length=1`，而 `CubicSpline` 至少需 2 点——`resample` spline + 1 波段 source **裸抛 `ValueError`**（11.2 边角探针实测坐实），是未结构化错误。裁定：`ResampleParams.source`/`.target` 与 `CropParams.source` 改 **`min_length=2`**（裁剪 1 波段无意义，一并收紧），违规在 schema 层报 `INVALID_OPERATOR_PARAMS`。**实现用新增 `AxisVector`（min_length=2），不动 `FiniteVector`**——后者被 11.1 已过闸的 `reflectance.white_reference/dark_reference`、`msc/emsc.reference` 使用，不为一致性动旧模型 | 11.2 复核边角探针（1 波段 + CubicSpline） |
| R11 | **11.3 开工前十一条实现口径（科祥取证 + agent 复核）**：①ICA=sklearn FastICA（lock:41 已声明 1.9.1，非新增依赖；实测同输入 **max diff=0.0**），`random_state` 走 params 默认 0、impl 签名不变；②降维无轴 → `meta["axis"]=null` 显式声明（省略仍拒，R9 不破）；③**B01 前置读原始 DN**——`registry.readable(raw=True)` + run 层自建有界读（`ReadableRows:88` 硬编码 `raw=False`，**禁改 #04**），`b01_branch` 记真实分支（plastic='scale'），11.3 仅 scale/passthrough；④MNF 噪声协方差=相邻波段差分 + `pinv` 防奇异；⑤B09 上凸包在 (band_index, reflectance) 空间、端点固定顶点自动、linear=首尾连线；⑥`scaler_params`=standardize 的 meta.fitted（该列唯一供值路径）；⑦artifacts 仅 sample_spectra+report，failed 无半份；⑧compare 收显式列表、复用 run；⑨SNR 逐像素收集（派生标量 ~1.2MB，红线 4 禁的是原始立方体）；⑩`run.error`=DataError.as_dict JSON；⑪同步执行无后台 | 科祥四探针（sklearn/lock、FastICA diff、open_envi raw、ReadableRows）+ agent 独立复核（lock:41 / superpixels:88 / max diff 0.0） |
| R12 | **codex 11.3 六触即停：run/B08/B10 接缝口径（agent 落盘）**：①**源哈希——payload 无源文件内容哈希**（实证 `model.py:138` as_dict 只含元数据、全仓无 hash 字段），卡 §2.4"复用 payload"前提不成立 → 改 run 预检一次性流式 sha256（禁 stat/元数据冒充；run 时现算比登记期快照硬，换文件必变）；②**预检全前置**（验源→源哈希→annotation_version→recipe_version+STALE→B01 分支判定），NOT NULL 供值齐才建 pending，失败不建 run（半份行不该存在）；③**全局拟合两类分流**——可流式精确不暂存（StandardScaler sum/sumsq、PCA/MNF 两遍块读：均值→中心化外积→eigh/pinv），ICA 暂存选中+B01 像素至 run/.tmp/（finally 必删、禁登记 artifact、禁双副本、字节+RSS 进 report；红线 4 禁原始立方体，派生集为记账例外）；④**MNF 公式钉死**（Σ_Δ=相邻差分协方差 B−1 ddof=1 → 重构 Σ_N B×B：对角 σ_i² 内部=两侧差分方差均值/2 边界=单侧/2，次对角=(σ_i²+σ_{i+1}²−Σ_Δ[i,i])/2 → W=pinv(Σ_N)^(−1/2) → C=W·Σ_S·W → eigh 降序**特征值=解释方差**，载荷=WV 定向，得分=(X−μ)WV）；⑤数值边界：n_components 必填无默认+运行时 ≤bands、NaN 谱拟合排除+变换行全 NaN、连续统零分母→NaN+zero_continuum_bands、SNR 零 RMS→NaN+snr_nan_count | codex 11.3 即停 + agent 取证（payload 无 hash 实证）+ 科祥授权落盘 |
| R13 | **11.5 超时债务（科祥发现 + agent 探针坐实，科祥授权落盘）**：`annotation.rs:325`/`datasets_dev.rs:152` 均 `.timeout(Duration::from_secs(30))`，而 run **同步执行**（R11⑪）——真实 cube B10 逐像素对比预估 10–40s/run（科祥估算，11.7 实测证伪/证实）、compare=N×单 run（S1 场景 N≈3–5）。**超 30s = "Python 已落库 succeeded、前端看到失败"的状态不一致，且 run_id 服务端生成、超时响应丢失后前端无从找回**。裁定：①11.4 维持同步（R11⑪ 不推翻，不改异步）；②**11.5 `preprocess_forward` 超时 ≥300s**（覆盖 S1 典型 N）；③恢复路径=11.4 增 `GET /api/v1/datasets/{identifier}/preprocess/runs`（摘要字段列表，超时后前端凭 cube 找回真实 run）；④**升级线：11.7 实测单 run >60s 或 compare N>5 → 回卡修订议异步，禁在 11.5 只调超时蒙混** | codex 11.4 令审查（科祥）+ agent 探针（两处 30s 实证） |
| R14 | **11.5 开工令三轮审查裁定（科祥三停 + agent 核定）**：①**安全缺口 1：`GetArtifact.kind` 改 `ArtifactKind` enum**（`SampleSpectra`/`Report`），serde 反序列化自动拒非法值，比 `String` 白名单更硬（`annotation.rs:144` `fn uuid()` 同理）；②**安全缺口 2：所有 id 字段加 `uuid()` 校验**（复制 `annotation.rs:144` 8 行，错误码 `INVALID_DATASET_ID`/`INVALID_RUN_ID`/`INVALID_RECIPE_ID`/`INVALID_PROJECT_ID`，后两个新码全仓无先例）；③**优化：`MAX_RESPONSE_BYTES` 复用**（`use spectrum_agent::annotation::MAX_RESPONSE_BYTES`，不重复定义）；④**204 空 body**：`forward()` 判 `status == 204` 返回 `Value::Null`（200+空 body 仍报错，不静默）；⑤**audit_boundary.py 13 处同步**（六→七：line 25 literal / 29 链式替换 `.replace(", annotations_forward", "").replace(", preprocess_forward", "")` / 31 加 `preprocess_forward` dev-only 反断言 / 41 加 `allow-preprocess-forward` count / 42 过滤排除两个 allow / 43 commands 列表 / 49 版本 0.1.1→0.1.2 / 58 authorization 加 TASK-05 / 59 count 6→7 / 60 only_added_command→"annotations_forward,preprocess_forward" / 61 only_added_permission 同理 / 62 product_version 0.1.2 / 65 输出路径改 `milestone05/evidence/11.5/boundary.json`）；⑥**构建生成物全提交**（四个 schema JSON + 六个 autogenerated toml 已跟踪，`cargo build` 更新合法，新增 `preprocess_forward.toml` 一并 add） | 科祥通读即停（三处）+ agent 探针（13 处实测） |
| R15 | **11.6 S06 前端备卡（agent 取证 2026-10-21）**：逐条对读 UI v2.3 S06（原型 1728–1846 行 + 交付表 767 行 + 路由表 2456 行）与 11.1–11.5 已发货接口，得十一项裁定，**其中 D1 为开工阻塞**。**D1（阻塞）前后曲线无数据源**：实测 `.runtime/m05-11.3/.../report.json`（3.4–4.2KB）键为 `run_id/cube_id/annotation_version_id/recipe_version_id/input_fingerprint/source_hashes/label_index/metrics/steps/b01/wavelengths/temporary_*/peak_rss_bytes/...`，**无任何谱曲线**；`sample_spectra.npz` 只有 `mean_i/std_i`（**配方后**），且为 npz 二进制前端不可解析——UI 要求"上：原始反射率／下：SNV+SG"缺"前"。**推荐方案 A**：`run.py` 在 `BoundedInput.lines()` 已产出的 `converted.spectra`（B01 后、配方前）上按类累积均值，写入 report 新增 `curves={wavelengths_in, wavelengths_out, classes:[{label_index,before,after,count}]}`，每类抽样 ≤512 点；不动 11.4/11.5（不加路由、不加第 8 命令、不动 ACL），report 体积 +≤40KB（8MiB 上限余量充足）；成本≈run.py 25 行+3 测试，需科祥授权回改已过闸的 11.3。**备选 B** 新增 `GET /runs/{id}/curves`+Rust 第 8 命令（≈1 天且 audit_boundary 再改 13 处，不推荐）。**D2** `msc`/`emsc` 的 `reference` 为必填 `FiniteVector`（schema:63/67）且 run 层无自动填充，前端无谱来源→**S06 不开放这两算子**，记 11.7 技术债（方案 A 落地后可用 `curves.before` 均值谱作参考，属阶段二）。**D3** `crop`/`resample` 需整条轴：前端以纯函数维护当前轴（初值 `dataset.wavelengths`），crop 只让用户填 lo/hi、resample 用起/止/点数生成等距 target；**轴为空则禁用二者**（实测样例 `wavelengths` 长度 0）。**D4** UI 四处无后端支撑：坏波段剔除（全仓 grep `bad_band` **零命中**）、去背景/仅 ROI（无算子；B09 linear 是谱级连续统不是像素掩膜）、历史 Kappa 表（属 S07/S08）、每步单独预览（run 是整链）——**一律不实现并在界面注明"阶段二/不适用"，不得伪造数值**。**D5** `guard`/`block_size` 不暴露，用默认 `clip`/32。**D6** 同步执行 + R13 恢复路径前端化：超时/`TRANSPORT` 后自动 `list_runs` 找回真实状态，禁直接报失败。**D7** 配方禁用 `reflectance`（`run.py:152` 预检硬拒），前端可选算子列表必须排除。**D8** project_id 取 `annotations.projects()[0]`（阶段一单项目）。**D9** 前端基线实测：本机无 node 24（nvm 仅 v14.21.3/v20.18.0，managed 22.22.2；package.json engines 写 24.19.0 与 #04 回执"node24.19.0"不一致），**实测 managed 22.22.2 `--test` 31 passed / `tsc --noEmit` exit 0**，11.6 验收按 22.22.2 执行并记录差异。**D10** B08 展示口径：三法均有 `explained_variance_ratio`+`cumulative_explained_variance`（`pca.py:39` `variance_meta`），**ICA 必须带 `variance_definition`"非 PCA 方差分解"**。**D11** `report.label_index` 是 `{index: label_id}`（`session.py:327`），类别名需经 `annotations.labels(project_id)` 映射 code；label 缺失时显示 id 前 8 位。**卡新增 §5.1（13 条可验收项）**。**科祥 2026-10-21 裁定：D1=A（`run.py` 补 `curves`，授权回改 11.3，不动 11.4/11.5）、D2=不开放 `msc`/`emsc`（记 11.7 技术债）**；D3–D11 由 agent 裁定并随卡执行 | Agent 取证（report 实例/`run.py:152`/`schema:63`/`session.py:327`/grep 零命中/node 实测）+ 科祥裁定 D1/D2 |
