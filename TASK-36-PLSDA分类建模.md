# TASK-36 · PLS-DA 分类建模卡（正式卡）

> **目标**：把 S07 从「只有 PLS 回归单轨」补齐为需求/原型要求的「PLS-DA 分类 + PLS 回归」双轨，交付**分类训练 → 分组交叉验证 → 指标与混淆矩阵 → 落库 → 结果/台账展示**的完整闭环。所有指标由真实后端算子计算，界面不出现任何示例数值。
> **前置**：TASK-35 已收口于 `5cdc820`（六文件已提交）；需求方 G4 手测通过。工作区实测 **15 项**（14 个 `artifacts/step2/*` 行尾噪声 + 1 个未跟踪 `docs/AI自动标注路径分析.md`），**禁触碰、禁提交**；本地领先 `origin/master` **219** 笔未 push。
> **事实源（唯一基线）**：需求 **v2.7** = `E:/中达瑞和公司/光谱数据AI-Agent处理平台_需求分析与设计.html`；UI **v2.3** = `E:/中达瑞和公司/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.html`。**用户本轮 @ 的 `10月15日/` 两份是归档副本（需求 v2.6 / UI v2.2），不得作为基线**（项目红线，TASK-25 §0 / TASK-35 已立）。
> **卡型**：**正式卡**。跨后端训练链、API 契约、openapi 快照、Rust/TS 契约、S07/S08/S09 三屏与源码 pin，远超轻量卡 2 文件上限；含 DDL 零改动裁定与 pin 授权清单。
> **三道闸门**：① 开工 `git status` 对照 §0.1 的 15 项快照（工作区本来不干净，不是要求空）；② 开工复跑 §0.1 基线并贴原文；③ 开工 `grep -n` 复核 §0.2/§0.3 全部锚点与 §0.4 全部 pin。
> **即停条款**：行号与实物不符须在回报中显式说明，不得自行改写本卡；卡内未写死的口径一律停下问，不许自造。

---

## 0. 事实底座（2026-11-07 18:04 备卡方实测）

### 0.1 基线

| 项 | 实测值 | 取数命令 |
|---|---|---|
| HEAD | `5cdc820 feat(ui): TASK-35 S06 预处理配方界面美化（v2.3 视觉语言 / 真实数据卡片化）` | `git log -1 --oneline` |
| 工作区 | **15 项**：14 个 `artifacts/step2/*`（行尾变化 656+/656-）+ `?? docs/AI自动标注路径分析.md` | `git status --short` |
| 前端（源码口径） | **271 / 271 pass，fail 0** | `node --test "src/**/*.test.ts"`（**禁裸跑**） |
| tsc | `npx tsc --noEmit` EXIT=0 | 同左 |
| 远程 | 领先 `origin/master` **219** 笔，未 push | `git rev-list --count origin/master..HEAD` |
| Python / Rust | **本卡开工按闸门②实测贴当段原文**；历史 collected `1568`、Rust 13 组仅为溯源值，不作跨卡阈值 | 见 §4 G3/G4 |

### 0.2 需求与 UI 锚点（行号 `grep -n` 直取，根目录基线）

