# TASK-30 复现基线卡（P0-3 · 正式卡）

> **状态**：**v1.3（2026-11-06 21:20 需求方裁定 G3 判据归属）**。版本链：v1 `2a5f626`（108 行）→ v1.1 `51254bb`（开工自检临时根口径）→ v1.2 `bbfe1a4`（三处口径冲突裁定）→ **v1.3 本版**。**本卡不代发提示词、不代提交**；卡是执行期唯一口径，对话补充无效，变更另出修订版。**v1.3 只改**：卡头状态行、§6 G3 行及其表下「v1.3 G3 口径注」；D1–D8、§1、§3 全部锚点与开工自检、§4 清单、§5 全部实现要点、G1/G2/G4–G7、§7 即停 6 条、§8 **全部零改动**。v1.3 只澄清 G3 的判据归属与环境差异处理，**不新增、不放宽任何验收要求，不改任何功能口径**；`fa7c4f1` 重锚的代码锚点未漂移。修订须单文件提交入库后再发提示词。
> **卡型**：**正式卡**，不是轻量卡。理由：① 契约改动——`report.json` 顶层加键；② 两项新口径决策——配方内容哈希的算法与落点、manifest 字段集。轻量判据（无新口径决策）不满足。
> **事实源**：需求 v2.7 `artifacts/step3/requirements-v2.7.txt`；需求/UI 文档 `E:/中达瑞和公司/10月15日/光谱数据AI-Agent处理平台_需求分析与设计.html`、`…_第一阶段UI设计与高保真原型.html`；归档版本禁引。
> **行号时效**：以下全部为 **HEAD `fa7c4f1`（2026-11-06 00:43 +0800）** 实读重锚。开工仍须逐条 grep §3，漂移即停，禁止按偏移推算；引用历史证据文件须标注快照时间与提交（见 §2 D6）。
> **不承载**：FR-A12 vs §6「中间产物是否物化」的裁定属于**输出根卡**，本卡不写、不引用其行号；本卡只管 manifest / 配方内容哈希 / 指标注脚。P0-4（`scaler_params` 唯一真源）继续挂账，另开卡。

## 1. 改什么（一句话）

把「配方哈希 + 数据集哈希 + 算子版本三者固定即可完全还原输出」（UI `—:1802`）从界面标语落成可核验事实：给配方加内容哈希、给 run 产物补需求 6.8 的 manifest 字段、给每个指标卡补 `算子 · 版本 · run_id` 注脚（UI 验收项 3 / 7，`—:2508/2512`）。**零物化、零输出根改动、零业务口径变化**。

## 2. 定案口径（不重开）

