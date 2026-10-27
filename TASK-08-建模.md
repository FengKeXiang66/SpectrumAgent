# TASK-08 建模

> **状态**：13.1 地基 · 已交付（HEAD `e89cd4b`）；13.2 PLS 回归 · 已实现，自动化验证完成，待独立复核。未 tag、未 push、未打包，未做安装态验收。
> **唯一开卡文件**：`.runtime/codex-132-prompt.txt`（v6），加用户已确认的 A14 HTTP schema 必要增量口径。本文件是 TASK-08 的台账文书，不重复卡内条款。
> **更新日期**：2026-10-26。

## §1 定位

承载 **FR-C01（PLS 回归，P0）** 与建模地基，分两段：

| 段 | 内容 | 状态 |
|---|---|---|
| 13.1 | 训练台账四表 + 标注/预处理/数据三条引用的数据集构建 + CV 与泄漏预检 + 分类指标 | 已交付 |
| 13.2 | 连续量（`sample_target`）+ 整样谱 X + PLS 回归 + 七指标 + KS 划分 + LV 扫描 + 桌面桥 | 已实现，自动化验证完成，待独立复核 |

上游依赖：#02 数据接入、#04 标注、#05 预处理、#07 对话编排。13.2 复用 13.1 的 `plan_folds` 签名、四表 DDL 与 `leak.py` 预检。

## §2 13.1 已交付记录（引用，不重述）

| 项 | 值 |
|---|---|
| 基线 | `19d09da2e4552cc8d011134fed08cd71c93ccc05` |
| 13.1 主体最终 HEAD | `a2ad2cb68e49c4f3a4827a399988c93c8a65e7ab`（7 次提交） |
| 13.1 修复段最终 HEAD | `e89cd4b`（`git log --oneline` 首行实核） |
| 授权文件 | 18 个（3 CHANGED + 15 NEW） |
| 生产行为 | 未接任何模型；生产路径不写 `metric` / `model_artifact`；`model_family` / `model_params` 恒 null |
| 收据 | `.runtime/131-results/receipt.md`（标题即「TASK-08 13.1 实现回报」）<br>`.runtime/131fix-results/receipt.md`（修复段）<br>续跑覆盖指令：`.runtime/131fix-results/continuation-instructions.txt` |

**交付物**：

- 四表：`training_run` / `training_fold` / `metric` / `model_artifact`（`modeling/migrations.py`）。
- 模块：`modeling/{migrations,cv,dataset,leak,metrics,run}.py`。
- 端点：`/api/v1/models` 下 `POST /runs/preflight`、`GET /runs/{run_id}`、`GET /runs`（`api/models.py` L25 router）。
- 测试：`src-python/tests/modeling/` 5 个文件共 33 个 test 函数。

**修复段要点**：R53（`_RawRows` 重构）**已撤销**——缺陷 A 不成立，`modeling/dataset.py` 仍用 `ReadableRows`，仅增注释与等价性断言（收据 A1）。**`_RawRows` 从未落地**，13.2 不得引用。

## §3 13.2 范围

**做**：`sample_target` 表 + CSV 导入 + 样本级取值 UI（补 FR-E02 取值端）；整样谱 X（去背景、绑定标注版本）；KS 划分 + 内层 KFold/LOO；PLS 回归 + LV 双建议；七指标；三表 CHECK 重建；`models_forward` 桌面桥。

**不做**：LV-RMSE 图渲染（13.8）；SPXY / 分层划分；batch 维度；模型注册命名与质检角色（13.8）。

## §4 13.2 裁定（编号 `13.2-R1 … 13.2-R14`）

