# TASK-31 输出根接线卡（正式卡）

> **状态**：**已解除排队、按届时 HEAD `c59dc1d` 重锚完成（2026-11-06 21:28），可执行**。TASK-30 已全部收口：卡 v1 `2a5f626` → v1.1 `51254bb` → v1.2 `bbfe1a4` → v1.3 `2f40deb`，八文件补丁 `c59dc1d`，**G1–G7 全部通过、最终验收完成**（收据 `.runtime/task30-v13-final-receipt.md`）；两卡同改 `preprocess/run.py` 的撞车面已消失，19:24 收回的并行放行不再适用，TASK-30 的 manifest 契约已成为本卡的既有基线。本轮**只做重锚**：订正被 TASK-30 平移的 `run.py` 行号、开工自检命令与现场 untracked 实况、状态与即停 2 的状态说明；**D1–D10 口径、§4 改动清单、§5 实现要点、G1–G8 判据、§7 即停 8 条、§8 挂账零改动**。修订历史：19:24 补两处缺口（D5 / D10）、19:34 补第三处缺口（D10 bootstrap 例外）；19:38 定稿排队。本卡不代发提示词；本轮入库按需求方 21:28「自动给我完成」书面授权，由起草方单文件提交。
> **卡型**：正式卡。契约改动（`ProjectPathResponse.output_enabled` 类型、`api/openapi.json` 快照重生成、产物相对路径基准）+ 多项新口径决策（真源归属、分层映射、多项目与全局守卫、fail-closed 边界、FR-A12 vs §6 裁定）。
> **事实源**：需求 v2.7 `artifacts/step3/requirements-v2.7.txt`；需求/UI 文档 `E:/中达瑞和公司/10月15日/光谱数据AI-Agent处理平台_需求分析与设计.html`（FR-A12 `—:523`、FR-A13 `—:524`）、`…_第一阶段UI设计与高保真原型.html`（S03 `—:1432`、验收项 13 `—:2517`）；`TASK-05-预处理.md:197`、`TASK-05:121`；归档版本禁引。
> **行号时效**：全部为 **HEAD `c59dc1d`（TASK-30 八文件补丁入库后）** 实读重锚。起草锚点 `fa7c4f1` 中仅 `preprocess/run.py` 因 TASK-30 新增 manifest / 入口计时 / 配方哈希查询而整体下移：`directory` `245→261`、`not_applicable` `341→358`、产物发布与登记 `345-352→378-390`、清理 `360/364→393/397`；其余文件（`backend/paths.py`、`backend/app.py`、`api/project_paths.py`、`api/preprocess.py`、`storage/guard.py`、`storage/recycle.py`、各测试与前端）行号实测未动。开工须逐条 grep §3，漂移即停；格式与键清单锚当前 HEAD，历史证据须标快照时间与提交。
> **承载裁定**：FR-A12 vs §6 的裁定**写在本卡一次**，导出卡按行号引用，不各裁一套。

## 1. 改什么（一句话）

把设置页里已是元数据、但恒不生效的 `output_root` 接成产物写入的唯一基准：启动时注入 `WriteGuard.roots` 走写白名单与审计，产物按 `<输出根>/<项目>/<数据集版本>/<run_id>/` 分层，下载端点与回收站映射同步切换；**不物化任何中间立方体、不改产物内容、不实现 NAS 专属语义**。

## 2. 定案口径（不重开）