| 事实 | 文件:行 | 要点 |
|---|---|---|
| C 域阶段一 | 需求 v2.7 `:486` | 「分析与建模 10 项，P0 5 / P1 3 / P2 2，**阶段一**」 |
| **FR-C02 PLS-DA** | v2.7 `:607` | 「判别分类，输出**类别概率与置信度**；对未达阈值的像素标记为"不确定"而非强行归类」**P0** |
| FR-C01 / C03 / C04 / C05 | v2.7 `:606 / :608 / :609 / :610` | PLS 回归（已实现）/ 经典分类器 / 波段选择 / 聚类，**均 P0、本卡不做** |
| FR-C06~C10 | v2.7 `:611-615` | 指数、解混、空谱分类 P1；深度模型、异常检测 P2 |
| 分组划分 / CV | v2.7 `:715 / :716` | FR-F02 划分单位必须是**样品**；FR-F03 **GroupKFold by sample_id，分组键平台强制推导、不允许用户关闭** |
| 分类指标 | v2.7 `:717` | FR-F04「OA / AA / Kappa / 每类 F1 / 混淆矩阵」 |
| 泄漏预检 | v2.7 `:718` | FR-F05 样品级重叠、近重复（余弦 > 0.999）、近邻跨侧，**发现即阻断** |
| 指标双报 / 种子 | v2.7 `:1990-1992 / :2000 / :2004` | 像素级 + 样品级；均值 ± 标准差；run 级种子统一控制并入库 |
| LV 双建议 | v2.7 `:2003` | 「CV 最小」与「拐点法」两个建议 + RMSE vs LVs 曲线让用户决策 |
| run manifest | v2.7 `:2215 / :2447-2468` | v2.7 **10 字段**（含 `annotation_version_id`/`metrics`/`artifact_path`/`operator`/`duration_s`）；FR-F01 `:714` 台账 P0 |
| 算子表 / 编排 | v2.7 `:1717 / :1720 / :1738 / :637 / :1664` | `train_plsda`、`cross_validate`（强制 GroupKFold）、`leakage_check`；FR-D01 对话解析 P0 |
| **阶段边界** | v2.7 `:2932 / :2954 / :2955` | 阶段一约 15 个 P0 算子（接入/预处理/PLS/指标）；**模型预标注、实验台账与模型注册、批量推理归阶段二** |
| 归档差异（需求） | v2.6 `10月15日/:2213` | run manifest 仅 **5 字段**，与 FR-F01 不对齐 → **一律按 v2.7** |
| S07 段 | UI v2.3 `:1837-1932` | 页头 `:1842`「分类与回归双轨」；双轨按钮 `:1853/1854`；分组 5-fold `:1880`；泄漏提示 `:1881`；LV `:1884-1885`；iPLS `:1889`；预检 `:1896-1900`；日志 `:1906-1913` |
| S08 段 | v2.3 `:1934-2014` | OA `:1946`、Kappa `:1947`、像素 `:1948`、LVs `:1949`、混淆矩阵 `:1955`、分类图 `:1978`、RMSE 拐点图 `:1996-1998`、波段重要性 `:2002-2004` |
| **S08 是 mock** | v2.3 `:1939 / :1947` | 「以下为**版本化 mock 展示，非真实 NAS 实测**」；「既有 Kappa 例值 · 待核对」「0.921 与本矩阵推导 0.918089 不一致」→ **示例数值一律不照搬** |
| S08 无置信度控件 | v2.3 `:1934-2014` 段内 0 匹配 | 需求 FR-C02 要求置信度/不确定，原型**未给控件** → 按 R8 只落数值，不做图 |
| S09 段 | v2.3 `:2016-2107` | Kappa 筛选 `:2032`、表头 `:2043`「run_id｜数据集｜配方｜模型｜OA｜Kappa｜LVs｜耗时｜时间」、复现命令 `:2096-2098` |
| 明确不做（UI） | v2.3 `:587 / :593 / :1844 / :1855` | 超参搜索/多实验对比/深度模型/批量推理页；ROC-PR/报告导出/时序 ROI；独立训练模板入口已移除；回归分支说明为静态 |
| 归档差异（UI） | v2.2 `10月15日/` | S07 有「作为模板保存」、S08 指标口径与 v2.3 不同（21.6 万像素 → 782,500）→ **一律按 v2.3** |

### 0.3 代码锚点（HEAD `5cdc820`，`grep -n` 直取）