| # | 口径 | 依据 |
|---|---|---|
| D1 | **哈希落点 = A：`preprocess_recipe_version` 侧的 DB 唯一真源**，实现方式用**一对一附表 `recipe_pipeline_hash`（`recipe_version_id` PK / `algorithm` / `sha256`）**；`report.json` 只写该值的**引用**，不重算、不另立算法 | 复现三要素中 `input_fingerprint` 已在 `preprocess_run`、算子版本在配方 JSON，配方哈希须可 SQL 查询/比对；report 是历史快照产物，不宜当唯一真源。**反对「仅 report 内」**：compare 引擎只查 DB（`compare.py:85`），且 11.6 加 `curves` 已证明键集会演进。**反对「双写」**：两处各算一套必然漂移，与「禁第二真源」（TASK-05 §2.3）冲突 |
| D2 | **规范化算法 `sha256/json-canonical-v1`**：取 `OperatorRegistry.parse_pipeline(pipeline).model_dump()`，再 `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`，UTF-8 编码后 sha256。算法标识随哈希一起落库、写进 manifest | `Step.params` 是 `dict[str, Any]`（`schema/__init__.py:70-73`），`model_dump()` **保留输入键序**；`RecipeStore._pipeline()`（`recipes.py:59-61`）只做 Pydantic 校验 + `json.dumps`，不规范化键序——这是键序事件的根因 |
| D3 | **保存时内容相等判定**：`add_version` 若新 pipeline 的规范化哈希等于该 recipe 最新版本哈希，结构化拒绝 `RECIPE_CONTENT_UNCHANGED`（400），不新增版本；`create`（新 code）不阻断，返回体带哈希。**v1.2**：D3 不弱化，既有并发用例 `test_recipes.py:95-100` 按语义适配为「不同内容并发追加」（见 §4 / G2） | 反面案例直接引 DB 实物：`plastic-snv-sg1` v1 `5d2925fd` 与 v2 `fde06616`（`2026-11-04`）两版 `steps` 解析后**相等**，仅 `window/polyorder` 键序不同 → 规范化后哈希必须相等，v2 本不该产生。该既有用例的真实意图是「并发下 version_no 唯一单调」，不是「允许同内容重复」，换输入即可两者兼得 |
| D4 | **既有行回填**：迁移时按 D2 计算并补齐 `preprocess_recipe_version` 全部既有行的哈希（含 builtin seed 行），**只补哈希、不改 `pipeline` 文本**（不违反版本不可变）；回填须幂等，`migrate()` 二次执行不产生重复行 | 现运行库 3 个 version、`preprocess_run=0`，回填不影响历史 run；`test_migrations.py:36-48` 断言二次 migrate 后所有表行完全不变 |
| D5 | **manifest 字段集**（顶层新增键，不动既有 20 键）：`env` / `seed` / **`duration_s`** / `operator` / `outputs.artifacts` / `reproducibility_assertion` / `recipe_pipeline_sha256` / `recipe_hash_alg`；`pipeline` 复用 `report.steps`，`inputs` 复用 `input_fingerprint` / `source_hashes` / 两个 version id，**不造第二份**。**v1.2**：`outputs.artifacts` 只列 `[{kind, relative_path}]`，**不内嵌任何 sha256**；sha256 唯一真源为 DB `preprocess_artifact.sha256`（`run.py:352` 在原子替换后实算），G4 从 DB 取 | 需求 6.8（`—:2445-2466`）的 `outputs.artifacts` 本就是文件名列表；`run.py:345-347` 先序列化 report、`:349-352` 才发布并算 sha、`:353-354` 才登记 DB，report 内嵌自身 sha 必然自引用循环。**v2.7 十项 run manifest `requirements-v2.7.txt:3478-3497`**（首项 `dataset_version_id`、末项 `duration_s`，`:3497` 总结句）：九项已有落点，唯 `duration_s` 未落 → 入口 `perf_counter()` 实测，**不用 `finished_at` 二次派生**；`run.py:331-341` 已有 19 键 + `:343` ranking |
| D6 | **出处 discipline**：`env.python/numpy/sklearn` 运行时实取，禁硬编码；`code_version` 取 git HEAD，取不到写 `null` + `not_applicable`；`image_digest` 单机桌面无容器 → `null` + 说明，**不得编造 sha256**；`seed` 顶层 `null` + `seed_sources` 列各 step 的 `params.random_state`（run 层无全局 seed，禁写 42）；`operator` = `null`、`actor` = `"local"`（J 域「单机单用户/进程即身份/不做登录」`requirements-v2.7.txt:409-412`；`storage/guard.py:114` 已用 `actor='local'`），**不得编造用户名** | 引用纪律：格式与键清单一律锚当前 HEAD；历史证据须标注快照时间与提交，本卡现场复核用到 `ica-report.json@2026-10-21 09:14 +0800`（早于 `5f5f2be 12:20 +0800` 约 3 小时，故为 19 键、无 `curves`） |
| D7 | **出域边界**：`outputs.artifacts` 用 POSIX 相对路径（`preprocess_artifact.relative_path` 原样），只落磁盘 report，**不进 LLM 上下文**；配方哈希与算法标识是可送出的元数据，绝对路径与原始谱不是 | FR-A13 / FR-L10；`workflows.py:132-141` 的 `run_provenance` 只透出 `step_i_op/version`，新字段若进工具返回须同守白名单 |
| D8 | **裁定不进本卡**：FR-A12 vs §6 的「默认只存参数、物化只走显式导出」由需求方定稿，但写在**输出根卡**里，本卡不承载、不引用其行号 | 需求方 2026-11-06 放行词 ③；避免后卡无法按行号引用 |

## 3. 现场锚点与影响面（HEAD `fa7c4f1` 重锚，开工 grep，漂移即停）