| # | 口径 | 依据 |
|---|---|---|
| D1 | **FR-A12 vs §6 裁定（两卡共用）**：默认维持「中间产物只存参数不存数据」的成本取舍（`TASK-05:121`「禁全量物化」）；物化只走「**显式导出**」这一条被审计的动作路径，归**导出卡**。本卡只接输出根，不产出 `processed_cube`、不扩大产物集合、不改 manifest / 配方哈希语义 | 需求 FR-A12（`—:523`）要求中间立方体落输出根，§6 成本章节（需求 `—:1096/2852`）要求「只存参数不存数据」——两者矛盾由本裁定收口；`run.py:358` 的 `not_applicable` 保持原样 |
| D2 | **真源归属 = 输出根接管（迁移语义，禁双写）**：配置输出根后，产物唯一写入基准切到该根，本机 `preprocessed/` 不再写；**未配置 / 空串时回落现行 `<AppPaths.root>/preprocessed`**，保证既有测试零基线变化。`preprocess_artifact.relative_path` 仍是 POSIX 相对路径、DB 表结构零改动，只是基准随配置切换 | 双写会立第二真源（TASK-05 §2.3）；`test_project_paths.py:88-108` 与 `test_task25_acceptance.py:154-155` 在「PUT 后不生效」前提下才绿，回落语义正好保持其基线 |
| D3 | **分层映射（逐字）**：`<输出根>/<项目>/<数据集版本>/<run_id>/`；`<项目>` = `project_path_settings.project_id`（阶段一单项目 D8）；`<数据集版本>` = **`cube_id`**（`dataset_registry` 每行即一次不可变导入版本，FR-A06），**不是 `annotation_version_id`**；`<run_id>` = `preprocess_run.id`。现行 `<cube_id>/<run_id>/` 是未配置时的回落形态 | 需求 FR-A12 `—:523`、UI S03 `—:1432`；`run.py:261` 现行 `preprocessed / cube_id / identifier` |
| D4 | **多项目与全局 WriteGuard**：全局只有一个 `WriteGuard` 实例（`guard.py:257-280` 按 `paths.root` 注册），阶段一只绑**一个** `output_root`；`PUT` **只落库、重启生效**（与 `test_project_paths.py:111-131` 的重启读回口径一致），不做热更新；配置第二个项目且根不同 → 结构化拒绝 `OUTPUT_ROOT_CONFLICT`（409），不静默取第一个。空 `output_root` = 回落本机 | 避免全局守卫与多项目路径产生第二真源；「重启生效」同时让 `test_task25_acceptance.py:154` 写入不可达 UNC 后**进程内不触发绑定**，保留其既有绿 |
| D5 | **fail-closed 边界**：输出根不可达 / 自检失败时，**启动期绑定失败不阻断进程启动**——捕获异常 + 写 `OUTPUT_ROOT_UNAVAILABLE` 审计 + `guard.ready=False` + 后续业务写由 `_resolve:184-205` 统一拒绝，且 `GET /settings/projects/{id}/paths` 仍 200 可用；**异常处理只圈输出根绑定/探针，本机 `self.root` 与 `temp_root` 自检失败仍按现状抛穿 lifespan（致命）**，禁止一刀切吞掉。`output_enabled` = 有配置 **且** `guard.ready` 且输出根可用；绑定失败返回 `False` 但不删配置。**不实现** FR-A13① 连接可用性自检、③ 断线重试/断点续传、④ 凭据加密，挂账另卡；FR-A13⑤ 路径不进日志 / 工具 / LLM 上下文由 `test_project_paths.py:134-154` 守住 | `guard.py:158-160` 现行缺根即 `OSError('writable root missing')` → `:180` `DataError`；`backend/app.py:28` 的 lifespan 无 try/except；`test_project_paths.py:114` 配 `R:\future`（无此盘）后 `:130-131` `subprocess.run(check=True)` 真重启，异常贯穿会让子进程起不来而非「保持绿」 |
| D6 | **8 MiB 与读取**：`MAX_ARTIFACT_BYTES`（`api/preprocess.py:17`）是 IPC 响应保护，与产物物理位置无关，**本卡不改**；但下载端点 `root = runner.paths.preprocessed.resolve()`（`:153`）必须跟着产物基准切换，否则配置后 404 / `INVALID_ARTIFACT_PATH`。超大产物的流式通道归导出卡 | 用户口径检查单 ⑤；`api/preprocess.py:143-163` |
| D7 | **回收站映射**：`storage/recycle.py:224` 的 `_owned` 把 `preprocessed/<cube>/<run>` 三段相对路径写死、`:268` 按此拼删除清单；输出根分层后必须同步适配，**不得放宽校验或删断言凑绿**，删除仍走 `resolve_delete` 单一出口 | TASK-26 永久删除改造口径；`tests/storage/test_recycle.py:50,109` |
| D8 | **源数据零改动**：应用层写白名单由 `guard.roots`（`guard.py:79-80`）覆盖，写向源目录一律 DENY + 审计；**CIFS/NFS 只读挂载属部署层，不在本卡**（延续 `TASK-05:197` 的边界裁定，本卡只解除其中「输出根不接线」部分）。输出根不得落在任何已登记源目录内，PUT 时校验并拒绝 | FR-A11/A12、UI 验收项 13 `—:2517` |
| D9 | **契约与 openapi**：`ProjectPathResponse.output_enabled` 由 `Literal[False]` 改 `bool` → `app.openapi()` 变化 → **必须重生成 `src-python/spectrumagent/api/openapi.json`**（格式见 `test_api.py:213-215`：`json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"`，按 `os.linesep` 换行），并同步前端 `ProjectPathsView.ts:20`「未启用」文案与 `project-path-form.ts:7` 默认值 | `api/openapi.json:4477-4489` 现存 schema；`test_api.py:209-215` 是逐字节断言，不可删改 |
| D10 | **FR-A12「不存在时自动创建（创建动作需记录）」定案 = 实现，机制 = trash 同款 bootstrap 例外**：配置了合法但尚不存在的输出根时，在 `validate_bootstrap` 之后、`initialize` 之前，经 `normalize_path` + 源重叠校验后**受控 `mkdir(parents=True, exist_ok=True)`**（与 `paths.py:62-63` 建 trash 的「Explicit bootstrap exception」同款，注释标明）；`OUTPUT_ROOT_CREATE` / 失败事件经 `guard._audit` 进内存 buffer（`guard.py:115-128`），由 `attach_database:135-138` 在自检通过后 flush 落库 —— **「创建动作需记录」由既有机制承接，零新增守卫**。**「禁裸 mkdir」限缩为：业务 ready 后禁裸 `Path.mkdir`；bootstrap 例外仅限输出根创建且必须留审计事件**。创建失败（如 `R:\future` 盘符不存在）→ 转 D5 不可用分支；**auto-create 救不了盘符/共享不可达，两处分别钉**。未配置输出根时仍回落本机，不自动创建 `preprocessed`（`paths.py:59-65` 现状）；输出根不得落在已登记源目录内（PUT 已校验） | 需求 FR-A12 `—:523` 逐字含该句。**三把锁互斥实证**：① 白名单锁 `_resolve:188` 先于一切，`startup=True` 只豁免 ready（`:195-196`），此时 X 不在 `roots:78-80` → DENY；② 就绪锁 `_prepare:267-269` 先绑 X 仍 `ready=False`（构造器 `:72`），`resolve_write:207-208` 无 startup 形参，而 `self_check:159-160` 又要求 X 已存在；③ 先例锁 `paths.py:62-63` 的 trash 恰是裸 mkdir，被修订前即停 8 一刀切禁止。故 `resolve_write(kind='OUTPUT_ROOT_CREATE')` 路径不可执行 |

