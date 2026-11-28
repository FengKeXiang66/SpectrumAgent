# 回归折内预处理：算子覆盖表与实施基线

状态：1a / 1b 已实现，最终验证记录见文末。1d 已独立提交为 `57bf763`；本文件保留实施前的核查依据，并单独列出本轮变更。

## 范围与现状

本轮先修复现有样品均值谱 PLS 回归的拟合范围、训练状态保存及注册重放，不迁移历史记录，不改变高级配方报告的执行语义，也不引入深度学习接口。

实施前核查（以 1d 提交为基线；下面标为“原”的行为已在本轮修复）：

- `src-python/spectrumagent/preprocess/__init__.py`：实际注册 **13** 个 v1 算子。
- `src/components/preprocess/pipeline.ts`：对话编辑器开放其中 **10** 个；reflectance 由 run 管理，MSC/EMSC 尚未在编辑器开放参考来源配置。
- `src-python/spectrumagent/modeling/dataset.py:build_sample_training_set`：原实现从确认标注提取均值谱，对全部样品先执行配方。
- `src-python/spectrumagent/modeling/run.py:TrainingRuns.regress`：原实现随后才进行 KS 划分和内层 CV。
- `src-python/spectrumagent/modeling/registry.py:ModelRegistry.register`：原实现注册时重新构建回归标定状态。
- `src-python/spectrumagent/modeling/inference.py:apply_with_calibration`：已实现冻结状态的只读变换，跨样品拟合算子不会在推理时重新 fit。

下表的“可复用”表示已有数值实现或变换公式，不表示新训练协议已经实现或通过验证。所有状态必须与算子版本、参数、步骤顺序、输入波段及拟合来源绑定。

## 编辑器开放的 10 个算子

| 算子 / 模式 | 是否跨样品拟合 | 需要冻结的状态 | 只 transform 的已有路径 | 与现版本数值等价的条件 / 失败边界 |
| --- | --- | --- | --- | --- |
| `sg_smooth` | 否；沿每条光谱的波段轴计算 | 参数、v1 算子版本、输入维数 | 原 `savgol.smooth` | 保留 window、polyorder、mode；interp 窗口不超过当前波段数；不改边界算法。 |
| `sg_derivative` | 否 | 参数、版本、导数单位 `band_index` | 原 `savgol.derivative` | v1 固定 `delta=1`，保留 order。不能直接按名称替换成使用 `delta_nm` 的分类 savgol。 |
| `snv` | 否；每条光谱分别求均值、标准差 | 参数、版本、`ddof=0`、zero_std 规则 | 原 `scatter.snv` | 保留总体标准差与零方差策略；分类 SNV 默认 ddof=1、退化判据也不同，不能直接视为等价。 |
| `standardize: standard` | **是**；按训练样品、逐特征拟合 | 每特征 mean/std、零尺度规则、拟合样品数 | 已有冻结标定的 `(X-mean)/std` 分支 | 保持 ddof=0；验证和测试只使用训练参数。纯矩阵 `standardize` 与流式 `fit_standard` 的方差算法不同，不能仅因字段同名就承诺逐位相等。 |
| `standardize: minmax` | **是** | 每特征 min/max、零尺度规则、拟合样品数 | 已有冻结标定的 `(X-min)/(max-min)` 分支 | 极值只来自训练样品；变换后的验证值允许超出 [0,1]，不得额外按验证数据重标定或裁剪。 |
| `standardize: area` | 否；每谱积分 | 参数、版本；无全局 fitted 数组 | 原 `standardize` 的 area 分支 | 保留按波段索引积分 `dx=1`，不能改成物理波长积分而沿用版本。 |
| `standardize: vector` | 否；每谱 L2 范数 | 参数、版本、零尺度规则 | 原 `standardize` 的 vector 分支 | 保留零分母行为；分类 l2 的 epsilon 规则不同，不直接互换。 |
| `crop` | 否 | 当前 source 轴、闭区间 range、输出轴 | 原 `crop` | source 必须匹配当前输入轴与维数；至少命中一个波段；输出波段顺序不变。 |
| `resample` | 否；每谱插值 | source/target、插值方法、输出轴 | 原 `resample` | 保留 linear/spline 与不外推规则；越界产生非有限值时严格训练应明确失败，不自动填补。PCA 等操作清除物理轴后，不允许凭空恢复波长轴。 |
| `pca` | **是** | 训练均值、loadings、版本、诊断元数据、输出维数 | 已有 `(X-mean) @ loadings` | 复用 `fit_pca` / 原矩阵 PCA 的协方差算法及定向规则；不能直接换成分类 sklearn PCA 并声称分量逐位相等。训练侧样品数、维数及下游 LV 必须可用。 |
| `mnf` | **是** | 训练均值、loadings、噪声估计与诊断元数据、输出维数 | 与 PCA 共用已有线性 transform | 复用 v1 的相邻波段差分噪声估计和白化；非半正定等退化按原规则失败，不静默改估计器或增加修正项。 |
| `ica` | **是** | 训练均值、定向后的 loadings、random_state、版本与诊断元数据 | 与 PCA 共用已有线性 transform | 复用 `fit_ica`；仅在训练侧运行 FastICA。保留随机种子、库版本和分量定向，样品不足等情况明确失败。 |
| `continuum` | 否；每谱计算连续统 | method、版本、波段索引语义 | 原 `continuum` | 保留 convex_hull/linear 与零连续统行为；非有限结果不得自动填补后训练。 |

