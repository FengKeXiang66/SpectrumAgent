# TASK-25 · 数据集列表、回收站与统一写入守卫

> 目标：修掉「冷启动列表为空」「导入部分数据却铺出全库」，并交付「删除进回收站 → 30 天内可恢复 → 到期物理删」，同路径重新导入固定走「全新数据集、新建 id、从头标注」。同时把「所有文件写入/删除收口到一个出口」的地基打起来。
> 前置：TASK-24 已收口；**出卡时 HEAD = `b5d4c25` 仅为事实记录、不作闸门**（闸门①只查 `git status` 干净；本卡提交入库后 HEAD 前进不影响开工），`git status` 干净。
> 事实源：需求 v2.7（`E:/中达瑞和公司/光谱数据AI-Agent处理平台_需求分析与设计.html`）+ UI ui-v2.3（同目录 `光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.html`）+ 技术选型定稿 v1.1 + 开发手册。**用户 @ 的 `10月15日/` 两份是归档副本（v2.6 / ui-v2.2），不得作为基线。**
> **三道闸门**：① `git status` 干净；② 每段开工前复跑 §0.1 **该段当前基线**并贴原文（历史 1489 / 13 文件仅作溯源、**不作闸门**），**前端口径固定 `node --test "src/**/*.test.ts"` = 218，禁用裸跑 `node --test`**；③ 每段开工第一步 `grep -n` 复核本卡 §0.2 全部行号，漂移即停上报。
> **即停条款**：行号与实物不符须在回报中显式说明，不得自行改写本卡；卡内未写死的口径一律停下问，不许自造。

---

## 0. 事实底座（历史基线 18:00 实测；A 段后当前基线 21:55 实测）

### 0.1 基线（历史值保留 + 当前值；数量类全部实跑）

> **下表为出卡时（A 段开工前，HEAD `b5d4c25`）的历史基线，永久保留作事实记录，不作后续闸门**；执行方不得把 1489 / 13 文件 / 出卡时行号当成 B/C/D 段的开工判据。

| 项 | 实测值 | 取数命令 |
|---|---|---|
| HEAD / 工作区 | `b5d4c25` / 干净 | `git log -1 --oneline`；`git status --short`（空） |
| 前端（**源码口径**） | **218 / 218 pass，fail 0** | `node --test "src/**/*.test.ts"`（**禁用裸跑**，见下方防再犯记录） |
| Python | **collected 1489**（本次仅收集，未跑全量） | `PYTEST_DEBUG_TEMPROOT=<OS临时目录,先mkdir> .venv/Scripts/python.exe -m pytest backend/tests src-python/tests --collect-only -q` |
| Rust | `cargo test` **13 组 test result 全绿**；`cargo clippy --all-targets -- -D warnings` **零 error** | `cd src-tauri && cargo test`；`cargo clippy --all-targets -- -D warnings` |
| SQLite | **3.50.4** | `.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.sqlite_version)"` |
| 生产写盘出口 | **13 个文件** | `grep -rln -E "\.write_text\(|\.write_bytes\(|np\.save|savemat\(|shutil\.rmtree|\.unlink\(|\.mkdir\(|open_memmap" src-python/spectrumagent backend --include=*.py | grep -v __pycache__ | grep -v /tests/ | sort` |
| 关联 `cube_id` 的列定义 | **9 行 / 9 张表** | `grep -rn -E "cube_ids? +TEXT" src-python/spectrumagent/*/migrations.py`（实测恰 9 行，**旧命令 `cube_id|cube_ids` 会混入注释与 UNIQUE 行、数字对不上命令，已弃用**） |

> **Python collected 分组（本次实测，口径 = collected）**：`backend` 45；`src-python` 1444 = `agent` 470 + `annotation` 379 + `preprocess` 281 + `modeling` 145 + `data` 106 + 根测试文件 57 + `mat` 6。取数命令：`PYTEST_DEBUG_TEMPROOT=<临时目录> .venv/Scripts/python.exe -m pytest backend/tests src-python/tests --collect-only -q 2>&1 | grep "::" | sed 's/::.*//' | awk -F/ '{if($1=="backend") print "backend"; else if($3=="agent") print "src-python/agent"; else print "src-python/"$3}' | sort | uniq -c | sort -rn`。
> **回归跑法**：Python 全量被 safe-delete hook 拦，**分段跑**；具体分段由执行方按开工时 hook 的实际行为现场定、贴开工与终值两段原文，**本卡不再预写陈旧段数**（旧注记 `backend 45 + 非 agent 724 + agent 四文件 105 + agent 既有 104` = 978 ≠ 1489，系历史执行分段误抄为 collected 分布，已删除）。`-m` 插 cwd 进 sys.path 才使 `import backend` 成立；环境变量必须与命令同条。跑 pytest 前查 C 盘空闲，<3GB 先清 `pytest-tmp-*`。