## 3. 现场锚点与影响面（HEAD `c59dc1d` 重锚，开工 grep，漂移即停）

| 文件:行 | 锚定内容 | 动作 |
|---|---|---|
| `backend/paths.py:7-9,21,47-49,59-65` | `NAS_OUTPUT_ROOT=None`、root=`%LOCALAPPDATA%/SpectrumAgent`、`preprocessed` property、`create_directories` 只建 6 个目录、末尾 `initialize(self)` 无参 | **改**：新增产物根解析 + 把 `output_root` 传进 `initialize`；bootstrap 例外插在 `validate_bootstrap` 之后 |
| `backend/paths.py:62-63` | trash 的「Explicit bootstrap exception」裸 mkdir 先例 | **D10 同款例外**：仅输出根创建，且必须留审计事件 |
| `backend/app.py:28` / `backend/__main__.py:29` | `paths.create_directories()` 在 lifespan / 启动入口，当前无异常围栏 | **改**：启动时读生效根、调用 D10 bootstrap 封装、D5 异常围栏（只圈输出根） |
| `api/project_paths.py:13-21,24-38,41-78` | `output_enabled: Literal[False]`、`normalize_path`（`smb://` → UNC）、建表、GET/PUT 只落库、`response()` 恒返回 False | **改**：类型、启用判定（D5）、PUT 冲突/重叠校验；**不建目录**（保持 D4 重启生效） |
| `api/settings.py:14-17` | `make_router(paths)` 内 `install_project_paths(router, paths)` 建表（早于 lifespan） | 不改（启动读表的前提） |
| `storage/guard.py:59-64,78-80,110-139,151-181,184-208,257-299,314-326` | 构造器 `ready=False`、`roots`、`_audit` buffer / `attach_database` flush、`self_check` 逐根探针、`_resolve` 白名单（startup 只豁免 ready）、`resolve_write` 无 startup 形参、`_prepare/initialize`、`_guard_for` | **改 `self_check` 输出根分支**（D5）+ **新增启动期 bootstrap 封装**（D10）；其余判定语义零改动，不复制第二套守卫 |
| `preprocess/run.py:261,378-390,393,397` | `directory = paths.preprocessed / cube_id / run_id`（`:261`）、npz / report 落盘与发布（`:378-380`）、`relative_to(paths.preprocessed)`（`:385`）、artifact / run 登记（`:387-388`）、`remove_directory(..., paths.preprocessed)`（`:393,397`） | **改**：产物根与分层；`relative_path` 仍 POSIX 相对；report 的 `outputs.artifacts`（TASK-30 已落地）由同一 `relative_to(root)` 派生，字段结构不变 |
| `api/preprocess.py:17,143-163` | 8 MiB 上限、下载端点 `root = runner.paths.preprocessed.resolve()` 与越界校验 | **改** root 基准；**不改** `MAX_ARTIFACT_BYTES` |
| `storage/recycle.py:218-230,262-272` | `_owned` 三段 `preprocessed/<cube>/<run>` 假设、删除清单拼接 | **改**：适配新层级，校验不放宽 |
| `tests/agent/test_project_paths.py:29,45,50` | 默认响应 `output_enabled=False`、空串往返、请求体带 `output_enabled` 应被拒（请求模型 `extra="forbid"`） | 适配默认响应；**请求体拒绝语义保持** |
| `tests/agent/test_project_paths.py:88-108` | 断言 `output_enabled is False`、输出目录不创建、`guard.output_root is None`、源文件哈希/mtime 不变 | **必红点**：改为「PUT 后进程内不绑定、重启后绑定」的适配断言，不得删断言凑绿 |
| `tests/agent/test_project_paths.py:111-131` | 配 `R:\future` 后 `check=True` 真重启、GET 读回全等 | **保持绿的前提**：启动期输出根绑定失败不阻断进程（D5）；不得靠删断言 |
| `tests/agent/test_project_paths.py:134-154` | 路径不进日志 / 工具 / LLM wire body | **保持绿**（FR-A13⑤ 红线） |
| `tests/agent/test_project_paths.py:157-163` | 鉴权 401 | 保持绿 |
| `tests/storage/test_task25_acceptance.py:154-155` | 配置不可达 UNC 后断言 `output_enabled is False` 并继续删除测试 | D4「重启生效」使其进程内不触发绑定 → 保持绿；`output_enabled` 断言按新语义适配 |
| `tests/preprocess/test_run.py:20-21,64,117,180,184,199,218` | `paths.preprocessed == tmp/SpectrumAgent/preprocessed` 及逐键产物断言 | 未配置回落 → 保持绿；新增配置生效用例另写 |
| `tests/preprocess/test_routes.py:185` | `paths.preprocessed/entry["relative_path"]` | 同上 |
| `tests/storage/test_recycle.py:50,109` | `preprocessed/<cube>/<run>` 相对路径 | 回落形态保持绿；新层级另增用例 |
| `tests/data/test_api.py:209-215` + `api/openapi.json:4477-4489` | openapi 逐字节快照 | **必须重生成快照**（D9），不得删改断言 |
| 需求 FR-A12 `—:523` | 「输出根可配置，不存在时自动创建（创建动作需记录）」 | **D10 承接**：bootstrap 例外创建 + buffer 审计；G2 加「根不存在」分支 |
| `src/components/settings/ProjectPathsView.ts:20` / `project-path-form.ts:7` / `project-paths.test.ts:11,84-87` | 「产物输出根（未启用）」、默认 `output_enabled:false`、PUT body 只含两字段 | **改**文案与默认值；输出根不可用时明示「输出根不可用、写入已暂停」（D5 全局拒写的用户可见解释，不设验收门）；PUT body 仍只含 `source_path/output_root` |