| 文件:行 | 锚定内容 | 动作 |
|---|---|---|
| `preprocess/run.py:331-341` | report 字面量 19 键（含 `curves`） | **改**：顶层追加 D5 字段 |
| `preprocess/run.py:343,345-346,354-355` | `ranking` 追加、npz 落盘、artifact/run DB 登记 | 不改（`outputs.artifacts` 只列 kind / relative_path；sha256 以登记表为真源、由 G4 从 DB 取） |
| `preprocess/recipes.py:16-36` | `input_fingerprint`，`:35` payload = `dataset_id\|源哈希\|标注版本\|像素数` | **不改其语义**（存量指纹禁静默变更） |
| `preprocess/recipes.py:59-61,63-92,94-108` | `_pipeline` / `create` / `add_version` / `get` / `list` | **改**：规范化、哈希、相等判定、返回体带哈希 |
| `preprocess/migrations.py:7-58,67-84` | `DDL` 常量与 seed | **改 `migrate()`**（独立表 + 幂等回填）；**`DDL` 常量零改动** |
| `preprocess/schema/__init__.py:70-73` | `Step.params: dict[str, Any]` | 不改（D2 依据） |
| `api/preprocess.py:81-163` | 全部端点**无 `response_model`**，返回 dict | 不改；新增字段进入响应 JSON 但**不改 `app.openapi()`** |
| `tests/data/test_api.py:209-215` | `test_api_schema_snapshot`：`openapi.json` 逐字节 + `app.openapi()` 全等 | 验收门 G1；若执行方新增 Pydantic 模型/端点 → openapi 必须重生成，否则红 |
| `tests/data/test_api.py:226/243` | `sqlite_master` 前后快照对比 | 新表在前后都存在 → 通过 |
| `tests/preprocess/test_migrations.py:23-33` | **`DDL.strip() == TASK-05 卡 SQL 代码块.strip()`** + `PRAGMA table_info` 快照（expected 内存库只执行卡内 DDL） | **本卡最硬约束**：改 `DDL` 常量或给原表加列都会红 → D1 选独立附表，且 `snapshot()` 的 `TABLES` 只含原 5 表 |
| `tests/preprocess/test_migrations.py:36-48,74-78` | 二次 migrate 行不变、空库缺 TASK-04 迁移时无 `preprocess_%` 表 | 回填幂等；新表名不含 `preprocess_` 前缀 |
| `tests/preprocess/test_recipes.py:95-100` | `test_concurrent_appends_get_unique_monotonic_versions`：4 线程对同一 recipe 连加 8 次相同 PIPELINE，断言 version 2–9 单调 | **v1.2 语义适配**（§4 / G2）：改为 8 个内容不同的 pipeline，保留 2–9 单调断言；属适配语义，非删断言凑绿 |
| `tests/preprocess/test_run.py:60` | **artifact kind 集合断言** `{item["kind"] for item in row["artifacts"]} == {"sample_spectra","report"}`，不是 report 逐键断言 | 本卡不加 artifact → 不影响；**导出卡加 `processed_cube` 时该行必红**，见 §8 |
| `tests/preprocess/test_run.py:159,179,332-336` | report 逐键断言，**无全键集合断言** | 顶层加键不影响 |
| `tests/preprocess/test_curves.py:75,82` | `set(curves) == {…}`、`set(item) == {…}` | **锁的是 `curves` 内部**；manifest 顶层加键，禁动 `curves` |
| `tests/preprocess/test_routes.py:84-85` | `report.json()["metrics"] == run["metrics"]` | 顶层 metrics 不变 → 通过 |
| `tests/preprocess/run_fixtures.py:44` | 原样读产物 JSON | 加键不影响 |
| `src/components/preprocess/types.ts:6,27-31` | `RecipeVersion` / `Report` **封闭 TS 结构** | **必须同步扩字段**，否则新字段在 UI 静默不可见（运行时不报错） |
| `src/components/preprocess/PreprocessPanel.tsx:15-22` | `MetricsView` | **改**：补注脚 |
| `src/components/preprocess/CompareChart.tsx:16-19` | 只读 `report.curves/steps/label_index` | 不改 |
| `src/components/preprocess/api.test.ts:36-40` | 假 report = `{curves:{classes:[]}}`，无键集合断言 | 加键不影响 |
| `src/components/preprocess/panel.test.ts:48-64` | 源码正则 pin：`fetch/invoke/http://`、`.updateRecipe/.deleteRecipe`、`ranking.sort|fisher 计算` 三条 `doesNotMatch` | 注脚只渲染已有字段字符串，禁引入网络调用与数值计算 |