| 编号 | 裁定 | 要点 |
|---|---|---|
| 13.2-R1 | 连续量存储 | 独立 `sample_target`，cube 粒度，`UNIQUE(cube_id, schema_id)` |
| 13.2-R2 | 表结构扩展 | 重建 `metric` / `training_run` / `model_artifact` 三表；加 `split_strategy`、`target_schema_id` |
| 13.2-R3 | 连续量摄入 | CSV 长表 `cube_name/schema/value` 三级匹配 + 样本级标注两条正路 |
| 13.2-R4 | 整样谱 X | 每 cube 一条；BG 索引读快照 `label_index.json`；流式累加 |
| 13.2-R5 | 解除回归拦截 | `dataset.py` L37 的 `TARGET_UNSUPPORTED` 解除，Y 走 inner join |
| 13.2-R6 | 划分与 CV | KS 自研（确定性）+ 内层 KFold/LOO；回归拒绝 `group_kfold`/`random` |
| 13.2-R7 | 指标口径 | 七指标（R²C/RMSEC/R²P/RMSEP/RPD/RER/偏差）；RPD<2.5 读时派生「仅可做半定量」 |
| 13.2-R8 | LV 扫描 | 同时给 `by_cv_min` 与 `by_elbow` + 曲线；落 `model_artifact(kind='lv_sweep')` |
| 13.2-R9 | API | `api/models.py` 既有 router 增端点；openapi 只增不减；`n_samples` 语义显式化 |
| 13.2-R10 | 前端最小 | 取值 UI + 七指标展示；图渲染留 13.8 |
| 13.2-R11 | 泄漏预检扩展 | 近重复光谱 cosine > 0.999 阻断（FR-F05） |
| 13.2-R12 | 纪律总纲 | Y 来历、指标名、划分策略、CHECK 枚举四处口径以卡为准 |
| 13.2-R13 | 桌面建模桥 | `models_forward` 八个固定 op；5 个文件 + 4 个生成文件 + 桥接测试 |
| 13.2-R14 | 编号口径 | 13.2 用 `13.2-Rn` 独立序列，不续编、不猜全局寄存器 |

三条兼容口径（已并入对应 R）：分类的 `GroupKFold` 原样保留、回归拒绝 `group_kfold`/`random`（R6）；持久层变更仅限白名单四类（卡内 A14b）；`split_strategy` 用 `'none'` 枚举 + `NOT NULL DEFAULT 'none'` + `task` 复合 CHECK（R2）。

## §5 验收（A1–A17）

| 编号 | 判据 |
|---|---|
| A1 | 三表重建 + `sample_target` 建表；行数前后相等；`split_strategy` 三态断言 |
| A2 | CSV 68 行 → `sample_target` 68 行；唯一约束生效 |
| A3 | 关联三校验（未关联 / 待确认 / 覆盖） |
| A3b | schema 解析四校验（精确命中 / 重名报错 / 未知字段 / 非 continuous / 值域越界） |
| A4 | 去背景生效；无 BG 回退；BG 全覆盖报错 |
| A5 | 版本绑定（换版本 X 变 Y 不变；加标签后重跑结果不变） |
| A6 | 回归拦截解除；无 Y 的 cube 自动排除 |
| A7 | PLS 可训；LV 双建议 + 曲线；手动覆盖 |
| A8 | 七指标落库；未定义记 None |
| A9 | KS 确定性 + 含量覆盖（或 `coverage_repaired`） |
| A10 | 分类 `GroupKFold` 原样保留；回归两值拒绝（行为断言，不用 grep） |
| A11 | 近重复光谱阻断 |
| A12 | `n_samples==68` |
| A13 | 样本级取值 UI 写入 `source='annotation'` |
| A14 | openapi 只增不减 |
| A14b | 持久层白名单外零变更（`PRAGMA table_info` 比对） |
| A15 | 五路回归全绿（pytest / node / cargo test / cargo build --release / build） |
| A16 | `_RawRows` 零引用 |
| A17 | `models_forward` 八 op + 越权拒绝 + release 构建通过 |

## §6 前向约束

1. **batch 维度**：现分组键是 cube；将来接入 batch 时键切到 batch，X/Y 仍按 `cube_id` 关联——禁把「cube 是唯一分组」写死。
2. **SPXY / 分层划分**：FR-F02 与 KS 并列的另两种方法，`split_strategy` 枚举已预留取值，13.2 不实现。
3. **跨项目 schema 复用**：`tree_path` 仅项目内唯一；真要做跨项目复用再引入全局 `code`，现不加。
4. **LV 图与模型注册**：渲染与阶段标记载体（实验/候选/生产）留 13.8（FR-F07 为 P1）。