**影响面结论**：未配置输出根时所有既有 preprocess / recycle 用例走回落路径、零基线变化；配置生效后必红的断言集中在 `test_project_paths.py:88-108`、`test_task25_acceptance.py:155` 与 openapi 快照三处，均按「适配语义」处理，禁删改凑绿。`test_project_paths.py:111-131` 由 D5 保证「保持绿」。

**开工自检**：① `git status --short` 全文回报（执行日实况 = 14 项 `artifacts/step2/` 噪声 M + **1 个 untracked `docs/AI自动标注路径分析.md`**；TASK-30 卡与八文件补丁、本卡均已入库，不再出现在清单；以全文回报为准，§4 目标文件须为非 M）；② 后端基线（**仓库根执行、命令逐字、必须全路径**）：`./.venv/Scripts/python.exe -m pytest src-python/tests/agent/test_project_paths.py src-python/tests/storage/test_task25_acceptance.py src-python/tests/data/test_api.py::test_api_schema_snapshot src-python/tests/preprocess -q --no-header`，执行前在仓库内预建**本次全新**临时根 `.runtime/task31-exec-temproot`（`.gitignore:43` 已忽略，不进 git status），并**同时**设 `PYTEST_DEBUG_TEMPROOT` / `TMP` / `TEMP` 三个变量指向它——只设一个仍会触发系统 Temp 的 WinError 5，等价写法见 `.runtime/131-results/run_pytest.py:8-9`；**HEAD `c59dc1d` 实测参照 311 passed / 1 warning（80.80s，耗时软判据）**，须实测回报、不得沿用参照数字当已通过；③ 前端 `node --test "src/**/*.test.ts"`（双层 glob 逐字；`src/*/.test.ts` 实测 0 tests 且 exit 0 假绿、禁用），**实测参照 265 / 265 pass / 0 fail**；④ 回报 Python 与 Node 版本（参照 Python 3.12.13；node 版本差异不作判据、不触发即停）。唯一判据「既有用例不变红变少」；数字与参照不符时先说明差异来源，不得继续。