**影响面结论**：report 顶层加键对后端既有断言零破坏（v1.2 唯一例外的语义适配已单列）；前端只有 `types.ts` 与 `MetricsView` 需要动；`openapi.json` 与 `TASK-05-预处理.md` 保持零字节改动。

**开工自检**：① `git status --short` 全文回报（现场为 14 项 `artifacts/step2/` 行尾噪声 M + 2 个 untracked：`TASK-31-输出根接线.md` 为已知排队卡、`docs/AI自动标注路径分析.md`；两者禁触碰；§4 目标文件须为非 M）；② 后端基线（**仓库根执行、命令逐字**）：`./.venv/Scripts/python.exe -m pytest src-python/tests/preprocess src-python/tests/data/test_api.py::test_api_schema_snapshot -q --no-header`，参照 `282 passed / 1 warning`；③ 前端基线 `node --test "src/**/*.test.ts"`（双层 glob；`src/*/.test.ts` 实测 0 tests 且 exit 0，假绿禁用），参照 `264 / 264 / 0`；④ 回报 Python 与 Node 版本（参照 Python 3.12.13，node 版本差异不作判据）。唯一判据「既有用例不变红变少」；数字与参照不符时先说明差异来源、不得继续。

**v1.1 临时根口径（20:42 需求方放行，仅作用于后端基线）**：执行前在仓库内预建**本次全新**的临时根 `E:\AI_Agent\.runtime\task30-opening-temproot`（`.gitignore:43` 已忽略 `.runtime/`，不进 `git status`），并**同时**把 `PYTEST_DEBUG_TEMPROOT` / `TMP` / `TEMP` 三个环境变量指向该目录；上面的 pytest 命令本体与其余参数逐字不变。三变量必须同设（实测只设 `PYTEST_DEBUG_TEMPROOT` 仍 33 setup errors，`TMP/TEMP` 指向系统 Temp 会再次触发 WinError 5）；等价写法见 `.runtime/131-results/run_pytest.py:8-9` 的项目既有惯例。**基线仍须实测回报 282 passed，不得沿用参照数字当已通过**；禁止清理或改 `%LOCALAPPDATA%\Temp` 的目录 / ACL。前端命令、四项自检其余内容、§6 G1–G7、§7 即停零改动。（v1.1 已执行并留证，该临时根已使用、不得再称全新。）