> **防再犯记录（2026-11-04 18:45 复核修订）**：裸跑 `node --test` 实测 **222**，其中只有 **218** 属于源码（`src/` 下 30 个 `*.test.ts`）；多出的 4 个来自两个**归档快照**：`milestone13/evidence/finishing/before/projection.test.ts`（2 个）与 `artifacts/step3/checkpoint-3/frontend-state.test.mjs`（2 个），`218 + 2 + 2 = 222` 已逐个单跑复现；`.runtime/` 下隐藏目录的快照不进发现域。若沿用旧卡口径 `node --test "src/**/*.test.ts"` → 218，与裸跑 222 不符会「开工即停」；若用裸跑 → 两个无人维护的旧快照被当回归对象，且本卡执行时往 `milestone25/evidence/` 归档 before 快照会**让收工数自我膨胀**。故全卡前端口径统一为源码 glob。**这是「数字带出处」教训的新形态：数字实测过、命令也写了，但命令的发现域没人查过——实测面窄于主张面的第三种变体。**

**当前基线（A 段收口后，HEAD `9ad8268`，2026-11-04 21:55 备卡方实测）**

| 项 | 实测值 | 取数命令 |
|---|---|---|
| HEAD / 工作区 | `9ad8268` / 干净 | `git log -1 --oneline`；`git status --short`（空） |
| 前端（源码口径） | **218 / 218 pass，fail 0**（未变） | `node --test "src/**/*.test.ts"` |
| Python | **collected 1506**（A 段新增 `storage/guard.py` 及其测试；本次仅 collect，未跑全量） | 同 §0.1 历史表 `--collect-only -q` 命令 |
| Rust | 以 A 段已归档原文 `milestone25/evidence/A/Rust-after.txt` 与 `clippy-after.txt` 为准；**备卡方本轮复跑遇 `os error 5`（资源占用）未取得新数，不编数字**；B 段开工按闸门②复跑并贴当段原文 | `cd src-tauri && cargo test`；`cargo clippy --all-targets -- -D warnings` |
| 生产写盘出口 | **14 个文件** = 原 13 个（内容已全部改为走守卫）+ 新增 `src-python/spectrumagent/storage/guard.py` | 同 §0.1 历史表 `grep -rln` 命令 |
| 关联 `cube_id` 列定义 | **9 行**（DDL 未改，历史值仍成立） | `grep -rn -E "cube_ids? +TEXT" src-python/spectrumagent/*/migrations.py` |

> **后续基线规则（B/C/D 段，不得自行简化）**：
> 1. 历史 **1489 collected / 13 文件 / 出卡时行号** 是 A 段前的事实记录，**永久保留、仅供溯源，不作任何闸门**；不得用它判断 B/C/D 是否退化，也不得要求退回该数值。
> 2. B/C/D **每段开工前**复跑「该段开工时」的当前基线（node 源码 glob / Python collected / cargo / clippy）并贴原文；**终值与该段开工值比较**，不得把 1489 或 1506 当跨段固定阈值。
> 3. 段内新增用例另计（沿用 TASK-17 的 A6 裁定：「原有 N 项全过，新增用例另计 N+M，M≥1，fail=0」）；**禁止为凑总数删改现有测试**。
> 4. 每段开工前按闸门③ `grep -n` 复核 §0.2 全部锚点；源码一改即可能漂移，**漂移继续即停上报**，由备卡方统一校准，执行方不得自行改卡。
> 5. `1489 → 1506` 的增量来自 A 段新增测试（含 `storage/guard.py` 相关），是正常增长，不是回归退化。

### 0.2 行号锚点（全部 `grep -n` 直取；**2026-11-04 21:55 按 HEAD `9ad8268` 全量校准，A 段改造后**）