## 4. 改动清单（清单外零改动）

| 文件 | 动作 |
|---|---|
| `backend/paths.py` | 产物根解析（含回落）、bootstrap 例外位置、`create_directories` 把 `output_root` 传入 `initialize` |
| `backend/app.py` / `backend/__main__.py` | 启动时读生效根、调用 D10 bootstrap 封装（受控 mkdir + `_audit` buffer）、D5 异常围栏（只圈输出根） |
| `src-python/spectrumagent/api/project_paths.py` | `output_enabled` 类型、启用判定（D5）、多项目冲突与源目录重叠校验 |
| `src-python/spectrumagent/storage/guard.py` | `self_check` 输出根分支（`OUTPUT_ROOT_UNAVAILABLE` + `ready=False` 不抛）+ 启动期 bootstrap 封装（创建 + `_audit` 事件进 buffer）；其余根语义零改动 |
| `src-python/spectrumagent/preprocess/run.py` | 产物根与 `<项目>/<数据集版本>/<run_id>/` 分层、相对路径基准、清理边界 |
| `src-python/spectrumagent/api/preprocess.py` | 下载端点 root 基准切换 |
| `src-python/spectrumagent/storage/recycle.py` | `_owned` 与删除清单适配新层级 |
| `src-python/spectrumagent/api/openapi.json` | **重生成**（D9 格式） |
| `src/components/settings/ProjectPathsView.ts` / `project-path-form.ts` | 文案与默认值；输出根不可用明示「写入已暂停」 |
| `src-python/tests/agent/test_project_paths.py` | 适配断言 + 新增「配置生效 / 回落 / 冲突 / 重启注入 / 根不存在自动创建 / 不可达不阻断进程」用例 |
| `src-python/tests/storage/test_task25_acceptance.py` | 适配 `output_enabled` 断言 |
| `src-python/tests/preprocess/test_run.py` / `test_routes.py` | 新增配置生效用例（既有条目零改动） |
| `src-python/tests/storage/test_recycle.py` | 新增新层级删除映射用例 |
| `src/components/settings/project-paths.test.ts` | 默认值与文案适配，既有断言零改动 |
| 本卡 `TASK-31-输出根接线.md` | 新建（单文件提交） |
| 14 项 step2 噪声 + 1 个 untracked `docs/AI自动标注路径分析.md` | **禁触碰**，不恢复、不改写、不提交 |