| 事实 | 路径:行 | 要点 |
|---|---|---|
| DDL 已为分类预留 | `src-python/spectrumagent/modeling/migrations.py:3-14` | `training_run.task CHECK('regression','classification')`、`cv_strategy CHECK('group_kfold','random','kfold','loo')`、复合 CHECK `:12-13` |
| metric / artifact 枚举 | `migrations.py:20-30` | `metric.name CHECK('oa','kappa','rmse',...)`、`scope CHECK('pixel','sample')`；`model_artifact.kind CHECK('model','confusion','predictions','lv_sweep')`、`UNIQUE(run_id,kind)` |
| 其余表 | `migrations.py:31-61` | `sample_target`、`model_registry`（`stage CHECK`）、`inference_run`、`inference_artifact` |
| **分类只到预检** | `modeling/run.py:40` `preflight`；`:18` | `:18` 只 `from .metrics import _regression, REGRESSION_METRICS`；预检写 `training_run` + `training_fold` 后即结束，**不训练分类器、不写 metric / model_artifact** |
| 回归训练入口 | `run.py:135 regress` / `:183` / `:192` | PLSRegression fit；指标落库 `:214` / 产物 `:216` |
| **分类指标纯函数已有** | `modeling/metrics.py:42-46` `_score`（oa/kappa/confusion/labels）、`:66 score_predictions`、`:74 summarize_folds`、`:85` 双报 | **未接入生产链**（`run.py:18` 只引回归） |
| CV / 数据集 / 泄漏 | `modeling/cv.py:8 plan_folds` / `:12-14`；`dataset.py:23/43/61/122/127`；`leak.py:9/33` | `plan_folds` 已按 task 分派，分类允许 `group_kfold`；`dataset.py:43` 分类分支已存在；泄漏预检现成 |
| 注册只放行回归 | `modeling/registry.py:85` | `if run["task"] != "regression"` → 本卡**不注册分类模型**（R11） |
| 推理链 | `modeling/inference.py:234 create` / `:166 _prepare` / `:38 apply_with_calibration` / `:104 predict` | 含量图推理，本卡不动（TASK-33 契约红线） |
| API 端点 | `src-python/spectrumagent/api/models.py:96-166` | 15 个 `@router`，`prefix=/api/v1/models`；`POST /runs` 在 `:136`、`POST /runs/preflight` `:149` |
| TrainBody 写死回归 | `api/models.py:50` | `task: Literal["regression"] = "regression"` → 本卡扩为联合（R5） |
| PreflightBody 已支持分类 | `api/models.py:20` | `task: Literal["classification","regression"]` |
| openapi 逐字节断言 | `src-python/tests/data/test_api.py:211-214` | `client.app.openapi() == expected` 且**文件字节**比对 → 改 schema 必须重生成快照（R5 显式授权） |
| 前端契约 | `src/components/modeling/api.ts:5 / :14 / :33-39 / :42 / :50` | `:5 TrainBody.task:'regression'` 写死；`:14 PreflightBody` 已含 classification；15 个 op 判别联合；统一 `models_forward` |
| Rust 契约 | `src-tauri/src/models.rs:10-11 / :25 / :28 / :127-132` | `#[serde(tag="op", rename_all="snake_case", deny_unknown_fields)]`、`ModelRequest` 15 变体、`CreateRun { body }`、`destination` 固定路径 |
| 前端屏 | `src/App.tsx:218/220/223`；`src/components/modeling/ModelPanel.tsx` 85 行 | s07→`ModelPanel`（仅回归工作台）、s08→`S08`、s09→`S09` |
| S08 / S09 只显示回归 | `src/screens/split-screens.test.ts:40`；`light-screens.test.ts:31-34` | pin 锁 `rows.filter(row => row.task === 'regression')` 与 `useState<'all' \| 'regression'>` |

### 0.4 源码 pin 全清单与授权边界

**A 组 · 本卡授权修改（仅限以下 5 条，逐条留痕，禁止删断言凑绿）**

| 文件:行 | 现被锁模式 | 本卡允许的改法 |
|---|---|---|
| `src/screens/split-screens.test.ts:40` | `rows.filter(row => row.task === 'regression')` | S08 需同时列出分类 run；改为放行两类并**保留原有回归断言语义**（如新增独立分类断言） |
| `src/screens/light-screens.test.ts:31` | `useState<'all' \| 'regression'>('regression')` | 筛选状态扩为 `'all' \| 'regression' \| 'classification'` |
| `light-screens.test.ts:32` | `runs.filter(row => row.task === 'regression')` | 同上，分类 run 可列出 |
| `light-screens.test.ts:33` | `task === 'regression' ? regressionRuns : runs` | 同上 |
| `light-screens.test.ts:34` | `doesNotMatch(ledger, /new Date\|Date.now\|Kappa/)` | S09 需显示真实 Kappa 列 → **仅从正则移除 `Kappa`**，`new Date` / `Date.now` 仍禁（时间列仍不渲染） |