## §7 文书与编号口径

- 仓库此前**没有** TASK-08 文书（根目录只有 `TASK-01…TASK-07`，`find -iname "*TASK-08*"` 为空）。本文件为新建，13.1 的细节**一律以收据为准**，不在此重述。
- 13.1 卡使用 `R1–R8`（`.runtime/codex-131-prompt.txt`）；修复段引用全局寄存器的 `R53–R55`（`.runtime/codex-131fix-prompt.txt`）。三者不是同一序列。
- 13.2 裁定统一记作 **`13.2-R1 … 13.2-R14`**，**不续编、不推测全局寄存器最大值**，避免造出不存在的编号。

## §8 需求索引

| 需求 | 行号（`artifacts/step3/requirements-v2.7.txt`） | 内容 |
|---|---|---|
| FR-C01 | L997-1000 | PLS 回归；LV 自动推荐（拐点/交叉验证最小）与手动指定**须同时给出两者对比** |
| S2 场景 | L536-548 | 涤棉 68 样、KS 划分、七指标、RPD<2.5 标半定量 |
| FR-F02 | L1289-1294 | 划分方法：随机 / KS / SPXY / 分层；划分单位是样品 |
| FR-F03 | L1295-1298 | k-fold / 留一 / 分组 CV；分组键平台强制推导 |
| FR-F04 | L1299-1306 | 回归指标：R²C / RMSEC / R²P / RMSEP / RPD / RER / 偏差 |
| FR-F05 | L1307-1310 | 泄漏检测，含近重复光谱，发现即阻断 |
| FR-E02 | L1156-1159 | 标签体系：枚举/布尔/连续/序数四类；示例即「涤纶含量 → 0–100 连续值」 |

## §9 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-26 | 新建本文件；登记 13.1 已交付记录与 13.2 备卡 v6 的 14 条裁定、17 项验收；确立 `13.2-Rn` 编号口径 |
| 2026-10-26 | 按 v6 与用户已确认的 A14 口径完成 13.2；保留以上历史记录和 `13.2-R1…R14` 序列，补实现证据、口径差异和前向限制（§10） |
| 2026-10-26 | 13.2 独立复核通过；收口三项非阻塞修补：`build_sample_training_set` 波长轴一致性断言（`WAVELENGTH_AXIS_MISMATCH`）、`run.py` `training_fold` 内层 CV 折语义注记、`assert` 改显式 raise 且失败路径 `from error` 透传（消息只带异常类型名，不泄露异常文本）；`capabilities/main.json` models-forward 从句归位至「不开放通用网络能力。」之前。提交 `fe67e85`（代码+测试）与 `36431c9`（台账+ACL），收据 `.runtime/132fix-results/receipt.md` |
| 2026-10-27 | 13.3 评价可视化（P0）：Canvas 2D 四图——FR-G04 的回归散点/残差、潜变量 RMSECV 曲线，加 S2 L545 的预测含量直方图；不宣称覆盖整个 G04。新增坐标/刻度/断线/分箱纯函数，按校准/预测分色、标记产物原值 LV 与半定量提示，空值/常量/缺产物/缺预测显式说明。纯函数 21 项、Node 全量 144 项通过，build exit 0，B1–B10 证据及自定项见 .runtime/133-results/receipt.md；零 Python/Rust/依赖改动。分类两图待分类训练，波段系数图待取数通道独立申报；注册/批量推理/含量图留 13.4，质检角色属 J 域阶段二。 |
| 2026-10-27 | 13.4（FR-F07 / FR-F08 / FR-G07 含量部分）：追加 model_registry 与独立 inference_run/inference_artifact，注册重建标定协议 v1、排序三元组指纹、同名原子取号；同目标 production 唯一，显式切换并将旧生产回落 candidate（阶段一灰度降级，无比例分流）。六个固定桌面操作接通注册与批量推理面板；像素流式 reshape、手工 PLS 预测并 ravel，五类跨样本拟合算子仅重放已存 fitted 或 mean/loadings，不改训练及预处理公共契约。全图预测、三态掩码、统计只含已标前景；固定训练 Y 彩色色带，披露越界总数与上下方向，pixel_mean 与 sample_prediction 并列；图区和元数据声明「模型训练粒度＝样品均值谱；像素级预测为域外外推，仅表示含量空间分布趋势」，RPD<2.5 同标「仅可做半定量」。FR-G07 区间叠加降级为全局训练残差均值 ±1 SD 加适用性图（任一变换后特征超出训练范围即域外，占比>0），不宣称覆盖解混丰度图。前向限制：operator/code_version/duration_s 与完整 run manifest 缺口保持待办，不以机器信息充当身份；解混丰度图、波段系数图、超参搜索另卡；「标定由注册时重建得出，非训练时实测值，可审计不可反证」，本次 source_hashes 随 calibration 保存，13.2 未存训练当时源哈希，不能反证历史标定；训练数据不可读显式 TRAINING_DATA_UNAVAILABLE 且零写入。含量图超过既有 8MiB 通道上限时保留统计并报 MAP_TOO_LARGE；真实大体量性能与安装态冒烟另验。证据与 C1–C15、自定项、快照见 .runtime/134-results/receipt.md（本地收据不入 git）；未 tag、未 push、未打包。 |