## 5. 实现要点

1. **启动注入顺序**：`create_app` 阶段 `install_project_paths` 已建表（`api/settings.py:17`）→ lifespan `create_directories()` 内可 `connect_database(paths.database)` 读 `project_path_settings`；把非空、非重叠的 `output_root` 传给 `initialize(paths, output_root=...)`。`validate_bootstrap`(`:283-291`) 先创建 `output_root=None` 的守卫，`initialize` 走 `_prepare` 的 else 分支更新 `guard.output_root` 并置 `ready=False`，随后 `self_check()` 逐根探针 —— 机制现成，**不要复制第二套守卫**；D10 的 bootstrap 例外插在 `validate_bootstrap` 之后、`initialize` 之前（见第 7 条），不改动这条守卫更新链路。
2. **分层不改语义**：`preprocess_run.id` / `cube_id` 仍是 DB 主键与分组依据，分层只影响磁盘目录拼接；`relative_path` 相对的是**生效产物根**，写入 `preprocess_artifact` 前用 `target.relative_to(root)`，读回时按同一根解析。
3. **不可达即拒绝**：输出根探针失败 → 审计 + `ready=False`，业务写由 `_resolve` 拒绝；**禁止静默回落本地缓存或旧副本**（FR-A13②）。回落本机只在「未配置输出根」时发生，两者是不同条件，不得混用。
4. **路径隐私**：`output_root` / `source_path` 只进 DB 与设置页响应，**不得进日志、工具快照、LLM wire body**；新增用例复用 `test_project_paths.py:149-154` 的三标记断言。审计事件可含路径（`write_audit` 既有语义），不进应用日志 / LLM。
5. **openapi 重生成**：按 `test_api.py:213-215` 的字节格式落盘，先跑 `test_api_schema_snapshot` 再跑全量；禁止为了让绿而弱化该断言。
6. **启动期异常围栏（D5）**：在启动注入层（或 `self_check` 内按 `root == self.output_root` 分流）**只**对输出根绑定 / 探针失败做捕获 + `OUTPUT_ROOT_UNAVAILABLE` 审计 + `ready=False`；`self.root` / `temp_root` 失败继续抛 `STORAGE_SELF_CHECK_FAILED` 贯穿 lifespan。GET 返回 200 且配置读回完整，`output_enabled=False`；绝不因输出根不可用让子进程启动失败。
7. **auto-create 顺序（D10，bootstrap 例外）**：读配置 → `normalize_path` + 源重叠校验 → **受控 mkdir**（在 `storage/guard.py` 的启动期封装内持有 guard、调用 `_audit` 写 `OUTPUT_ROOT_CREATE` 事件进 buffer，业务层不直接访问私有方法）→ `initialize(paths, output_root=...)` 更新 roots 并 `self_check` 逐根探针 → `attach_database:135-138` flush buffer 落库。创建失败转第 6 条分支。**此阶段绝不能走 `storage.resolve_write`**（白名单 / 就绪双锁，见 D10 依据栏）；创建 / 失败事件都进 `write_audit`，路径明文不进日志与 LLM（第 4 条红线）。

## 6. 验收门（8 道，可执行、不自指）