**B 组 · 零改动（任何一条变红即停）**

- `src/components/modeling/api.test.ts:50-59`（`calibration_origin` / `fit_scope` / `calibration_provenance_present`、`InferencePanel` 三个字段回显、禁 `fetch|invoke|http`、禁 `scaler_params`）
- `src/components/modeling/registry.test.ts:53-60`（禁 `invoke|fetch`、「可审计不可反证」「正在计算标定…」「统计结果保留」「全局训练残差区间」「clippingMessage」「pixel_mean」「sample_prediction」）
- `src/screens/split-screens.test.ts:39/41-57`（`modeling.runs()`、`onOpen(row.id)`、`modeling.train(`、`onOpenResults(row.run_id)`、`<RegistryPanel`、`<InferencePanel`、禁把回归结果放回 ModelPanel、禁 `var(--brand`）
- `src/screens/light-screens.test.ts:20-30/38-55`（S02 禁 pid/port/useEffect/modeling.runs；App 的 dashboard 过滤与 onOpenRun；S09 表头、禁时间列、`row.id.slice(0,8)`、`modeling.run(selectedRun)`、泄漏预检 details、禁 `Promise.all(records.map`）
- `src/shell/skin-guards.test.ts:14-17`（`modeling-skin.css` 禁 `position:fixed|100vh|z-index`、`!important`、禁 `@media`、禁裸 `.model-panel` 选择器）
- `src/shell/screens.test.ts:9/21-22`（屏号序列与标题，含 s07/s08/s09）
- `src-python/tests/data/test_api.py:207-214` 的 openapi 断言**逻辑零改动**（只重生成快照文件）

> **纪律**：A 组只允许改上述 5 行的字面，其余断言、用例数量、既有源码字符串**一条不动**；B 组全保留。若需改 A 组之外的任何断言 → **即停上报**，由备卡方出修订版。

### 0.5 关键裁定（R1–R12，写死口径，不得自行改写）