| 事实 | 路径:行 | 判定行要点 |
|---|---|---|
| 列表初始为空 | `src/App.tsx:54` | `useState<DatasetRecord[]>([])` |
| 引擎换代次清空列表 | `src/App.tsx:85` | `setRecords([])` 在 `[status.generation_id]` 的 useEffect 内 |
| 合并全库 | `src/components/datasets/DatasetPanel.tsx:48` | `mergeRecords(previous, result.all_datasets)` |
| 合并函数只加不删 | `src/components/datasets/types.ts:35` | `Map` set 后 `[...merged.values()]` |
| 全库字段声明 | `src/components/datasets/types.ts:15`；`src-python/spectrumagent/api/schemas.py:35` | `all_datasets: ...` |
| 已有断言依赖该字段 | `src/components/datasets/display_names.test.ts:14` | `G2 all_datasets refreshes a previously unique name...` |
| 表内唯一约束 | `src-python/spectrumagent/api/registry.py:120` | `CREATE TABLE ... UNIQUE(header_key,raw)`（原 `:118`） |
| 导入查重 | `src-python/spectrumagent/api/registry.py:156` | `SELECT id,payload ... WHERE header_key=? AND raw=?`（原 `:150`） |
| 导入插入 | `src-python/spectrumagent/api/registry.py:165` | `INSERT INTO dataset_registry (...)`（原 `:159`） |
| 全库记录生成 | `src-python/spectrumagent/api/registry.py:174` | `all_records = [...]`（原 `:168`） |
| 读时重新打开源文件 | `src-python/spectrumagent/api/registry.py:200` / `:204` | `def readable` / `read_header(Path(stored.header_path), ...)`；失败抛 `SOURCE_CHANGED`（原 `:194`/`:198`） |
| `payload` 整列重写 | `src-python/spectrumagent/api/registry.py:161` | `UPDATE dataset_registry SET payload=? WHERE id=?`（原 `:155`） |
| 前端 IPC 请求联合类型 | `src/components/datasets/api.ts:6` | `export type Request = ...` |
| 目录选择对话框 | `src/components/datasets/api.ts:35` | `open({ directory: true, multiple: true, filters: [...] })` |
| Rust 请求枚举 | `src-tauri/src/datasets_dev.rs:51` / `:52` | `#[serde(tag = "op", ..., deny_unknown_fields)]` / `pub enum DatasetRequest` |
| 外键开关 | `backend/database.py:10` | `PRAGMA foreign_keys=ON`（原 `:8`） |
| NAS 占位常量 | `backend/paths.py:8` / `:9` | `NAS_SOURCE_ROOT`/`NAS_OUTPUT_ROOT` = `None` |
| 数据根属性 | `backend/paths.py:40/44/48/52/56` | `database` / `snapshots` / `preprocessed` / `exports` / **`trash`（A 段新增）** |
| 会话上下文读写 | `src-python/spectrumagent/agent/state.py:166` / `:173` | `json.loads(...["context_json"])` / `UPDATE agent_session SET context_json=?` |
| 出域禁运兜底 | `src-python/spectrumagent/agent/llm.py:136` | `_DENY_TEXT`（注释声明 fallback, not primary boundary） |
| 删除前路径归属校验（可复用） | `src-python/spectrumagent/agent/mat.py:52` / `:88` / `:190` | `resolve().is_relative_to(self.paths.exports.resolve())` |
| 覆写已有的级联清理 | `src-python/spectrumagent/annotation/session.py:387-389` / `:405` | `DELETE FROM annotation / sample_spectrum / training_mat` + **`storage.rmtree(directory)`（A 段已收口，原 `shutil.rmtree` 在 `:406`）** |
| A 段守卫实际接口 | `src-python/spectrumagent/storage/guard.py:329/333/345` | `resolve_write` / `resolve_delete` / `rmtree`（另有 `:337 mkdir`、`:341 unlink`、`:349 replace`）；**B 段直接调用，不另造出口** |
| 父表重建迁移手法 | `src-python/spectrumagent/modeling/migrations.py:68-102` | `PRAGMA defer_foreign_keys` + `SAVEPOINT` + create-copy-drop-rename |
| 项目级 projection 配置 | `src-python/spectrumagent/annotation/projection_io.py:21` / `:73` / `:74` | `:21` `return paths.root / "projects"/.../"projection.json"`；`:73` `root = paths.exports.resolve()`；`:74` `folder = root / cube_id`（A 段未改，仍吻合） |

### 0.3 科祥 2026-11-04 拍板口径（五条，不得自行改写）

1. **删除一律进回收站**，软删 **30 天**内可恢复，回收站内占用仍计入本机磁盘占用（回到 UI 4.3 `:808` 原文，**不改文档**；此前「物理删除、不可恢复」的中间口径作废）。
2. **原始 ENVI 文件不真删**，源目录全程零改动；标注 JSON 等程序产物从工作区移走，**30 天到期才物理删**。
3. **重新导入固定走「作为全新数据集导入（新建 id、从头标注）」**；仍须人点确认框、默认选中该项，不静默决定。
4. **恢复 = 文件移回 + 清删除状态 + id 不变**，历史标注/版本/台账全在。
5. **列表 = 已登记的全部活跃数据**，冷启动自动加载；导入只追加本次选中批次，不再把全库铺出来。

### 0.4 复核结论：回收站实现方式改定（与早前讨论不同，口径不变）

早前建议「主表加 `deleted_at` + 部分唯一索引」。备卡复核后**改定方案 B**，理由写在卡里，执行方不得回退到方案 A：

- 探针实测：现有 `UNIQUE(header_key,raw)` 下，旧行仅标记软删后同路径 `INSERT` 仍报 `UNIQUE constraint failed`；改成 `CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL` 可行（软删行 + 新活跃行共存，第二条活跃行仍被拦）。
- 但方案 A 要**重建 `dataset_registry` 这张父表**（表内 UNIQUE 不能 ALTER 掉），它被 `annotation_draft` / `sample_target` / `inference_run` REFERENCES 且 `PRAGMA foreign_keys=ON`；且要给**所有**读查询加 `deleted_at IS NULL`，漏一处就把回收站数据串出来（语义贯穿风险）。
- **方案 B（本卡采用）**：新增独立 `recycle_bin` / `recycle_item` 表；删除时把主表行**连同关联子行**搬进回收站并从主表移出。好处：主表唯一约束不用动、不用重建父表、**所有现有读查询天然只看到活跃数据**、同路径重新导入直接 `INSERT` 成功。代价：删除/恢复要按外键顺序搬 §3.2 列出的全部关联表（**以该顺序清单为准，不另写表数**，避免与 §0.1「9 行 cube_id 列定义」混淆），顺序见 §3.2。
- 方案 A 的探针结论保留备查，**不选**。