## §10 13.2 实现与验证记录

实现基线为 `e89cd4b0d4c5859260e279afdebe1201176653ab`。连续量从 CSV 或样本级手填进入 `sample_target`；X 由显式选中的成功预处理 run 绑定标注版本，沿既有 `ReadableRows(raw=False)` 流式累加前景均值。回归使用 KS 外层划分与训练集内 KFold/LOO 选 LV，同时保存两种建议、手动选择值、预测残差及七指标。桌面工作台经八个固定 `models_forward` 操作接入。

验收命令、执行模式、逐条 A1–A17（含 A3b/A14b）、提交记录和前后 SHA256 见本地交付收据 `.runtime/132-results/receipt.md`。原始日志保存在同目录；不将该收据当作安装态验证或发布证明。

| 证据 | 结果 / 断言 |
|---|---|
| `tests/modeling/test_migrations.py::test_132_upgrade_preserves_three_rows_per_table_and_foreign_keys` | 原四表各 3 行保留；旧字段信息与 `training_fold` SQL 不变；外键审计为空；真实 COMMIT 与重复迁移通过；分类默认 `none`、回归遗漏划分被 CHECK 拒绝 |
| `tests/modeling/test_regression.py::test_real_asgi_csv_annotation_pls_68_samples_and_lv_endpoint` | 真实 ASGI/数据库/源谱/PLS：68 条 CSV、68 样品、272 前景像素、7 项指标、LV 端点；成功预处理行由 fixture 显式构造 |
| `tests/modeling/test_regression.py::test_sample_mean_bg_version_binding_snapshot_index_and_missing_y` | 快照索引换序、后来增加标签与最新版本均不改变原 run 绑定结果；显式换绑定版本则 X 变、Y 不变；无 Y 样品排除且引用仍等长 |
| `tests/modeling/test_regression.py::test_pls_curve_manual_metrics_artifacts_and_train_only_cv` | KFold/LOO 双路径；所有拟合仅见外层训练样品；双 LV 建议、手动覆盖、曲线、模型重放与 SHA256 校验；外层指标 `fold_index=NULL` |
| `tests/modeling/test_regression.py::test_undefined_scores_persist_null_not_zero` | 常量 Y 的四个未定义分写 SQL NULL；不填 0 |
| `tests/modeling/test_regression.py::test_near_duplicate_spectra_block_before_run` | 原始均值谱余弦近重复阻断，`training_run` 零行 |
| `src-tauri/tests/models_forward.rs` | 八个 op 通过真实回环假引擎；越权、路径穿越、身份不符、敏感响应与响应上限被拒绝；两份 handler 和 ACL 对齐 |