| # | 裁定 |
|---|---|
| **R1 基线** | 只认 v2.7 需求 + v2.3 UI；`10月15日/` 归档（v2.6/v2.2）不作依据。v2.6 的 run manifest 5 字段与 v2.2 的 S08 指标口径均已被基线修订，引用一律按 §0.2 根目录行号。 |
| **R2 不展示示例数值** | v2.3 `:1939/:1947` 的 OA 94.5%、Kappa 0.921、782,500 像素、LVs 9、误分 43,200 等是 **mock 且 Kappa 待核对**，一律不进界面；S08/S09 只显示真实后端返回值，`null` 显示「不适用」。 |
| **R3 范围** | 本卡只做 **FR-C02 PLS-DA 分类训练 + 评估 + 展示**。FR-C03 经典分类器、FR-C04 波段选择（iPLS）、FR-C05 聚类、FR-C06~C10 全不做；阶段二的模型预标注、批量推理、实验台账与模型注册（v2.7 `:2954-2955`）不做。 |
| **R4 DDL 零改动** | `metric.name CHECK` 只有 `oa/kappa`（无 AA/F1/confusion），故：`metric` 表只落 **oa / kappa**（`scope` 用现成 `pixel` / `sample` 实现双报）；**AA、每类 F1、混淆矩阵、均值±标准差、阈值统计**统一写入 `model_artifact` kind=`confusion` 的 JSON 产物；**类别概率 / OOF 预测**写 kind=`predictions`。产物一律经 `storage.resolve_write` 守卫落本地根。**禁改 DDL、禁加列、禁重建表、禁扩 CHECK**（TASK-33 §7 即停 1/2/3、TASK-30 P0-4）。 |
| **R5 契约** | **复用** `POST /api/v1/models/runs`（`api/models.py:136`），把 `TrainBody.task`（`:50`）由 `Literal["regression"]` 扩为 `Literal["classification","regression"]`；**不新增端点**（TASK-33「引入新端点须显式授权」）。四处同步：Python `api/models.py:50`、TS `src/components/modeling/api.ts:5`、Rust `src-tauri/src/models.rs:25 CreateRun`（若 body 为 `Value` 透传则实测确认零改）、`src-python/spectrumagent/api/openapi.json`。**显式授权重生成 openapi 快照**并逐字节复核（`test_api.py:211-214`），其他 path/schema 不得变化。 |
| **R6 划分** | 强制 `group_by=sample_id` / `cv_strategy='group_kfold'`（FR-F03 v2.7 `:716`），**用户不可关闭**；沿用 `cv.py:8 plan_folds`（`:12-14` 分类已允许 group_kfold）。`-1 留白` 与 `-2 不确定` 不参与训练、不进指标分母（v2.3 `:1899`）。 |
| **R7 泄漏** | 训练前强制 `leak.py:9/33` 预检；近重复光谱余弦 > 0.999、样品跨侧、样品级重叠 → **阻断并回报告**（FR-F05 v2.7 `:718`），不静默放行。 |
| **R8 置信度与拒识** | FR-C02 的「类别概率与置信度 / 不确定」按：`confidence_threshold` 作为**显式入参**（`[0,1)`），**默认 0 = 不启用拒识**（不静默决定）；像素最大类别概率低于阈值标 `-2 不确定`，不强行归类、不进指标分母；类别概率随 OOF 预测落盘（R4）。**本卡不做逐像素置信度图 / 伪彩分类图**（v2.3 S08 无控件，且属阶段二）。 |
| **R9 潜变量** | LV 数支持「CV 最小」与「RMSE 拐点」**两个建议值 + 手动指定**，范围 1–20（v2.3 `:1884-1885`、v2.7 `:2003`）；**只给数值建议，不画 LV-RMSE 曲线**（TASK-08 §3 `:42` 挂账）。 |
| **R10 指标** | OA / AA / Kappa / 每类 F1 / 混淆矩阵（FR-F04 v2.7 `:717`），**像素级 + 样品级双报**、fold 均值 ± 标准差（v2.7 `:1990-1992/:2000`）；全部由 `metrics.py:42-74` 现有纯函数产出，**LLM 只编排不产数值**。 |
| **R11 注册与推理** | 本卡**不注册分类模型**（`registry.py:85` 只放行 regression）、不改 `coefficients` 键集、不做分类批量推理/预标注；`inference.py` 与 TASK-33 标定契约零改动。 |
| **R12 pin** | 只允许改 §0.4 A 组 5 行；B 组与既有测试零删改；新增用例另计，禁为凑总数删改既有测试（TASK-17 A6）。 |

---

## 1. 范围与明确不做

**本卡做**（四段，按依赖顺序）：A 后端分类训练与落库 → B 契约与 S07 双轨配置 → C S08 分类结果 + S09 台账 → D 验收。

**明确不做**（越界即停）：
- FR-C03 经典分类器、FR-C04 iPLS/CARS/SPA/UVE 波段选择、FR-C05 聚类、FR-C06~C10；
- 模型预标注 / 置信度门控 / 人工复核队列 / 批量推理（v2.7 `:2954-2955` 阶段二）；
- 伪彩分类图、ROC/PR、报告导出、时序与 ROI 趋势、超参搜索网格、多实验对比矩阵（v2.3 `:587/:593`）；
- 深度模型、LV-RMSE 曲线渲染、SPXY / 分层划分、batch 维度、模型注册命名与质检角色（TASK-08 §3 `:42`）；
- 任何 DDL 变更、新增 API 端点、改动 `inference.py` / 标定契约 / `preprocess_run.scaler_params`（TASK-30 §7 即停 4、TASK-33 §7）；
- 触碰工作区 14 个 `artifacts/step2/*` 与 `docs/AI自动标注路径分析.md`。