## 4. 改动清单（清单外零改动）

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/preprocess/recipes.py` | D2 规范化 + 哈希、D3 相等判定、`get/list` 返回体带哈希 |
| `src-python/spectrumagent/preprocess/migrations.py` | `migrate()` 内独立建 `recipe_pipeline_hash` + D4 幂等回填；`DDL` 常量不动 |
| `src-python/spectrumagent/preprocess/run.py` | report 顶层补 D5/D6 字段（哈希值从 DB 读，不重算；`duration_s` 入口计时实测；`outputs.artifacts` 只列 kind / relative_path） |
| `src/components/preprocess/types.ts` | `Report` / `RecipeVersion` 同步扩字段 |
| `src/components/preprocess/PreprocessPanel.tsx` | `MetricsView` 补 `算子 · 版本 · run_id` 注脚 |
| `src-python/tests/preprocess/test_recipes.py` | **v1.2 语义适配 `:95-100`**：8 个内容不同的 pipeline 并发追加，保留 version 2–9 单调断言；追加 D2/D3/D4 用例（键序、同内容被拒且 version 数不变、回填幂等） |
| `src-python/tests/preprocess/test_run.py` | 追加 manifest 出处用例（运行时版本实取、null 带说明、`outputs.artifacts` 不含 sha256 且 sha256 从 DB 取与文件实算一致、`duration_s` 实测非派生） |
| `src/components/preprocess/panel.test.ts` | 追加注脚 pin，既有断言零改动 |
| 本卡 `TASK-30-复现基线.md` | **修订**（单文件提交） |
| `api/openapi.json`、`TASK-05-预处理.md`、`backend/paths.py` | **零改动** |
| 其余既有测试断言 | **零改动**（唯一例外：`test_recipes.py:95-100` 的 v1.2 语义适配，见上） |
| 14 项 step2 噪声 + 2 个 untracked（TASK-31 排队卡、docs） | **禁触碰**，不恢复、不改写、不提交 |

## 5. 实现要点

1. **规范化只认语义**：`sort_keys=True` 递归排序 `params` 字典；Pydantic strict 模型已固定数值类型，不得先把 int 转 float 再算。算法标识 `"sha256/json-canonical-v1"` 与哈希同行落库，为将来算法升级留可判别依据。
2. **独立表而非 ALTER**：`recipe_pipeline_hash` 的 `CREATE TABLE IF NOT EXISTS` 放在 `migrate()` 内、不并入 `DDL` 常量；`test_migrations.py:25` 的逐字节断言与 `:32` 的 schema 快照因此零改动通过。若执行方想改走 `ALTER TABLE preprocess_recipe_version ADD COLUMN`，须同步修订 TASK-05 卡 SQL 代码块并让 expected 内存库执行同一迁移，**不得删改断言**——该路径属卡外变更，先停上报。
3. **回填顺序**：先跑原 DDL + seed，再建附表，再对 `SELECT id,pipeline FROM preprocess_recipe_version` 逐行 `INSERT OR IGNORE`；二次 `migrate()` 行集必须完全一致（`test_migrations.py:36-48`）。
4. **manifest 出处与自引用**：`env` 用 `sys.version` / `np.__version__` / `sklearn.__version__`；`code_version` 用 `git rev-parse --short HEAD`（取不到 → `null` + `not_applicable`）；**`duration_s` 在 `RunEngine.run()` 入口取 `started = perf_counter()`、report 组装前存 `perf_counter()-started`（秒、float、≥0），不从 `created_at` / `finished_at` 反推**；**`outputs.artifacts` 只列 `[{kind, relative_path}]`，不内嵌 sha256、不写 report 自身摘要**——sha256 唯一真源是 DB `preprocess_artifact.sha256`，落盘 / 登记顺序（`run.py:345-354`）保持现状，**禁两阶段回写**；`reproducibility_assertion` 逐字写「同 recipe_pipeline_sha256 + 同 input_fingerprint + 同算子版本重跑：`sample_spectra.npz` 的 SHA256 必须一致；`report.json` 含 run_id / duration_s 等动态字段，不承诺文件字节一致，仅核验 `recipe_pipeline_sha256` / `input_fingerprint` / `metrics` / `steps` 语义一致」。
5. **注脚只做展示**：读 `report.steps[*].op/version` 与 `report.run_id` 拼字符串，多算子逐个列；不新增网络调用、不计算任何指标、不写死示例数字。

## 6. 验收门（7 道，可执行、不自指）

| 门 | 命令 / 断言 | 预期 |
|---|---|---|
| G1 契约零漂移 | `pytest tests/data/test_api.py::test_api_schema_snapshot tests/preprocess/test_migrations.py` | 全绿；`openapi.json`、`TASK-05` 卡、`DDL` 常量零字节改动；逐字节断言与 schema 快照断言**未被删改** |
| G2 哈希确定性 | 新增用例：同一 pipeline 两种键序 → 同 sha256；`plastic-snv-sg1` v1/v2 规范化哈希相等；`add_version` 同内容返回 `RECIPE_CONTENT_UNCHANGED` 且 version 数不变；**不同内容并发追加仍产生 2–9 单调版本**（`test_recipes.py:95-100` 语义适配后） | 四条全绿 |
| G3 回填 | **执行方验收门（已完成）**：隔离临时库用 `tmp_path` 造 3 个 version 夹具，经 `migrate()` 回填后四条件——哈希非空、算法标识一致、`pipeline` 文本逐字节不变、二次 migrate 行集相同。**需求方事实依据（非执行方门）**：本机真实运行库只读核对（路径见 `backend/paths.py:18-21,40-41`；4 张 `preprocess*` 表、2 recipe / 3 version / 0 run、三个 version id 与 D3/D4 一致），**不迁移、不写入** | 隔离夹具四条件全绿即判 G3 通过；真实库 `recipe_pipeline_hash` 暂缺为**预期**（补丁未部署、应用未重启、`migrate()` 从未在真实库运行），**不作失败判据**；执行方会话看不到该库 / 表按环境差异记录，不即停、不自行建库或迁移，**不得把隔离夹具结果冒充真实库结果** |
| G4 manifest 出处 | env 与运行时实取相等（非硬编码）；`image_digest/seed/operator` 为 null 时各有 `not_applicable` 说明；**`outputs.artifacts` 只含 `{kind, relative_path}` 且不含 sha256；两件产物的 sha256 从 DB `preprocess_artifact` 取、与文件实算一致**；**`duration_s` ≥0、与独立 `perf_counter()` 计时同量级，且 report 中不存在由 `finished_at` 派生的第二份耗时** | 通过 |
| G5 注脚与前端 | `node --test "src/**/*.test.ts"` | 0 fail、既有用例不变红变少；指标卡下方注脚含 op / version / run_id |
| G6 复现非自指 | 同配方 + 同数据重跑两次：两次 `input_fingerprint` 相等、`sample_spectra.npz` sha256 相等、report 的 `recipe_pipeline_sha256` 相等；两次 report 的 `run_id` / `duration_s` 不同属正常，**report 文件整体 sha256 不作判据**；另核验两次 report 的 `metrics` / `steps` 语义一致 | **不得**以「report 里有该字段」或「report 字节一致」当验收依据 |
| G7 清单隔离 | 收工 `git status` 对照开工快照 | 仅 §4 清单文件为新增改动；14 M 噪声与 2 untracked 零变化、未提交 |

> **v1.3 G3 口径注（需求方 21:20 裁定）**：v1.2 的 G3 字面「真实运行库迁移后…」与「真实库一律只读、禁止 migrate」冲突；且执行方会话对 `%LOCALAPPDATA%` 存在访问隔离（此前 `%LOCALAPPDATA%\Temp` 已现 WinError 5、连 `preprocess*` 表都读不到），字面判据在执行方视角下永远无法关闭。故拆三层，互不替代：① **执行方验收门 = 隔离临时库三版本夹具四条件**（已由执行收据 `.runtime/task30-v12/receipt.md` 留证通过）；② **需求方事实依据 = 真实库只读核对**，仅作 D3/D4 的实物证据，不写入、不迁移；③ 环境差异只记录，不触发即停、不自行建库。真实运行库在整个流程中保持只读，**不得为让 G3 字面变绿执行迁移**；G3 关闭后按本卡其余门与全量纪律收口。

> Python 全量 pytest 另按既定纪律走七分区独立进程 + 每部全新临时根（safe-delete 钩子 50 次 unlink/回合预算），环境为 `.venv/Scripts/python.exe`；单模块命令不替代全量。

## 7. 即停（6 条）

1. §3 任一锚点漂移，或开工时 §4 目标文件已为 M → 停，上报。
2. 需要改 `TASK-05-预处理.md` / `api/openapi.json` / `DDL` 常量，或**删改任何既有断言**凑绿 → 停（**v1.2 明确许可的 `test_recipes.py:95-100` 语义适配除外**）。
3. 需要改 `input_fingerprint` 既有语义、或给既有 run 静默改指纹 → 停。
4. 需要动 `preprocess_run.scaler_params` 与 modeling 注册/推理契约（P0-4）、输出根、`processed_cube` 导出、FR-A12 vs §6 裁定 → 均不在本卡，停。
5. manifest 字段出现硬编码版本号、编造的 `image_digest` / `seed: 42` / 人名 operator / 由 `finished_at` 反推的 `duration_s`，或绝对路径进入 LLM 上下文 → 停。
6. 既有用例变红变少、或新增用例只断言「字段存在」而无数值/出处核验 → 停。

## 8. 边界与后续（挂账，不在本卡）

- 输出根接线卡（含 FR-A12 vs §6 裁定）→ 本卡入库、需求方发提示词后按序起草；随后 processed_cube 按需导出卡。两卡不同时在途。
- **导出卡已知影响点**：`tests/preprocess/test_run.py:60` 的 artifact kind 集合断言把 kind 锁死为两值；导出卡登记 `processed_cube` 后该断言**必红**，须在导出卡内同步适配断言以接纳新 kind（不得删断言 / 放宽判定凑绿），并在导出卡 §3 锚点表中显式列出。
- P0-4（`scaler_params` 唯一真源）另开卡，先裁定「两套标定来源」口径；冻结标定已闭环、非阻塞。
- `BUILTIN_PIPELINE` seed 行（`migrations.py:60-64`）的键序与前端 `compilePipeline` 不同是历史事实，本卡只回填哈希、**不改写 seed 文本**；若要统一规范化存储另立卡。