| 最终自动化出口 | 结果 / 执行模式 |
|---|---|
| Python 全量 | 1172 passed = backend 45 + src-python 非 agent 860 + agent 267；三个独立默认 pytest 进程，无 cache；每次先查 C 盘并预建 E 盘临时根 |
| Node | 123/123；Node 24.22.1 默认 `--test` |
| Rust | 81 passed（含 1 doctest）；`cargo test --offline`；桥接定向 4/4，八 op 全部实发 |
| release 编译 | `cargo build --release --offline` exit 0；仅编译二进制，无打包 |
| 前端 build | TypeScript + Vite exit 0 |
| 原 #08/#05 链 | `scripts/e2e_task08.py` 116/116；真实导入、标注、预处理与分类预检回归 |
| 原 #07 链 | 218/218；无并行测试/构建的独立执行；忽略目录副本仅迁移 OUT，冻结证据不变 |
| OpenAPI snapshot | `tests/data/test_api.py::test_api_schema_snapshot` passed；旧 operation 和其余旧 schema 比对通过 |

**已申报的口径差异与实现选择：**

1. A14 按用户明确批准的例外执行：旧 `PreflightRequest` 仅扩展 CV 枚举与可选 `split_strategy`；所有旧 operation 定义、其余旧 schema、required 列表保持不变。新增 4 个 path、5 个 operation、3 个 schema（`POST /runs` 复用原 GET path）。
2. A10 的「现有测试不修改」与旧参数化中「回归 random 可用」冲突。该单个回归参数改为 kfold，并另加 group_kfold/random 均拒绝的行为断言；分类参数与 GroupKFold 分支保留。
3. R2 的重建步骤采用 create/copy/drop/rename，避免先重命名旧父表时 SQLite 自动改写 `training_fold` 外键。`foreign_keys` 全程保持 ON；完整外键审计后清除 SQLite 延迟 DROP 计数，并恢复调用者的 deferral 设置。真实提交验证通过。卡称旧 INSERT「7 列」，实物为 11 列；保留实物字段列表并验证默认值。
4. 所选有效样品必须使用相同配方步骤和参数（否则 `RECIPE_MISMATCH`）。均值谱应用既有 pipeline 的全数据拟合限制仍由 `preprocess_full_fit.acknowledged` 与 `affected_steps` 显式记账；本段未实现训练折专用算子拟合。PLS 自身拟合和 LV 扫描限制在训练集合内。
5. CSV 按行返回无效字段、重名、未知字段、越界和未关联清单；有效行继续导入。显式覆盖时同一键的后行生效；默认不覆盖。损坏 CSV 返回 `INVALID_TARGET_CSV` 且零写入。
6. 模型以 JSON 系数、截距和输入均值保存，避免对象反序列化；测试按保存值重放预测并校验产物哈希。尚无跨 sklearn 版本的模型注册协议。

**前向限制：**真实桌面点击与安装态冒烟留待实际运行验证；本段证据覆盖前端适配器、Rust 回环桥、真实 REST 和构建。LV/分布/残差图渲染、SPXY/分层、batch、模型注册与角色继续按 §6 排期。无新增依赖；未改标注、预处理或后端既有表结构。

**复核收口注记（2026-10-26）：**

1. `training_fold` 在回归路径记录的是**内层 CV 折**，外层 KS 划分只存于 `model_params.train_cube_ids/test_cube_ids`；该表在 13.1 分类路径下记录评估折。跨实验读取或将来按折复现时，须先核对 `task` 与 `model_params`，勿直接当评估折画学习曲线。
2. 波长轴一致性由 `build_sample_training_set` 断言封死：各 cube 须共享同一刻度（全部未知视为一致），否则 `WAVELENGTH_AXIS_MISMATCH`。registry 的 `SOURCE_CHANGED` 只防单 cube 登记后漂移，不防跨 cube 轴不一致，故跨仪器合并项目仍应在导入端把关。
3. 68 样品链的前景像素为 272（4 像素/样品），`row_blocks` 流式累加仅在结构上验证，未在真实大体量上压测；留待冒烟或后续卡用大体量数据复验。