---

## 2. 四段交付

### A 段 · 后端分类训练与落库

1. 在 `modeling/run.py` 增加分类训练路径（可由 `POST /runs` 按 `task` 分派，或新增 `classify` 方法由现有 `create_run` 调用），**复用** `preflight`（`:40`）、`dataset.py:43` 分类数据集构建、`cv.py:8 plan_folds`、`leak.py:9/33` 预检；
2. 训练器：`PLSRegression` 对 one-hot 类别 Y 拟合 + argmax 判别（或等价 PLS-DA 实现，**实现前须在回报说明所选等价形式与概率口径**，禁静默换成别的算法）；输出每像素类别概率；
3. 按 R6/R7/R8/R9 执行分组 5-fold、`confidence_threshold` 拒识、LV 双建议；
4. 按 R4/R10 落库：`metric` 只写 oa/kappa（pixel/sample 双 scope）、`model_artifact` 写 `confusion` JSON 与 `predictions`、`training_run.status` 收口；产物写经 `storage.resolve_write`；
5. 复现：run 级种子、数据集/标注/配方版本、算子版本、超参入 `training_run` 与产物 manifest（v2.7 `:714/:2215`）；同种子重跑指标一致（NFR-04 `:919`）。

### B 段 · 契约同步 + S07 双轨配置

- Python `api/models.py:50`、TS `api.ts:5`、Rust `models.rs:25`（实测决定是否需改）、`openapi.json` 四处按 R5 同步；
- `ModelPanel.tsx` 增任务切换（PLS-DA 分类 / PLS 回归）与分类专属配置：分组 5-fold（固定，不可关闭）、LV 双建议 + 手动、`confidence_threshold`（默认 0 并显示说明）；
- 分类分支**不改**回归分支已有控件与文案（pin `split-screens.test.ts:53-57` 仍绿）；预检沿用 `POST /runs/preflight`（`PreflightBody.task:'classification'` 已存在）；
- S07 不照搬 `ds-v3 (240 立方体)`、`240 样品`、预估耗时等原型示例数值；样本量、类别数从真实标注/数据集读取后显示。

### C 段 · S08 分类结果 + S09 台账

- S08：按 `run.task` 分流；分类 run 显示真实 OA / AA / Kappa / 每类 F1 / 混淆矩阵（来自 `model_artifact` confusion JSON）、像素级与样品级双报、fold 均值 ± 标准差、**LV 两个建议值**、`confidence_threshold` 与不确定像素数；`null` 显示「不适用」；
- S09：筛选状态与列表按 §0.4 A 组放行 classification run；表头 Kappa 列显示**真实值**（`light-screens.test.ts:34` 仅移除 `Kappa` 禁词，仍禁 `new Date`/`Date.now`）；
- **不新增**时间列、ROC/PR、分类图、报告导出；S02「回归运行概览」与回归分支零变化；
- `modeling-skin.css` 新增样式须过 `skin-guards.test.ts:14-17`（禁 fixed/100vh/z-index/!important/@media/裸 `.model-panel`）。

### D 段 · 验收

按 §4 G1–G7 逐条贴取数命令与原文输出；需求方手测走查（S07 双轨 → 分类训练 → S08 真实指标 → S09 台账列出分类 run → 回归分支回归验证）。

---

## 3. 落库与数据流规格（速查）

| 数据 | 落点 | 依据 |
|---|---|---|
| `training_run` | task=`classification`、cv_strategy=`group_kfold`、seed、cube_ids / annotation_version_ids / preprocess_run_ids、status | `migrations.py:3-14` 已有 CHECK |
| `training_fold` | 每折 train/test groups、计数 | `:15-19` |
| `metric` | **仅** `oa` / `kappa`，`scope='pixel'` 与 `'sample'` 各一 | `:20-25` CHECK 限制（R4） |
| `model_artifact` kind=`confusion` | AA / 每类 F1 / 混淆矩阵 / 均值±std / 阈值统计 的 JSON | `:26-30`、`UNIQUE(run_id,kind)`（R4） |
| `model_artifact` kind=`predictions` | OOF 类别概率与预测标签 | 同上（R8） |
| `model_artifact` kind=`model` / `lv_sweep` | 仅当确有真实产物时写，禁占位 | 同上 |