---

## 1. 范围与明确不做

**本卡做**（四段，按依赖顺序）：A 统一写入出口与审计 → B 回收站删除/恢复链路 → C 列表与 S03 UI → D 验收。

**明确不做**（越界即停）：
- NAS 只读挂载、只读账号与凭据加密、连接自检与 fail-closed、NAS 目录树浏览、产物实际写入 NAS 输出根 + run manifest（FR-A12 全量）——**另立卡**。
- FR-A01 新格式（GeoTIFF/COG、HDF5/NetCDF、Specim、.mat、IrisCube）、S10 检索、分类双轨（PLS-DA）、E 域 L2–L4、J/K/L 三域、报告导出、深度模型、瓦片大图。
- **S03 两个路径字段本卡只做「选择 / 保存 / 显示」**：数据源（本机或 UNC）、产物输出根配置为可保存设置；**产物落盘位置不变**（仍 `paths.root` 下），不把产物写到 NAS 输出根。界面须明示该状态，不得做成假入口。

---

## 2. A 段 · 统一写入出口与审计（**已于 `9ad8268` 交付收口**）

### 2.1 `src-python/spectrumagent/storage/guard.py`

- 单一出口 `resolve_write(path, *, kind)` 与 `resolve_delete(path)`：路径 `resolve()` 归一 → 判是否落在**三个可写根**内 → 判是否落在任一数据源目录（含子目录）内 → 越界抛 `WRITE_TO_SOURCE_DENIED` 并写审计。
- 三个可写根（需求 8.1 / 开发手册 `:51` / 技术选型 v1.1 `:24`）：**本地数据根** `paths.root`（DB / 日志 / 握手 / 缓存，以及 `annotations`（快照）、`preprocessed`、`exports`、`models`、`inferences`、`projects`（项目级配置）、`trash` 等产物目录）、**产物输出根**（本卡为配置项，默认不启用）、**系统临时目录**。**目录名一律以 `backend/paths.py` 实测为准，禁止按属性名推断**（`AppPaths.snapshots` 的实际目录名是 `annotations`，见 `backend/paths.py:44-45`）。漏掉本地根或 temp 会拦掉程序自身数据库与日志。
- **`unlink` / `rmtree` / `rename` 同为写操作，一并收口**；`src-python/spectrumagent/agent/mat.py:52/88/190` 的 `is_relative_to` 校验模式继续保留作纵深校验。
- **A 段已完成**：§0.1 历史基线记录的 **13 个**生产写点已全部改为走守卫；同一 grep 现为 **14 个文件**（新增 `storage/guard.py` 本身）。**B 段新写点一律调用 `storage.resolve_write` / `resolve_delete` / `rmtree`，不得绕过守卫**。
- ALLOW / DENY **全量留痕**（不只记 DENY），对应 UI 6.4 #13「被拒写入尝试均完整留痕」。

### 2.2 审计表（append-only）

`write_audit(id, ts, action, target_path, decision, reason, deletion_id, actor)` 与 `deletion_audit(deletion_id, action, cube_id, summary_json, confirmed_by, created_at)`。
**写路径覆盖**：逐列写明每条 `NOT NULL` 在 INSERT 时由谁供值（`id`=uuid4、`ts`=服务端 UTC 时间、`action`=枚举常量、`target_path`=守卫入参、`decision`=ALLOW/DENY 常量、`reason`=结构化错误码或空串禁 NULL、`deletion_id`=删除批次或空串、`actor`=固定 `local`），**禁靠 DEFAULT 兜底**。审计表只允许 INSERT，不提供 UPDATE/DELETE 路径，并在测试里反证。

### 2.3 自检、守卫自举与启动顺序（复核补充裁定，禁止自行简化）

1. **审计写不得递归**：`write_audit` 的 INSERT 是写操作，但**不经过 `resolve_write`**，走独立内部通道直接写 `paths.root/db` 下的审计表；否则 `guard → audit → guard` 无限递归。独立通道仍须固定目标路径（不接受外部入参路径）并在测试中反证「审计写不触发第二次守卫判定」。
2. **启动顺序钉死**：`create_directories()` 建 `trash/`（其 `mkdir` 本身是写，属初始化，**先于自检且不经守卫**）→ 三个根自检 → 通过后才放行任何业务写任务。任一自检不通过 → 明确告警且拒绝开始写任务（fail-closed），不静默降级。
3. **DB 未就绪窗口**：`backend/logging_config.py`、`backend/handshake.py` 属启动早期写点，数据库可能尚未就绪。裁定：此时审计先写**有上限的内存环形缓冲**，DB 就绪后一次性刷入并标 `flushed_at`；缓冲溢出写 `AUDIT_BUFFER_OVERFLOW` 告警，**不静默丢弃、不无限增长**。刷库动作本身同样走独立通道。
4. 自检项：三个根可写、数据源目录不在可写根内、`paths.root/trash` 存在、审计表可写、环形缓冲可刷入。