`standardize` 在表中按 4 种模式拆行，算子名称仍然只有 10 个。判断拟合范围必须依据模式，不能仅检查 `op == standardize`。

## 后端另外注册的 3 个算子

| 算子 | 是否跨样品拟合 | 状态 / 参考与 transform 路径 | 首版严格训练边界 |
| --- | --- | --- | --- |
| `reflectance` | 给定标定参考或比例因子后不跨样品拟合；分支选择还检查输入和 HDR 判据 | hdr、branch、white/dark 参考、guard；原 `reflectance` | 高级 run 有隐式 B01 转换，不能把它与用户配方中的显式步骤混为一谈。新回归须记录输入所处阶段和标定来源，防止漏做或重复转换；分支歧义按现有规则失败。该算子不新增到编辑器。 |
| `msc` | 当前实现要求显式 reference；逐谱求回归系数，不自动学习全样品参考 | 固定参考谱、参考指纹、版本；原 `scatter.msc` | reference 不是“无需来源审查”：若来自本数据集，必须明确是否只由训练侧生成。首版保持编辑器不开放；来源不明时不能承诺严格独立评估，不自动改用全样品均值参考。 |
| `emsc` | 同 MSC，另含每谱多项式基线系数 | 固定 reference、polynomial_order、版本；原 `scatter.emsc` | 同 MSC；保留设计矩阵和秩检查，不将逐谱系数误当作跨样品全局拟合状态。 |

历史配方/模型继续走原版本读取路径。后端注册成功不等于任意组合已满足新协议；新协议的未覆盖步骤、未知版本、缺失状态或无法确认的引用必须明确失败，不能回退到全数据 fit。

## 1a：执行层决定

保留 `modeling` 回归入口与历史产物格式读取路径。采用已有分类侧验证过的训练/变换分离约定，复用高级配方自己的算子数值实现，不把分类 `SpectralPipeline` 直接用于全部回归配方。

最小实现边界：

1. 拆出只读原始样品均值谱与输入来源的提取路径，使回归可以在任何跨样品 fit 之前获得 X_raw；其他调用方的历史行为不暗中改变。
2. 新协议的 KS 外层划分使用声明明确的原始样品均值谱，保存依据和样品清单。KS 会读取待划分池的原始 X 来选择划分，这是划分算法本身；禁止的是先在全体 X 上拟合标准化/PCA，再以其输出定义划分。不使用“先求训练统计量再决定训练集”的循环定义。
3. 内层每折，先在该折训练均值谱上顺序执行配方并获取 fitted 步骤记录，再以冻结状态变换该折训练/验证数据，之后才训练 PLS、选择 LV。
4. 最终只在外层完整训练集拟合一次预处理与 PLS，外层测试数据只 transform/predict。
5. transform 复用并提取现有 `apply_with_calibration` 的冻结变换数值路径，避免训练和部署各写一份重放公式。原有部署路径继续调用同一实现并保留原版本兼容。