> **写路径覆盖**：每条 NOT NULL 列在每个写入路径都要显式供值（id=uuid4、run_id、relative_path、sha256=产物实际哈希、created_at=服务端 UTC），禁靠 DEFAULT 兜底、禁手填落盘数值。

---

## 4. 验收门（每条带取数命令，禁自报数不带模式）

| 门 | 命令 / 断言 | 预期 |
|---|---|---|
| G1 | `node --test "src/**/*.test.ts"`（禁裸跑） | **271+新增 / 271+新增 pass / 0 fail**；A 组 5 条 pin 按授权改、B 组逐条绿、既有用例零删改；新增用例写明「什么情况下会红」 |
| G2 | `npx tsc --noEmit` + `npm run build` | 均 EXIT=0 |
| G3 | Python 分段跑（`.venv/Scripts/python.exe -m pytest backend/tests src-python/tests`，环境变量同条、C 盘空闲先查、被 hook 拦则分段） | 全绿，贴 **当段开工与终值** collected/pass 原文；`test_api.py:211-214` openapi 逐字节断言通过 |
| G4 | `cd src-tauri && cargo test`；`cargo clippy --all-targets -- -D warnings` | 全绿 / 零 error，组数以当段原文为准 |
| G5 | `git diff -- src-python/spectrumagent/api/openapi.json` | 仅 `TrainBody.task` schema 相关变化，其他 path/schema 逐字节不变；贴 diff 原文 |
| G6 | 需求方手测走查（截图） | S07 双轨切换 → 分类训练成功 → S08 指标/混淆矩阵为真实值且无 mock 示例数 → S09 列出分类 run 且 Kappa 真实 → 回归分支行为与改造前一致 → 阈值/LV 入口存在且默认不静默拒识 |
| G7 | 收工 `git status --short` 对照开工 15 项快照 | 仅本卡清单内文件为新增 M；14 噪声 + 1 docs 零变化、未提交；`git diff --cached --name-only` 提交时须为逐文件清单 |

---

## 5. 红线

1. **LLM 只编排不产数值**：所有指标、概率、混淆矩阵由后端算子计算；工具出参只准标量，8MiB forward 红线不破。
2. **源目录只读零改动**；产物写入/删除一律经 `storage.resolve_write` / `resolve_delete` / `rmtree`，三个可写根不变。
3. **DDL 零改动、不新增端点**；`inference.py` / 标定契约 / coefficients 键集 / `scaler_params` 零改动。
4. **不展示假数据与未实现项**：mock 数值、示例样本量、类别数、耗时、置信度图、ROC/PR、Kappa 历史表一律不进界面；`null` → 「不适用」。
5. **分组划分不可关闭**：`group_by=sample_id` 由平台强制推导；泄漏预检失败即阻断。
6. **NAS 路径 / 文件名 / 凭据不进 LLM 上下文与日志**；工具出参白名单、`agent/llm.py:136` 兜底不变。
7. **pin 纪律**：§0.4 A 组只改 5 行、B 组零改动；删改断言凑绿 → 即停。
8. **写路径覆盖 / 语义贯穿**：每个 NOT NULL 列显式供值；`task` 概念在 Python/TS/Rust/openapi/DDL/前端分流/测试断言中口径一致。
9. **保护文件禁触碰**：14 个 `artifacts/step2/*` + `docs/AI自动标注路径分析.md`；**逐文件提交，禁 `git add -A` / `git add .`**。
10. **行号与实物不符须在回报中显式说明，不得自行改写本卡。**

---

## 6. 即停条款