---

## 3. B 段 · 回收站删除链路

### 3.1 数据模型

- `recycle_bin(deletion_id TEXT PRIMARY KEY, cube_id TEXT NOT NULL, header_key TEXT NOT NULL, raw INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, reason TEXT, restored_at TEXT, purged_at TEXT, manifest_sha256 TEXT NOT NULL)` —— `expires_at = created_at + 30 天`，服务端算，禁前端传。
- `recycle_item(deletion_id TEXT NOT NULL, seq INTEGER NOT NULL, table_name TEXT NOT NULL, row_json TEXT NOT NULL, file_src TEXT, file_dst TEXT, PRIMARY KEY(deletion_id, seq))` —— 存被搬走的每一行完整数据与文件 src→dst 映射；`file_src`/`file_dst` 为相对 `paths.root` 的 POSIX 路径，禁绝对路径、禁 `..`、禁反斜杠。
- `dataset_registry` **不改名、不重建、不加列**；`UNIQUE(header_key,raw)` 保持原样。

### 3.2 删除顺序（`PRAGMA foreign_keys=ON`，从叶到根，单事务）

先只读扫描生成**影响清单**（标注版本数、预处理/训练/推理 run 数、目录清单、体积），签发短时 `preview_token` 绑定清单哈希；确认框必须展示该清单。

事务内搬行顺序（`row_json` 逐行存进 `recycle_item`）：
`inference_artifact` → `inference_run` → `model_registry` → `metric` / `training_fold` / `model_artifact` → `training_run` → `sample_target` → `preprocess_artifact` → `preprocess_run` → `training_mat` → `annotation` / `sample_spectrum` → `annotation_version` → `annotation_draft` → `dataset_registry`。

- **`training_run.cube_ids` 是 JSON 数组文本**（`src-python/spectrumagent/modeling/migrations.py:4`），可能跨多个 cube：撞到跨 cube 的 run 一律 **fail-closed 拒绝单删**并提示，不许悄悄删掉别人的实验记录。
- 恢复按**反序插回**，id 全部复用原值；插回前若同 `header_key+raw` 已有活跃记录 → **拒绝恢复并留痕**（UI 写清：想恢复旧的，须先把新的也删进回收站，或等 30 天到期）。
- `agent_session.context_json`（`src-python/spectrumagent/agent/state.py:166/173`）若含旧 `cube_id`，删除时清理/标记该引用；验收须断言任意会话引用不指向已删 id。

### 3.3 文件回收区

- `backend/paths.py` 的 `trash` 属性已由 A 段落地（`:56`）= `root / "trash"`；本次目录 `trash/<deletion_id>/`，保留原相对结构。
- 删除用**同盘 move**（`Path.rename` / `storage.replace`），**不 unlink**；映射写进 `recycle_item.file_src/file_dst`。DB 事务提交成功后才算删除完成，失败则整体回滚（含文件移回）。
- 要移走（**2026-11-04 21:55 行号已按 A 段后校准，全部相对 `paths.root`**）：`annotations/<cube_id>/vN/`（`annotation.json`、`label_index.json`、`label_map.npz`、`spectra.npz`；`annotation/session.py:361` 用 `self.paths.snapshots / cube_id / f"v{version_no}"`，而 `AppPaths.snapshots` = `root/annotations`，`backend/paths.py:44-45`）、`exports/<cube_id>/`（labelme `.json` / `.meta.json` / `manifest.json`，`projection_io.py:73-74`）、`exports/<cube_id>/<version_id>/training_mat.mat`（`agent/mat.py:51`）、`preprocessed/<cube_id>/<run_id>/`（`preprocess/run.py:245`）、`models/<run_id>/`（`modeling/run.py:176`）、`inferences/<run_id>/`（`modeling/inference.py:225`）。`annotation_version.snapshot_ref` 是相对 `paths.snapshots` 的 POSIX 路径（`preprocess/run.py:165` 用 `paths.snapshots.joinpath` 消费），解析时必须以 `root/annotations` 为基，**不得当成 `root/snapshots`**。
- **绝不碰**：源目录任何内容；`projects/<project_id>/projection.json`（**项目级共用，位于 `paths.root/projects/`，不在 `exports/` 下**，`projection_io.py:20-21`）；`project` / `label_schema` / `label` / `preprocess_recipe*` / `project_recipe`（项目级资产）；`llm_call` 与 `agent_*` 审计出域记录（FR-I03 不可改，S11 原型写明不可删）。
- 按 `annotation_version.snapshot_ref` 精确解析目标，**禁一刀切 `rmtree(annotations/<cube_id>)`**。

### 3.4 到期物理删除

启动自检或定时触发：扫 `expires_at` 已过且未 `restored_at` 的批次 → 对 `trash/<deletion_id>/` 与 `recycle_item`/`recycle_bin` 行做物理删除 → 写 `PURGE` 审计。**该 `unlink`/`rmtree` 必须走 §2.1 守卫**；长任务执行中不得触发。