训练集内预处理范围的变化是新协议的预期行为；“与现版本等价”指相同拟合人群、相同参数、相同版本下的数值语义，不要求与历史全数据拟合的结果相同。

### 1a 独立验收

- 观测每次 fit 的样品编号，必须等于相应训练折，不含验证或外层测试。
- 在固定外层/内层划分下，扰动验证/测试 X 或 y，不改变对应训练侧预处理状态和模型训练结果。外层 KS 的独立测试与数值拟合隔离测试分开，避免修改候选池后重新划分而产生误判。
- 拟合后将各跨样品 fit 入口替换为抛错桩，验证/测试 transform 仍能成功。
- 在固定划分、参数和环境下比较原谱、固定 SG 防退化结果；不要求标准化/PCA 的分数必须发生变化。
- 逐一覆盖 standard/minmax、PCA、MNF、ICA，以及无状态算子和组合顺序；检查维数、物理轴、样品不足和非有限结果的错误行为。未支持路径必须有明确拒绝。
- 训练各折的 PCA/ICA 维数及 PLS LV 不得通过静默降低用户参数来修复。

## 1b：训练状态快照与兼容

- 新训练使用明确的协议版本标记，独立记录 KS 输入表示、外层划分、内层折、配方版本、输入指纹和拟合来源。
- 保存最终训练侧实际使用的完整预处理状态及 PLS 参数；注册读取该训练产物，不重新从数据构建状态。
- 注册校验训练状态引用和校验值，训练时记录的预测必须能由重载产物重放。
- 冻结状态变换后的训练/测试预测、保存前后预测、注册后对同输入的预测一致；同一路径承诺精确一致，跨实现或 BLAS 计算路径的数值容差另行明确，不能只检查输出维数。
- 旧模型仍保留 `registration_reconstruction` 的来源声明，不自动改标为训练状态快照。比较界面/工具须检查协议一致性，不静默混排新旧成绩。
- 1a 和 1b 可分开审查与测试，但必须配套交付；不能发布“新训练、旧重建注册”混搭的链路。

## 对话与集成验收边界

- 1c 另行增加回归训练方案状态、revision、方案卡与执行路径；现有预处理草稿不冒充完整训练方案。
- `modeling.infer` 发起回归推理，`modeling.inference` 查询结果。自然语言需要绑定模型、数据、标注版本和处理引用，需单独验证引用解析、错误纠正和结果展示；工具存在不代表该体验已经验收。
- 分类和回归推理分别验收，保留“样品均值谱训练、像素输出为外推”的既有适用范围说明。
- NPZ Study 分别覆盖有 `groups_key` 的分组路径和无分组信息的 exploratory 路径；分组字段不能自动当作实物真值定义。
- 会话恢复读取草稿 revision、方案卡、任务及结果，不重放历史 workspace 导航。

## 1d 提交验证记录

独立提交：`57bf763 feat: move preprocessing configuration into assistant chat`。

- Python：`tests/test_preprocessing_editor.py`、`tests/test_current_workflow.py`、`tests/test_agent_router.py`，20 passed。
- 前端：`preprocessing-editor.test.mjs`、`assistant-catalog.test.mjs`、`chat-labels.test.mjs`，17 passed。
- Rust：`cargo test --manifest-path src-tauri/Cargo.toml --lib --locked --offline agent::streaming_tests --no-fail-fast`，13 passed，完成 Rust 转发层编译验证。
- `npm run build` 与 `git diff --check` 通过。构建保留现有分包提示；Python 有 Starlette 依赖弃用提示。
- 尚未重新打包或启动更新后的桌面 EXE，未推送 GitHub。桌面运行验证与已完成的源码/编译验证分别记录。