1. §0.2/§0.3 锚点漂移，或开工时工作区不是 15 项快照 → 停，上报；
2. 需要改 DDL / 加列 / 重建表 / 新增 API 端点 / 改 `inference.py` / 改标定契约 → 停；
3. 需要改 §0.4 A 组之外的任何 pin 或删除既有断言 → 停；
4. 分类训练需引入未在本卡写死的算法口径、概率定义或默认阈值 → 停，由备卡方裁定；
5. 需要触碰保护文件或改动第 6 个以上非清单文件 → 停；
6. 手测出现 mock 数值混入、回归分支退化、分组 CV 可被关闭 → 停。

---

## 7. 交付与提交顺序

1. 一次一段（A → B → C → D），每段独立提交并贴该段回归原文；
2. 每段开工按闸门①②③，锚点漂移即停上报，由备卡方统一校准；
3. 收口按 G1–G7 全绿后逐文件提交，提交信息建议 `feat(modeling): TASK-36 PLS-DA 分类训练与双轨展示`；
4. 回报格式沿用 TASK-23/24/35：改动文件清单、每条验收的取数命令与原文输出、未决项、遗留债；
5. **本卡不代发提示词、不 push**；发布动作（打包/冒烟/tag/Release/manifest/push）按项目流程由负责人执行，当前本地领先 219 笔未推送。

## 8. 遗留债（本卡不做，不在授权面内）

| # | 债 | 处置 |
|---|---|---|
| D1 | FR-C03 经典分类器、FR-C04 波段选择（iPLS/CARS/SPA/UVE）、FR-C05 聚类 | 各自另立正式卡；S07 原型 `:1889` 的 iPLS 入口本卡不展示 |
| D2 | 模型预标注 / 置信度门控 / 复核队列 / 批量推理 | v2.7 `:2954-2955` 阶段二，另立卡 |
| D3 | 伪彩分类图、ROC/PR、报告导出、超参搜索、多实验对比 | v2.3 `:587/:593` 阶段二/三 |
| D4 | LV-RMSE 曲线、SPXY / 分层划分、batch 维度、模型注册命名与质检角色 | TASK-08 §3/§6/§9/§10 挂账 |
| D5 | 分类模型注册与分类批量推理（`registry.py:85` 只放行 regression） | 需动训练/注册契约，另立卡（TASK-30 P0-4） |
| D6 | TASK-35 §8 的 D1「算子链 · v1」写死 legend 等 UI 挂账 | 让位本卡主线，继续挂账 |
| D7 | 工作区 15 项噪声 + 本地领先 219 笔未推送 | 非产品缺陷；由负责人定处置与过闸，备卡方不擅自处理 |
| D8 | 归档副本 `10月15日/`（v2.6/v2.2）与基线并存易误引 | 只在卡头标注，不改用户文件 |

---

## 9. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-11-07 18:04 | **初版（正式卡）**：按需求方「按 PLS-DA 出卡」指令起草。四路只读调研（需求 v2.7/v2.6 归档、UI v2.3/v2.2 归档、后端建模实现、前端与源码 pin）+ 备卡方 `grep -n` 复核关键行号。**基线锁定根目录 v2.7/v2.3**，排除用户 @ 的 `10月15日/` 归档；记录两处版本实质差异（v2.6 run manifest 5 字段 vs v2.7 10 字段；v2.2 S08 指标口径 vs v2.3 mock 待核对）。核心裁定 R1–R12：**DDL 零改动**（metric 只落 oa/kappa，AA/F1/混淆矩阵写 model_artifact confusion JSON）、**复用 POST /runs 不新增端点**（四处契约同步 + openapi 快照显式授权）、**group_by=sample_id 不可关闭**、**confidence_threshold 显式入参默认 0 不静默拒识**、**不照搬 S08 mock 数值**、**只给 LV 双建议数值不画图**、**不注册分类模型/不做批量推理**。§0.4 列全源码 pin 并**只授权修改 5 行**、其余零改动。四段交付 A/B/C/D + G1–G7 验收门。卡入库后交执行方，需求方手测与发布动作归负责人。 |