### 3.5 接口契约（三处同步 + 契约测试）

| 层 | 新增 |
|---|---|
| 后端 | `GET /api/v1/datasets/catalog`（活跃列表，**只返摘要字段**：id / display_name / shape / 波长范围 / 读模式 / source_path / 可用状态；带 limit+offset，**禁回传完整 `SpectrumDataSet`**，8MiB forward 红线）；`GET /api/v1/datasets/{id}/delete/preview`（影响清单 + preview_token）；`POST /api/v1/datasets/{id}/delete`（body `confirm: true` + `preview_token`）；`GET /api/v1/recycle`；`POST /api/v1/recycle/{deletion_id}/restore`（`confirm: true`）。新增 `src-python/spectrumagent/api/recycle.py` 并在 `src-python/spectrumagent/app.py` 注册。 |
| Tauri | `src-tauri/src/datasets_dev.rs:52` 的 `DatasetRequest` 增 `Catalog {limit,offset}` / `DeletePreview {id}` / `Delete {id,confirm,preview_token}` / `RecycleList {}` / `Restore {deletion_id,confirm}`；`destination` 与 `forward` 同步；`deny_unknown_fields` 的契约测试逐 op 覆盖。 |
| 前端 | `src/components/datasets/api.ts:6` 的 `Request` 与 `src/components/datasets/types.ts:26-33` 的 `DatasetTransport` 同步新增方法。 |

**重新导入分支（科祥拍板固定新建 id）**：`POST /api/v1/datasets/import` 增 `confirm_new: bool = False`。若 `recycle_bin` 存在同 `header_key+raw` 且未带 `confirm_new=true` → 返回结构化 `REIMPORT_CONFIRMATION_REQUIRED`（409），前端弹确认框（默认选中「作为全新数据集导入」、写清新 id + 旧那份留回收站 30 天 + 期内占双份空间）；带上后按 `registry.py:165` 正常 **INSERT 新 id**。`DatasetRequest::Import` 加 `#[serde(default)] confirm_new`。**禁止静默新建，也禁止静默复用旧 id。**

### 3.6 崩溃窗口与启动恢复（复核补充裁定）

§3.3 只写了事务失败回滚，未覆盖**进程死在「文件已 move、DB 事务未提交」之间**。裁定如下，执行方不得省：

- 启动时在 §2.3 自检通过之后、放行业务写任务之前，扫 `trash/<deletion_id>/` 与 `recycle_bin` 做对账，用 `recycle_bin.manifest_sha256` 校验目录清单。
- **有目录、无有效 `recycle_bin` 行**（或行已 `restored_at` / `purged_at`）→ 判定失败删除：若 `recycle_item` 有映射，按 `file_src`/`file_dst` 把文件**移回原位**、清理该 trash 目录，写 `ORPHAN_ROLLBACK` 审计；**无映射**（连 `recycle_item` 都未落库）→ 整目录移到 `trash/_orphan/<uuid>/` 并告警，**不自动删、不自动归位**，等人工处置，写 `ORPHAN_QUARANTINE` 审计。
- **有 `recycle_bin` 行、目录缺失** → 标记该批次 `INCOMPLETE`，**禁止恢复、禁止到期清理**，告警等人工。
- 上述所有 move 走 §2.1 守卫；对账完成前**拒绝该 cube 的导入 / 标注 / 训练 / 再删除**（fail-closed），避免半完成状态被继续写。
- 验收：注入「move 之后、commit 之前杀进程」的故障，重启后断言文件全部回原位或进隔离区、无半完成删除、审计两条动作可查。

---

## 4. C 段 · 列表与 S03 UI

1. **冷启动自动加载**：`src/App.tsx` 在 `status.phase === 'Ready'` 且 `generation_id` 稳定后调 `catalog()` 填 `records`；必须处理竞态（旧代次响应不得覆盖新代次）、失败提示、源文件失效标记（显示但标「源文件不可用」，**不静默跳过、不拿旧数据接着算**）。`src/App.tsx:85` 的清空保持不变，清空后必须重新拉。
2. **导入只合并本次批次**：`src/components/datasets/DatasetPanel.tsx:48` 改用 `result.datasets`；提示补「本次选中 N 个（新增 X / 已有 Y）」。`all_datasets` 字段**保留不删**——`src/components/datasets/display_names.test.ts:14` 的 G2 断言靠它刷新重名显示名；改造后须让 `catalog()` 接管该刷新，并保留 G2 断言全绿。
3. **删除/恢复 UI**：列表加「已删除」筛选、删除确认框（展示影响清单、写清 30 天可恢复与占用不释放）、恢复按钮（冲突时显示拒绝原因）。**删除不能由对话直接执行**（FR-D07 + UI `:1209`），对话只能「发起 → 人点确认框」。
4. **S11**：显示回收站占用体积、条目数、预计释放日期，以及出域禁运清单里的「NAS 路径与文件名」条目。
5. **S03 两字段**：数据源（本机 / UNC）与产物输出根，两个独立输入框 + 只读徽标 + 「浏览…」 + 「保存为该项目默认」；`?src=` / `?out=` 预填；S11 显示当前值。`smb://` 在 Windows `Path()` 打不开，**必须归一为 UNC `\\server\share\...`**（`api/registry.py` 的 `absolute()` 要求绝对路径并 `resolve()`）。**显示完整路径 ≠ 暴露给 LLM**：`safe_name()` 的「never expose directories」约定不变，工具出参只准标量、沿用 `src-python/spectrumagent/agent/llm.py:136` 兜底。格式清单按 ui-v2.3 `:1417` 分期，**不得**出现 `.mat` / IrisCube 的假入口。