| 门 | 命令 / 断言 | 预期 |
|---|---|---|
| G1 契约 | `pytest tests/data/test_api.py::test_api_schema_snapshot` | 重生成的 `openapi.json` 与 `app.openapi()` 全等且逐字节匹配；断言未被删改 |
| G2 生效分层 | 配置**已存在**与**不存在**两种本机临时输出根各重启一次 → 跑 preprocess run | 不存在的根被自动创建且审计含 `OUTPUT_ROOT_CREATE`；两种情况下产物都落在 `<输出根>/<项目>/<cube_id>/<run_id>/`，两件产物 sha256 与登记表一致，`relative_path` 为 POSIX 相对且可被下载端点取回 |
| G3 回落 | 清空 `output_root` → 跑同一 run | 路径与现行 `<root>/preprocessed/<cube>/<run>/` 逐字节一致；`test_run.py` / `test_routes.py` / `test_recycle.py` 既有用例全绿 |
| G4 白名单与零改动 | 构造写向源目录的调用 + 前后源目录清单/哈希/mtime 比对 | DENY + 审计留痕；源目录无新增子目录、无重命名、无删除（UI 验收 13） |
| G5 fail-closed | 配置不可达输出根（`R:\future` 级）后重启 | **子进程能启动、GET paths 200 且配置读回完整**（`test_project_paths.py:111-131` 绿）；业务写收到结构化 `DataError` 而非进程崩溃；审计有 `OUTPUT_ROOT_UNAVAILABLE`；**不静默回落本地**；`:134-154` 路径隐私断言全绿 |
| G6 多项目/重启 | 第二项目配置不同根 → 409；同配置重启后 GET 读回全等 | `OUTPUT_ROOT_CONFLICT`；`test_paths_survive_real_engine_process_restart` 绿 |
| G7 全量 | Python 七分区独立进程 + 每部全新临时根（每部按 §3 三变量写法预建，避免撞系统 Temp 权限）；`node --test "src/**/*.test.ts"` 双层 glob（禁裸跑） | 唯一判据「既有用例不变红变少」；必红断言均为**适配语义**而非删除 |
| G8 清单隔离 | 收工 `git status` 对照开工快照 | 仅 §4 清单文件为新增改动；14 项噪声与其余 untracked 零变化、未提交 |

## 7. 即停（8 条）

1. §3 锚点漂移，或开工时 §4 目标文件已为 M → 停，上报。
2. **TASK-30 未入库 / 未 G1–G7 收口即要求并行执行** → 停（19:24 收回并行放行的历史依据）。**该排队条件已于 21:28 解除**：TASK-30 卡 v1.3 `2f40deb` 与八文件补丁 `c59dc1d` 均已入库、G1–G7 全绿，撞车面消失。本条改为基线守卫：若开工发现 HEAD 不含 `c59dc1d`，或 `run.py` 中 TASK-30 的 manifest / 配方哈希契约缺失 → 停并上报，不得自行补造。
3. 物化 `processed_cube` / 改产物内容 / 改 TASK-30 的 manifest 契约 / 碰 `scaler_params`（P0-4）→ 均不在本卡，停。
4. 删改既有断言凑绿（尤其 `test_project_paths.py:101,108`、`test_task25_acceptance.py:155`、`test_api.py:212-215`）→ 停。
5. 本地 + 输出根双写、静默回落本地缓存、对多项目不同根取第一个而不报错 → 停。
6. 实现 NAS 挂载层 `ro`、凭据加密、断点续传，或把 `output_root` / `source_path` 送进日志 / 工具 / LLM 上下文 → 停。
7. 输出根落在已登记源目录内仍放行，或 `self_check` 失败后继续业务写 → 停。
8. **业务 ready 后**仍用裸 `Path.mkdir` 创建产物目录、bootstrap 例外扩大到输出根以外目录、创建/失败未留 `OUTPUT_ROOT_CREATE` / `OUTPUT_ROOT_UNAVAILABLE` 审计事件、或创建走 `storage.resolve_write` 触发白名单与就绪锁；异常围栏一刀切吞掉本机根自检失败；把输出根不可用做成进程崩溃或静默回落本地 → 停。

## 8. 边界与后续（挂账，不在本卡）

- **导出卡**（`processed_cube` 按需导出）：按 D1 裁定承接「显式导出」；须处理 `tests/preprocess/test_run.py:60` 的 artifact kind 集合断言（TASK-30 §8 已点名）、ENVI `.hdr/.img` 格式、超 8 MiB 流式下载、内存红线论证、导出物关联 run manifest。
- **P0-4**（`scaler_params` 唯一真源）另开卡，先裁定「两套标定来源」口径。
- **NAS 专属语义卡**：FR-A13① 连接可用性自检、③ 断线重试/断点续传、④ 凭据加密、只读挂载层与启动自检告警，均不在本卡。
- 卡内 `output_enabled` 为「配置已生效且自检通过」而非「NAS 已连通」；连通性语义归上述专卡，避免两个状态混写。