## 本轮实现与审查边界

### 1a：拟合隔离

- `preprocess/fitted.py` 提供最小的 fit/transform 分离，复用原有 v1 高级配方数值核。冻结变换从旧推理实现提取，历史推理和新训练共同使用；没有把分类 experiments 草稿或 schema 迁入回归。
- `modeling/dataset.py` 新增不执行配方的读取选项，原调用方默认行为保留。新回归按固定图像行顺序累计均值，与部署的样品预测一致。
- `modeling/regression.py:select` 每折拟合一次配方，冻结变换后比较 LV；保存各折的真实状态和样品编号。最终拟合独立执行，只使用外层训练样品。
- 每一步拟合后先走冻结变换，再拟合下一步，消除链式降维等操作的批矩阵与逐行重放计算路径差异。
- KS 输入改为原始样品均值谱；保留 KS 原有候选池 z-score 距离和含量范围修复，均在划分记录中声明。
- 首版开放原编辑器的 10 个算子，含 standardize 的四种模式。显式 reflectance、MSC、EMSC 在新严格训练中拒绝，未暗中扩展参考来源约定。

### 1b：快照、注册、推理

- 新协议为 `sample_pls_foldwise_v1`；无协议标记的旧回归显示为 `sample_pls_full_fit_legacy`，保留原注册重建路径。
- 训练保存 `calibration.json`（真实训练状态）、`split.json`（外层划分与内层状态）、`replay.json`（只用于本机重放的输入均值谱及来源），以及原有模型、预测、LV 产物。内容不通过工具摘要发送给模型服务。
- 训练完成前读取实际保存的文件重放逐样品预测。快照记录算子版本、代码校验值、库环境、训练来源和 PLS 实际参数。
- 新注册路径检查产物校验值、训练身份、样品与标注绑定、划分和逐样品预测，直接复制训练快照，不重新读取原始数据或测量值，也不重新拟合。
- 训练账本新增 calibration/split/replay 产物类型；启动迁移保留旧产物行、唯一约束和外键，迁移可重复执行。
- 结果、台账、注册界面和对话摘要显示新旧口径。对话跨协议比较返回不可直接比较标记，不将旧成绩自动改标为新协议。
- `modeling.infer` / `modeling.inference` 的原有调用和确认边界保留；集成测试按 cube 绑定当前处理与标注引用，不按列表位置猜测。

### 尚未包含

上述 1a/1b 阶段未包含回归训练方案卡；后续 1c 的实现与验证见 [回归对话方案](regression-conversation-plan.md)。回归预处理联合选优、实物级 Study 评分及深度学习接入仍未实现。没有重新打包桌面 EXE，也没有推送远端。

## 本轮最终验证

- 后端全量：`python -m pytest tests -q --tb=short --show-capture=no`，**205 passed、1 skipped**。最初沙箱执行只有 DPAPI 测试报 WinError 2；该单项及最终全量均在正常本机权限下通过，测试使用临时目录与固定假密钥。
- 新增 `test_regression_pipeline.py` 覆盖 10 个算子及不同归一化模式、链式降维、冻结重放不调用 fit、折内样品与数值参数核对、外层测试扰动隔离、固定划分的原谱/SG sklearn 数值基线、参考/轴/退化拒绝、真实 ENVI 回归注册推理、缺失快照拒绝、旧模型读取及迁移外键保留。
- 扩展原对话集成用例，走通预处理表单、处理、测量值、训练确认、注册、推理确认和结果查询。模型响应由测试脚本提供；此项验证真实对话路由和工具执行，不代表已实测外部模型服务的自然语言规划质量。
- 前端：`node --test tests/*.test.mjs`，**24 passed**；最终 `npm run build` 通过，保留既有分包提示。
- `git diff --check` 与新增模块的 Python 编译检查通过。本轮没有改动 Rust，沿用 1d 已完成的编译与 13 项转发测试记录。
- 本轮 1a/1b 改动与覆盖文档仍留在工作区待审查；未新增本地提交、未推送、未重新打包桌面应用。