---

## 5. D 段 · 验收（每条带取数命令，禁自报数不带模式）

**A 组 · 只读红线**：删除/恢复/到期清理前后，源目录文件清单 + 内容哈希 + mtime 完全一致；构造一次写向源目录与一次删向源目录的调用，均被拒且 `write_audit` 有 DENY 记录；`grep -rn "unlink\|rmtree" src-python/spectrumagent backend` 逐个确认已收口到守卫；反证「审计 INSERT 不再触发第二次守卫判定」（§2.3 第 1 条），以及启动顺序为「建 trash → 自检 → 放行写任务」（可注入自检失败，断言业务写被拒）。

**B 组 · 回收站**：删除后主表无该行、工作区原位置无 JSON、`trash/<deletion_id>/` 文件齐全；恢复后 id 不变且标注版本 / 预处理 run / 训练台账全在；有同路径活跃记录时恢复被拒并留痕；到期后物理删除且 `PURGE` 审计可查、审计行不可改；注入「move 之后、commit 之前杀进程」，重启后按 §3.6 断言无半完成删除、`ORPHAN_ROLLBACK` / `ORPHAN_QUARANTINE` 审计可查、对账完成前该 cube 的写任务被拒。

**C 组 · 列表与重新导入**：冷启动（含引擎换代次）列表自动出现；导入 3 个已登记文件时提示「新增 0 / 已有 3」且列表不被全库撑大；`display_names.test.ts:14` G2 仍绿；同路径重新导入必须新建 id、新数据集下查不到任何旧标注/版本/run；未带 `confirm_new` 时返回 409。

**D 组 · 全量回归**：`node --test "src/**/*.test.ts"` 全绿且 pass ≥ 218（贴**本段开工与终值**两段原文，**禁用裸跑 `node --test`，见 §0.1 防再犯记录**）；Python 按 §0.1 分段跑法全绿并贴 collected 与**本段开工基线**（历史 1489 / A 段后 1506 均为溯源值，**不作跨段固定阈值**；collected 口径，非 pass 口径）；`cargo test` 全绿、`cargo clippy --all-targets -- -D warnings` 零 error（组数以当段原文为准，禁写死 13 组）；`npm run build`（含 `tsc --noEmit`）。新增测试须写明「什么情况下会红」，空断言 0 条。

**孤儿检查**：按 `cube_id` / `version_id` / `run_id` 扫全部业务表，断言无指向已删除对象的行；`agent_session.context_json` 无已删 id。

---

## 6. 红线

1. 源目录（含子目录）零改动：**不写、不建、不改名、不删**；DENY 全量留痕。
2. 审计 / 出域记录只增不改；`llm_call` 与 `agent_*` 不进删除链路。
3. 回收站 30 天内**不物理删**；到期 `unlink` 仍走守卫。
4. 恢复 id 不变；重新导入固定新建 id，且必须人点确认框，不静默。
5. 对话不能直接执行删除；写操作在界面可定位、可撤销（回收站即撤销路径）。
6. NAS 路径 / 文件名 / 凭据不进 LLM 上下文、不进日志；工具出参只准标量。
7. `catalog` 只返摘要，不回灌完整 payload（8MiB forward 红线）。
8. 锁：SQLite WAL 单 writer，删除/恢复为短事务，事务内不跑长计算；**禁给 `DraftStore` 加锁**（锁序反转）。
9. `dataset_registry.payload` 重导入整列重写（`src-python/spectrumagent/api/registry.py:161` `UPDATE dataset_registry SET payload=? WHERE id=?`），**任何新增元数据不得塞 payload**，一律独立列/独立表。
10. **逐文件提交**，禁 `git add -A` / `git add .`；每段提交带对应测试。
11. **行号与实物不符须在回报中显式说明，不得自行改写本卡。**

---

## 7. 交付与提交顺序

按 A → B → C → D 四段推进，**一次一段、每段独立提交并贴该段回归原文**；**A 段已于 `9ad8268` 收口**。每段开工前复跑 §0.1 **该段当前基线**与 §0.2 行号：历史 1489 / 13 文件 / 出卡时行号仅作溯源、不作闸门；段内新增用例另计，禁为凑总数删改测试；数值一律带执行模式与取数命令。回报格式沿用 TASK-23/24：改动文件清单、每条验收的取数命令与原文输出、未决项、遗留债。

## 8. 遗留债（本卡发现，不在授权面内）

| # | 债 | 处置 |
|---|---|---|
| D1 | `all_datasets` 与 `catalog` 双份刷新显示名，语义有重叠 | 本卡保留字段并让 catalog 接管；后续另立卡统一，不在本卡删字段 |
| D2 | 跨 cube 的 `training_run.cube_ids` 无产品口径 | 本卡 fail-closed 拒绝单删；口径待拍板 |
| D3 | S03 输出根只存配置不落盘、NAS 只读挂载/凭据/产物写 NAS 未做 | 另立 FR-A12 卡；本卡界面须明示，不做假入口 |
| D4 | `agent_session.context_json` 无 schema 校验 | 本卡只清理本 cube 引用；整体 schema 化另立卡 |
| D5 | 出域记录页（S11）仍是空态、检索 S10 仍是占位 | 属阶段一断点，另立卡，不并入本卡 |
| D6 | C 盘可用空间 0 字节（2026-11-04 21:55 实测），Bash 输出与 Edit 备份受影响；pytest 临时目录实测仅 0 MB，清不出空间 | 本轮卡修订改走直接写 E 盘；**执行方需自行处理磁盘**（本机环境问题，不属产品缺陷），并在回报里注明所用跑法 |

---

## 9. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-11-04 18:06 | **初版（201 行）**：四段 A 守卫与审计 → B 回收站删除链路 → C 列表与 S03 UI → D 验收；§0 事实底座（行号锚点全 `grep -n` 直取）；§0.4 方案 B（独立回收站表）定稿并保留方案 A 探针备查；§0.3 五条拍板口径；明确不做清单与 5 条遗留债 |
| 2026-11-04 18:45 | **复核轮一（217 行）**：① 前端基线 222 → **218**、命令改 `node --test "src/**/*.test.ts"`、闸门②与 D 组同步、新增防再犯记录（222 = 218 + 2 + 2 的解剖）；② Python 分段注记按实测 collected 分布重写、删陈旧段数、改由执行方按 hook 现场定；③ `cube_id` 换精确取数命令 `cube_ids? +TEXT`；④ §0.4 措辞消歧为「以 §3.2 顺序清单为准」；⑤ §2.3 重写（审计独立通道不递归 / 启动顺序 / DB 未就绪环形缓冲）；⑥ 新增 §3.6 崩溃窗口三态对账；⑦ A/B/D 组验收补对应断言 |
| 2026-11-04 20:08 | **定稿（217 行 + 本节）**：§0.2 `projection_io.py:73` 实测 off-by-one，改为 `:73`/`:74` 双行并留痕；整表锚点复核无第二处漂移；卡头「前置 HEAD」标注为出卡时事实记录、不作闸门（防闸门自指变体）；补 §9 修订记录。本卡随后由备卡方**单文件提交入库，远程推送归负责人** |
| 2026-11-04 20:50 | **即停后路径裁定（228 行）**：执行方报 §3.3 两处路径与实物不符，实测裁定「先修卡再继续 B 段」：① `AppPaths.snapshots` 实际目录名 `annotations`（当时 `backend/paths.py:44-45`、`annotation/session.py:362`），全卡 `snapshots/...` 改为 `annotations/...`；② 项目级配置实为 `paths.root/projects/<project_id>/projection.json`（`projection_io.py:20-21`），**不在 `exports/` 下**，修正「绝不碰」清单与 §2.1 枚举；③ §0.2 的 `:21` 描述原本即正确，属卡内自相矛盾；④ 提示词两处同步替换。其余产物根实测无误。（**本行行号为 20:50 时点实测，A 段后以 §0.2 校准表为准**） |
| 2026-11-04 21:55 | **A 段后全量校准（即停后修订）**：执行方报 A 段 `9ad8268` 改造造成锚点漂移，备卡方独立实测后裁定「**修订卡后继续 B 段**」。① §0.2 全表按 HEAD `9ad8268` 重取：`registry.py` 118/150/159/168/194/198/155 → **120/156/165/174/200/204/161**、`database.py` 8 → **10**、`session.py` 388-390/406 → **387-389/405** 且删除出口改为 `storage.rmtree`、`paths.py` 新增 **:56 `trash`**、新增「A 段守卫实际接口」锚点行；② §3.3 三处（`session.py:362`→**361**、`modeling/run.py:175`→**176**、`modeling/inference.py:224`→**225**）、§3.5 `:159`→**165**、§6 红线 9 `:155`→**161** 同步；③ §0.1 保留历史基线（1489 / 13 文件）并新增「当前基线」（HEAD `9ad8268`、collected **1506**、写点 **14** 文件含新增 `storage/guard.py`、node 218/218）与**五条后续基线规则**；闸门②/§2.1/§5 D 组/§7 同步口径；④ §8 新增 D6（C 盘 0 字节的本机环境债，不属产品缺陷）。**裁定选 1，不拆段、不中断 B** |
