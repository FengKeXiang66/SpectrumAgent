# TASK-25 B 段交付：回收站、catalog 与三层契约

执行模式：本机 Windows PowerShell；现有 .venv Python / SQLite、Node 源码 glob、Rust debug test / all-targets clippy、tsc --noEmit + Vite。未新增依赖。

提交空白校验：git diff --cached --check -- . ':(exclude)milestone25/evidence/B/*.txt'。终端原文 txt 的尾空白 / EOF 空行保留；代码、测试、报告与脚本纳入检查。暂存检查曾发现 before-anchor-commands.ps1 多一个 EOF 空行，仅移除该空行，不改命令或原始输出。

当前权威卡为 eb1b25b，A 段提交为 9ad8268。B 段开工时权威卡为 b6b247e（252 行），git status 干净，§0.2 全部 grep -n 锚点吻合，基线原文在 evidence/B/before-*。段内发现重导入边界即停，备卡方在 eb1b25b 只提交文档、用户明确解除即停并授权继续 B 与自行提交；执行方未改任务卡。未 push。

## 交付行为

- 新增 recycle_bin / recycle_item，主表未改名、未重建、未加列，UNIQUE(header_key,raw) 保持不变。新增独立 recycle_health 表记录 INCOMPLETE / 隔离状态，元数据未塞 payload。
- 删除预览只读扫描业务库：返回标注版本、预处理 / 训练 / 推理 run 数、目录和逻辑字节数。300 秒 HMAC token 绑定完整行与文件元数据清单；确认必须严格 true，清单变化或 token 失效会拒绝。
- 事务按卡列出的叶到根顺序逐行保存完整 row_json 后移出，恢复按反序插回并复用 id。跨 cube 的 training_run 拒绝单删；发现其他跨 cube 依赖也拒绝，避免搬走其他数据集的实验。pending / running 关联 run 拒删。
- 文件仅同盘 storage.replace：annotations 以 snapshot_ref 精确解析，exports/<cube> 包含 MAT，另处理登记 run 的 preprocessed / models / inferences。未登记快照目录与 projects/<project>/projection.json 保留。所有 mkdir / move / rmtree / manifest 写入均经过 A 段守卫；数据库打开沿用受守卫的 connect_database。
- 清单使用规范 POSIX 相对路径，拒绝绝对路径、..、反斜杠、驱动器号、越界、链接和重叠快照。manifest_sha256 校验规范 JSON 清单；文件清单字段为路径 / 类型 / 大小 / mtime_ns，不重读大型数组内容。源文件内容 SHA256 则在验收中单独逐文件比较。
- 文件移动或 SQLite commit 失败都补偿移回、整体回滚。独立 deletion_audit 记录 DELETE / DELETE_ROLLBACK / RESTORE / RESTORE_ROLLBACK / RESTORE_DENIED / PURGE / ORPHAN_ROLLBACK / ORPHAN_QUARANTINE；原 append-only 触发器继续生效。
- expires_at 严格由服务端 created_at + 30 天计算；到期前不清理产物。到期清理在启动对账后触发，只处理完整且未恢复的批次；长任务期间跳过，_orphan 永不自动清理。回收站体积含隔离目录实际文件逻辑字节数。
- 启动顺序为 A 段存储自检后迁移 / 对账，再放行业务。无有效 bin 行但有映射则移回并记 ORPHAN_ROLLBACK，无映射则整目录隔离并告警。缺目录、清单损坏、条目缺失均标 INCOMPLETE，禁止恢复 / 清理，相关 cube 与同路径导入被阻止，等待人工处置。
- 有效业务请求在完整 ASGI 响应期间持有任务租约，覆盖 Agent SSE 的实际执行期；删除 / 恢复 / 清理在独占维护窗口运行。未给 DraftStore 加锁，SQLite 写事务内没有数组计算或文件内容哈希。
- 删除时递归清理 agent_session.context_json 中本 cube、版本与 run 的引用，保留其他记忆；llm_call、agent_round / step / plan 等审计出域记录不进搬迁与删除链路。
- catalog 在同一 WAL 读取快照内分页，仅返回 id / display_name / shape / wavelength_range / raw / source_path / available。页上限 200，完整 payload 只从 SQLite 加载该页，不通过 HTTP 返回。源文件失效保留摘要并标 available=false；实际计算仍走 readable 的 SOURCE_CHANGED 校验。
- 按 eb1b25b 四象限：活跃记录优先，无论是否有同键回收记录、是否带 confirm_new，都正常返回已有 id / existing=true；无活跃且有未恢复回收记录时，缺确认返回 409 REIMPORT_CONFIRMATION_REQUIRED，确认后新建 id；两者皆无则首次新建。整批读取快照预检后，短写事务内整批复核，INSERT 前再次检查；确认后竞态出现活跃记录和 UNIQUE 冲突均结构化返回 REIMPORT_ACTIVE_EXISTS(409)，整批回滚，绝不静默复用或增加 id。同路径已有新活跃 id 时恢复拒绝，并记录 RESTORE_DENIED。
- 前端 newDatasetConfirmation 只根据 REIMPORT_CONFIRMATION_REQUIRED 返回“新建 id、从头标注、30 天、双份空间”文案；活跃结果与 REIMPORT_ACTIVE_EXISTS 不产生该确认文案。importMessage 的已有提示和新增 / 已有数字来自真实 summary。两函数已测试，实际界面接入属于 C 段，没有提前改 DatasetPanel。
- 后端五个新操作、Rust DatasetRequest / destination 与 deny_unknown_fields 测试、前端 Request / DatasetTransport 已同步。新增删除能力未注册为 Agent 工具；人点确认框与冷启动 UI 属 C 段。

## NOT NULL 供值来源

| 表 / 列 | INSERT 供值 |
|---|---|
| recycle_bin.deletion_id | 服务端 uuid4 |
| cube_id / header_key / raw | 正在删除的登记行，不从前端额外接收 |
| created_at / expires_at | 服务端 UTC clock / + timedelta(days=30) |
| manifest_sha256 | 规范 JSON 清单 SHA256 |
| reason / restored_at / purged_at | 初次明确写 NULL；恢复后服务端写 restored_at；清理物理移出 bin 行 |
| recycle_item.deletion_id / seq | 当前批次 / 按卡顺序枚举 |
| table_name / row_json | 固定表白名单 / 完整原行；文件映射项为 @file / {} |
| file_src / file_dst | 明确写 NULL 或经过校验的 root 相对 POSIX 路径 |
| recycle_health.deletion_id / cube_id / status | 当前批次 / 对账识别的 cube 或空串 / 固定错误状态 |
| deletion_audit 全列 | 原 A 段 deletion_event 显式供批次、动作、cube、summary_json、local、UTC 时间 |

## 新增用例失效条件（均有实际断言）

| 测试 / 参数组 | 什么情况下会红 |
|---|---|
| full_delete_restore | 任一关联表漏搬、外键悬空、资产被误动、未登记快照被带走、源哈希或 mtime 改变、恢复 id / 行内容丢失 |
| reimport_and_conflict | 未确认仍导入、复用旧 id、旧标注串到新 id、冲突恢复成功或缺 RESTORE_DENIED |
| reimport_quadrants ×8 | 活跃 × 回收站 × 确认八种组合中，id / existing / imported 或确认文案与四象限口径不符 |
| reimport_confirmed_race | 两个真实 Registry / SQLite 连接都预检无活跃后，未出现一成功新建 + 一结构化 409 |
| reimport_unique_is_structured | INSERT 的 UNIQUE 冲突漏成裸异常或发生静默复用 |
| reimport_batch_is_atomic | 混合首次导入 / 待确认项在整批拒绝前已写入部分行 |
| reimport_key_includes_raw | raw=True 的回收记录错误拦截 raw=False 的首次导入 |
| expiry_and_audit | 30 天前清理、到期未清理、PURGE 缺失、审计可 UPDATE / DELETE、源文件变化 |
| preview_binding ×4 | false / 篡改 / 过期 / 清单变更仍删除 |
| move_failure_rolls_back | 第二次 move 失败后行或文件未复原，或残留错误 bin |
| commit_failure_rolls_back | 真实 deferred FK 在 commit 拒绝后，文件或数据库未整体回滚 |
| restore_move_failure | 恢复第二次 move 失败后，回收文件、活跃表或 restored_at 残留半状态 |
| purge_waits_for_long_run | running run 尚存时发生到期物理清理 |
| multi_cube_fails_closed | 跨 cube JSON 数组 run 被单删 |
| incomplete_fail_closed ×3 | 缺目录 / 清单损坏 / 文件改变后仍可恢复或清理 |
| orphan_mapping_rollback | 有持久映射的孤立目录未移回或缺 ORPHAN_ROLLBACK |
| killed_move_is_quarantined | 父进程强制终止子进程后发生已提交半删除、产物丢失、无隔离 / 审计、相关 cube 仍可写 |
| busy_and_startup_gate | 对账前导入 / 读取 / 删除仍放行，或活动任务期间可维护 |
| stream_lease_until_body_end | 响应头已发但 SSE 未结束时租约被释放 |
| http_contract_and_catalog | API 路由抢占、返回完整 payload、缺分页、弱 bool / 额外参数可过、失效源被隐藏、身份头 / 认证链路失效 |
| mapping_paths_refused ×6 | 绝对路径、..、反斜杠、驱动器路径或非规范路径被接受 |
| 前端 api.test 新增 2 例 | IPC 方法 / 字段 / 确认分支不一致，或默认自动发送 confirm_new |
| 前端 importDecision.test 新增 3 例 | 活跃状态也显示“新建 id”确认、错误码误判、提示数字偏离 summary |
| Rust 新增 6 例 | 任一新 op 路径 / verb / body / 分页错误，额外字段可绕过，或 import 默认确认 |

## 环境处置与中间失败记录

开工 C 盘约 0.4 GiB，先清理本任务已结束的 A 段临时夹具；不足 3 GiB 后又核对 .runtime/task23/src-python-pytest.log，清理其明确记录的旧 regression 临时夹具。均在同一 PowerShell 内验证完整绝对目标位于 OS Temp、精确目录名和非 reparse point 后删除；未清理真实数据源。B 段基线结束后清理 t25bo。运行始终用系统临时目录的 PYTEST_DEBUG_TEMPROOT，未把 --basetemp 指向 E 盘。

一次新增测试复跑被 Free<3GB 的 throw 门禁拦下，未执行 pytest；清理已结束的基线临时夹具后才继续。最终全量的临时目录、时间、跑前 C 盘空闲字节与逐段退出码见 Python-final-command.txt；后附 environment.txt 是另一次明确时间的现场取数，不混为同一时点。

首轮新增测试为 7 failed / 15 errors：夹具 training_mat 占位符多一个、异常字符串不含 code（应断言 error.code）、外部失效注入删除了仍被 Windows 映射的二进制。已修正夹具与断言，失效注入改为移除头文件。第二轮 19 passed / 3 failed：深层 trash/MAT 路径超过 Windows 主机限制，夹具根改为较短的独立兄弟目录；生产守卫未放宽。两轮完整失败原文均归档。

两轮中间 src-python 全量在提交前复查期间主动停止：分别补齐读取快照 / 列表串行 / 外部 kill 注入，以及将清单收敛为元数据清单避免重读大型数组。中止原文保留，均不作通过或终值。随后完整批次为 1 failed / 1484 passed / 2 skipped，唯一失败是新增接口未同步 OpenAPI 快照；从组合应用重新生成快照，原快照逐字断言未改，定向 1 passed。该失败原文同样保留。t25b4 的旧口径完整批次为 1485 passed / 2 skipped，作为改口前记录保留，不作最新终值。

段内 §3.5 即停的合成原文为 reimport-active-ambiguity.txt：删除 A → 确认新 B → 再次导入活跃 B 先 409 再 existing=true，与新 id 提示冲突。备卡方 eb1b25b 裁定活跃优先；新增四象限、真实双连接竞态、UNIQUE、整批原子、raw 二元键与前端文案断言。定向 storage + 原 data API 为 53 passed；最终完整批次采用 t25b5。B-STOP.md 保留解除后的历史记录，不代表仍阻断。

## 回归结论与交付边界

开工 node 218 pass / 0 fail，终值 223 pass / 0 fail；Python 开工 1506 collected，终值 1544 collected，新增 38 例。开工实跑 backend 45 pass、src-python 1459 pass / 2 skip；终值 backend 45 pass、src-python 1497 pass / 2 skip。既有用例未删改，两个既有 skip 保留。Rust / clippy / build 原文附后。

C 的冷启动与竞态处理、导入批次 UI、删除 / 恢复确认框、S03 / S11，以及 D 的汇总验收尚未实施。本段没有改 App / DatasetPanel，all_datasets 与 G2 断言保留。真实 NAS 挂载与输出落盘、安装包不在 B 段验证面。

下一段开工前须由备卡方校准本段正常代码改动造成的锚点漂移；当前 grep 在 anchors-after-B.txt，执行方没有自行改卡。既定遗留债 D1–D6 保持，隔离 / INCOMPLETE 依卡等待人工处理；没有新增自动归位、提前清理或跨 cube 批量删除口径。

Rust 取数模式：完整 cargo test stdout，开工 13 段 test result、终值 13 段，均为原文实测；终值主单元测试 54 passed（开工 48）。clippy 终值 ^error 命中 0。

## 改动文件清单

- [src-python/spectrumagent/storage/recycle.py](E:/AI_Agent/src-python/spectrumagent/storage/recycle.py)
- [src-python/spectrumagent/api/recycle.py](E:/AI_Agent/src-python/spectrumagent/api/recycle.py)
- [src-python/spectrumagent/api/openapi.json](E:/AI_Agent/src-python/spectrumagent/api/openapi.json)
- [src-python/spectrumagent/api/registry.py](E:/AI_Agent/src-python/spectrumagent/api/registry.py)
- [src-python/spectrumagent/api/datasets.py](E:/AI_Agent/src-python/spectrumagent/api/datasets.py)
- [src-python/spectrumagent/api/schemas.py](E:/AI_Agent/src-python/spectrumagent/api/schemas.py)
- [src-python/spectrumagent/app.py](E:/AI_Agent/src-python/spectrumagent/app.py)
- [src-python/tests/storage/test_recycle.py](E:/AI_Agent/src-python/tests/storage/test_recycle.py)
- [src-tauri/src/datasets_dev.rs](E:/AI_Agent/src-tauri/src/datasets_dev.rs)
- [src/components/datasets/api.ts](E:/AI_Agent/src/components/datasets/api.ts)
- [src/components/datasets/types.ts](E:/AI_Agent/src/components/datasets/types.ts)
- [src/components/datasets/api.test.ts](E:/AI_Agent/src/components/datasets/api.test.ts)
- [src/components/datasets/importDecision.ts](E:/AI_Agent/src/components/datasets/importDecision.ts)
- [src/components/datasets/importDecision.test.ts](E:/AI_Agent/src/components/datasets/importDecision.test.ts)
- [milestone25/B-STOP.md](E:/AI_Agent/milestone25/B-STOP.md)
- [milestone25/REPORT-B.md](E:/AI_Agent/milestone25/REPORT-B.md)

证据文件：

- [anchor-drift.md](E:/AI_Agent/milestone25/evidence/B/anchor-drift.md)
- [anchors-after-B.txt](E:/AI_Agent/milestone25/evidence/B/anchors-after-B.txt)
- [before-anchor-commands.ps1](E:/AI_Agent/milestone25/evidence/B/before-anchor-commands.ps1)
- [before-anchors.txt](E:/AI_Agent/milestone25/evidence/B/before-anchors.txt)
- [before-build.txt](E:/AI_Agent/milestone25/evidence/B/before-build.txt)
- [before-clippy.txt](E:/AI_Agent/milestone25/evidence/B/before-clippy.txt)
- [before-cube-columns.txt](E:/AI_Agent/milestone25/evidence/B/before-cube-columns.txt)
- [before-node.txt](E:/AI_Agent/milestone25/evidence/B/before-node.txt)
- [before-Python-backend.txt](E:/AI_Agent/milestone25/evidence/B/before-Python-backend.txt)
- [before-Python-collected.txt](E:/AI_Agent/milestone25/evidence/B/before-Python-collected.txt)
- [before-Python-source.txt](E:/AI_Agent/milestone25/evidence/B/before-Python-source.txt)
- [before-Rust.txt](E:/AI_Agent/milestone25/evidence/B/before-Rust.txt)
- [before-sqlite.txt](E:/AI_Agent/milestone25/evidence/B/before-sqlite.txt)
- [before-workspace.txt](E:/AI_Agent/milestone25/evidence/B/before-workspace.txt)
- [before-writer-files.txt](E:/AI_Agent/milestone25/evidence/B/before-writer-files.txt)
- [build-after.txt](E:/AI_Agent/milestone25/evidence/B/build-after.txt)
- [clippy-after.txt](E:/AI_Agent/milestone25/evidence/B/clippy-after.txt)
- [environment.txt](E:/AI_Agent/milestone25/evidence/B/environment.txt)
- [guard-probe-after.txt](E:/AI_Agent/milestone25/evidence/B/guard-probe-after.txt)
- [implementation-index.txt](E:/AI_Agent/milestone25/evidence/B/implementation-index.txt)
- [lifecycle-probe.txt](E:/AI_Agent/milestone25/evidence/B/lifecycle-probe.txt)
- [lifecycle_probe.py](E:/AI_Agent/milestone25/evidence/B/lifecycle_probe.py)
- [node-after.txt](E:/AI_Agent/milestone25/evidence/B/node-after.txt)
- [openapi-diff-summary.txt](E:/AI_Agent/milestone25/evidence/B/openapi-diff-summary.txt)
- [Python-backend-after.txt](E:/AI_Agent/milestone25/evidence/B/Python-backend-after.txt)
- [Python-collected-after.txt](E:/AI_Agent/milestone25/evidence/B/Python-collected-after.txt)
- [Python-collected-pre-ruling.txt](E:/AI_Agent/milestone25/evidence/B/Python-collected-pre-ruling.txt)
- [Python-final-command.txt](E:/AI_Agent/milestone25/evidence/B/Python-final-command.txt)
- [Python-pre-ruling-command.txt](E:/AI_Agent/milestone25/evidence/B/Python-pre-ruling-command.txt)
- [Python-source-after.txt](E:/AI_Agent/milestone25/evidence/B/Python-source-after.txt)
- [Python-source-interrupted.txt](E:/AI_Agent/milestone25/evidence/B/Python-source-interrupted.txt)
- [Python-source-inventory-review-interrupted.txt](E:/AI_Agent/milestone25/evidence/B/Python-source-inventory-review-interrupted.txt)
- [Python-source-pre-ruling.txt](E:/AI_Agent/milestone25/evidence/B/Python-source-pre-ruling.txt)
- [Python-source-schema-failed.txt](E:/AI_Agent/milestone25/evidence/B/Python-source-schema-failed.txt)
- [recycle-acceptance.txt](E:/AI_Agent/milestone25/evidence/B/recycle-acceptance.txt)
- [recycle-first-failed.txt](E:/AI_Agent/milestone25/evidence/B/recycle-first-failed.txt)
- [recycle-second-failed.txt](E:/AI_Agent/milestone25/evidence/B/recycle-second-failed.txt)
- [recycle-writers.txt](E:/AI_Agent/milestone25/evidence/B/recycle-writers.txt)
- [reimport-active-after-ruling.txt](E:/AI_Agent/milestone25/evidence/B/reimport-active-after-ruling.txt)
- [reimport-active-ambiguity.txt](E:/AI_Agent/milestone25/evidence/B/reimport-active-ambiguity.txt)
- [reimport-ruling-targeted.txt](E:/AI_Agent/milestone25/evidence/B/reimport-ruling-targeted.txt)
- [reimport_probe.py](E:/AI_Agent/milestone25/evidence/B/reimport_probe.py)
- [Rust-after.txt](E:/AI_Agent/milestone25/evidence/B/Rust-after.txt)
- [schema-after.txt](E:/AI_Agent/milestone25/evidence/B/schema-after.txt)
- [schema-first-failed.txt](E:/AI_Agent/milestone25/evidence/B/schema-first-failed.txt)
- [writer-files-after.txt](E:/AI_Agent/milestone25/evidence/B/writer-files-after.txt)

## 开工 HEAD 与工作区

取数命令（本机实际执行；完整原文见 [before-workspace.txt](E:/AI_Agent/milestone25/evidence/B/before-workspace.txt)）：

```powershell
git log -1 --oneline; git status --short
```

```text
b6b247e docs(task25): A 段后全量校准锚点与基线规则（1506 / 14 文件）
```

## 开工全部锚点原文

取数命令（本机实际执行；完整原文见 [before-anchors.txt](E:/AI_Agent/milestone25/evidence/B/before-anchors.txt)）：

```powershell
& .runtime/task25/B-current-opening/anchor-commands.ps1
```

```text
src/App.tsx:54:  const [records, setRecords] = useState<DatasetRecord[]>([]);
src/App.tsx:60:  const [selected, setSelected] = useState<DatasetRecord | null>(null);
src/App.tsx:85:    setWorkspace({}); setRecords([]); setRefreshVersions({}); setNavigation(null); setWorkspaceName(''); setPreviewCandidates({});
src/components/datasets/DatasetPanel.tsx:48:        setRecords(previous => mergeRecords(previous, result.all_datasets));
src/components/datasets/types.ts:15:  all_datasets: DatasetRecord[];
src/components/datasets/types.ts:27:export type DatasetTransport = {
src/components/datasets/types.ts:35:export function mergeRecords(previous: DatasetRecord[], incoming: DatasetRecord[]): DatasetRecord[] {
src/components/datasets/types.ts:36:  const merged = new Map(previous.map(record => [record.id, record]));
src/components/datasets/types.ts:37:  for (const record of incoming) merged.set(record.id, record);
src/components/datasets/types.ts:38:  return [...merged.values()];
src-python/spectrumagent/api/schemas.py:35:    all_datasets: list[DatasetRecord]
src/components/datasets/display_names.test.ts:14:test('G2 all_datasets refreshes a previously unique name without duplicating records', () => {
src-python/spectrumagent/api/registry.py:120:            db.execute("CREATE TABLE IF NOT EXISTS dataset_registry (id TEXT PRIMARY KEY, header_key TEXT NOT NULL, raw INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(header_key,raw))")
src-python/spectrumagent/api/registry.py:156:                row = db.execute("SELECT id,payload FROM dataset_registry WHERE header_key=? AND raw=?", (key, int(raw))).fetchone()
src-python/spectrumagent/api/registry.py:165:                    db.execute("INSERT INTO dataset_registry (id,header_key,raw,payload,project_id) VALUES (?,?,?,?,?)", (identifier, key, int(raw), json.dumps(dataset.as_dict(), ensure_ascii=False), default_project_id(db)))
src-python/spectrumagent/api/registry.py:174:            all_records = [batch_records.get(identifier) or DatasetRecord(id=identifier,
src-python/spectrumagent/api/registry.py:200:    def readable(self, identifier, raw=None):
src-python/spectrumagent/api/registry.py:204:            current = read_header(Path(stored.header_path), Path(stored.data_path), raw=mode)
src/components/datasets/api.ts:6:export type Request = { op: 'import'; path: string; raw: boolean } | ({ op: 'preview'; id: string } & PreviewOptions)
src/components/datasets/api.ts:35:  const result = await open({ directory: true, multiple: true, filters: [{ name: 'Hyperspectral', extensions: ['hdr', 'img', 'raw', 'bin', 'json', 'txt'] }] });
src-tauri/src/datasets_dev.rs:51:#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
src-tauri/src/datasets_dev.rs:52:pub enum DatasetRequest {
backend/database.py:10:    connection.execute("PRAGMA foreign_keys=ON")
backend/paths.py:8:NAS_SOURCE_ROOT: Path | None = None
backend/paths.py:9:NAS_OUTPUT_ROOT: Path | None = None
backend/paths.py:40:    def database(self) -> Path:
backend/paths.py:44:    def snapshots(self) -> Path:
backend/paths.py:48:    def preprocessed(self) -> Path:
backend/paths.py:52:    def exports(self) -> Path:
src-python/spectrumagent/agent/state.py:166:        return json.loads(self.session(session_id)["context_json"])
src-python/spectrumagent/agent/state.py:173:            db.execute("UPDATE agent_session SET context_json=? WHERE id=?", (value, session_id))
src-python/spectrumagent/agent/llm.py:136:_DENY_TEXT = re.compile(r"[a-z]:|\\|/[^\s/]+|\.(?:img|hdr|mat)\b|\blabel_map\b", re.I)
src-python/spectrumagent/agent/mat.py:52:                if not path.resolve().is_relative_to(self.paths.exports.resolve()):
src-python/spectrumagent/agent/mat.py:88:        if relative.is_absolute() or ".." in relative.parts or "\\" in row["relative_path"] or ":" in row["relative_path"] or not path.resolve().is_relative_to(self.paths.exports.resolve()):
src-python/spectrumagent/agent/mat.py:190:            if not temporary.resolve().is_relative_to(self.paths.exports.resolve()):
src-python/spectrumagent/annotation/session.py:387:                        db.execute("DELETE FROM annotation WHERE version_id=?", (version_id,))
src-python/spectrumagent/annotation/session.py:388:                        db.execute("DELETE FROM sample_spectrum WHERE version_id=?", (version_id,))
src-python/spectrumagent/annotation/session.py:389:                        db.execute("DELETE FROM training_mat WHERE annotation_version_id=?", (version_id,))
src-python/spectrumagent/annotation/session.py:405:                    storage.rmtree(directory)
src-python/spectrumagent/modeling/migrations.py:68:    deferred = db.execute("PRAGMA defer_foreign_keys").fetchone()[0]
src-python/spectrumagent/modeling/migrations.py:69:    db.execute("SAVEPOINT modeling_132")
src-python/spectrumagent/modeling/migrations.py:81:                db.execute(f"INSERT INTO {name}_132 ({fields}) SELECT {fields} FROM {name}")
src-python/spectrumagent/modeling/migrations.py:82:            db.execute("PRAGMA defer_foreign_keys=ON")
src-python/spectrumagent/modeling/migrations.py:84:                db.execute(f"DROP TABLE {name}")
src-python/spectrumagent/modeling/migrations.py:86:                db.execute(f"ALTER TABLE {name}_132 RENAME TO {name}")
src-python/spectrumagent/modeling/migrations.py:97:            db.execute("PRAGMA defer_foreign_keys=ON")
src-python/spectrumagent/modeling/migrations.py:98:        db.execute("RELEASE modeling_132")
src-python/spectrumagent/modeling/migrations.py:101:        db.execute("RELEASE modeling_132")
src-python/spectrumagent/modeling/migrations.py:102:        db.execute(f"PRAGMA defer_foreign_keys={int(deferred)}")
src-python/spectrumagent/annotation/projection_io.py:21:    return paths.root / "projects" / str(UUID(str(project_id))) / "projection.json"
src-python/spectrumagent/annotation/projection_io.py:73:    root = paths.exports.resolve()
src-python/spectrumagent/annotation/projection_io.py:74:    folder = root / cube_id
src-python/spectrumagent/api/registry.py:161:                        db.execute("UPDATE dataset_registry SET payload=? WHERE id=?", (json.dumps(stored.as_dict(), ensure_ascii=False), row[0]))
backend/paths.py:56:    def trash(self) -> Path:
src-python/spectrumagent/storage/guard.py:329:def resolve_write(path, *, kind):
src-python/spectrumagent/storage/guard.py:333:def resolve_delete(path):
src-python/spectrumagent/storage/guard.py:337:def mkdir(path, *, parents=False, exist_ok=False):
src-python/spectrumagent/storage/guard.py:341:def unlink(path, *, missing_ok=False):
src-python/spectrumagent/storage/guard.py:345:def rmtree(path):
src-python/spectrumagent/storage/guard.py:349:def replace(source, destination):
```

## 开工 node 原文

取数命令（本机实际执行；完整原文见 [before-node.txt](E:/AI_Agent/milestone25/evidence/B/before-node.txt)）：

```powershell
node --test "src/**/*.test.ts"
```

```text
✔ block clicks retain the legacy geometry and omit label_id for erase and uncertain (2.4405ms)
✔ IPC superpixels: exact Rust variant, one command, no arbitrary route (0.4754ms)
✔ IPC diffuse: exact Rust variant, one command, no arbitrary route (0.3435ms)
✔ IPC regions: exact Rust variant, one command, no arbitrary route (0.2209ms)
✔ IPC undo: exact Rust variant, one command, no arbitrary route (0.2369ms)
✔ IPC working: exact Rust variant, one command, no arbitrary route (0.239ms)
✔ IPC validate: exact Rust variant, one command, no arbitrary route (0.214ms)
✔ IPC save: exact Rust variant, one command, no arbitrary route (0.2606ms)
✔ IPC versions: exact Rust variant, one command, no arbitrary route (0.2152ms)
✔ IPC version_overlay: exact Rust variant, one command, no arbitrary route (0.3139ms)
✔ IPC projects: exact Rust variant, one command, no arbitrary route (0.2955ms)
✔ IPC labels: exact Rust variant, one command, no arbitrary route (0.1671ms)
✔ IPC add_label: exact Rust variant, one command, no arbitrary route (0.2116ms)
✔ IPC catalog: exact Rust variant, one command, no arbitrary route (0.1829ms)
✔ optional defaults are left to Python; all prompt and geometry forms retain [line,sample] (0.4727ms)
✔ all three structured label bodies match Python and carry the working project id (0.2964ms)
✔ local estimates and display state cannot enter request projections (0.8046ms)
✔ structured errors keep code, field messages and context; client never swallows rejection (1.2756ms)
✔ RGB id decoding retains ids above 255 and verifies every block count (15.103ms)
✔ hitTest is local and rejects out-of-image and fractional coordinates (0.3769ms)
✔ 3px Euclidean boundary is inclusive; drags produce no block action (0.2925ms)
✔ badges distinguish blank, uncertain, two and three kinds of marking (0.4266ms)
✔ canvas uses unscaled id loading, the existing contextmenu guard and down-time modifiers (55.4449ms)
✔ 2GiB boundary and plus one require exactly the shared extra approval (1.4318ms)
✔ draft client projects only fixed confirm fields into the tenth command (1.1956ms)
✔ mock forward fetches estimate then confirms the fetched revision (0.5374ms)
✔ fetch failure and invalid summaries block approval instead of assuming zero (0.862ms)
✔ confirmation card renders fetched byte count, loading, refusal and second dialog (10.5727ms)
✔ only HUMAN_CHECK uses the confirm card and pending-call revision stays server-owned (1.1211ms)
✔ old numeric preview call keeps the exact single-band request (11.614ms)
✔ extended preview request projects only allowed keys and explicit full resolution (0.3279ms)
✔ S05 band changes use display state, full resolution, and retain PNG onload hotfix (3.028ms)
✔ display modes are exclusive, preserve RGB order and reject duplicates (0.5723ms)
✔ entry defaults to backend automatic selection and displays returned RGB wavelengths (0.5615ms)
✔ default LUT is identity for all 256 intensities (0.4862ms)
✔ LUT rejects nonfinite/out of range/gap under 16 and preserves last valid parameters (0.4197ms)
✔ LUT follows clamp and inverse gamma, one table for RGB, alpha unchanged and input untouched (0.4141ms)
✔ manual LUT values stay local and are independent of image request keys (39.0302ms)
✔ point coordinates retain [line,sample] and send one-pixel spectra_mean, never region (0.7897ms)
✔ point inspection returns before any edit tool and leaves null gaps visible (1.6794ms)
✔ box mean uses existing half-open endpoints, direction independent, no spectral arithmetic (0.3092ms)
✔ box inspection routes to spectra before edits and has no readiness dependency (0.4628ms)
✔ storeGesture projects exactly point, box or doodle and strips nested extras (5.8889ms)
✔ gesture projection adds no absent variant fields or optional defaults (0.7933ms)
✔ gesture client uses only annotations_draft_forward and preserves server reference (0.3638ms)
✔ gesture store failure reaches caller without a fabricated reference (13.5949ms)
✔ B1/B6 parent folder supports Windows, slash and mixed paths (2.8299ms)
✔ B1 matching is exact, case insensitive and trims only (0.2842ms)
✔ B1 background number 1 is excluded; first ordered foreground match wins (0.2378ms)
✔ B2 catalog returns the canonical code without constructing label fields (0.2633ms)
✔ B2 an absent folder matches after the refreshed label list includes the catalog label (0.1837ms)
✔ B3 matching leaves the input list and labels unchanged (0.2493ms)
✔ B4 folders are derived separately for each cube (0.1896ms)
✔ B5 single-file import with an arbitrary parent has no fallback label or catalog code (0.2447ms)
✔ C4: previous version total and current label-index counts render as separate summaries (91.7308ms)
✔ C4: zero classes and uncertainty are omitted while zero blank pixels remain visible (0.3701ms)
✔ C4: missing overwrite summary cannot suppress the confirmation dialog (0.3905ms)
✔ C1/C2/C3/C7: auto-default uses a touched ref, resets per dataset, and follows the version count (0.358ms)
✔ C1/C3/C6: overwrite retains the confirmation gate and cancelling only dismisses the dialog (0.2832ms)
✔ projection consumes save response, shows a selectable absolute path and fixed folder command (1.247ms)
✔ projection failures keep save available and explicitly explain overwrite retry (0.572ms)
✔ click binds C; Delete and Shift are not independent commands (2.5581ms)
✔ 0 is background-only; 1–9 are numeric; unbound or out-of-range labels remain mouse-only (1.3271ms)
✔ Enter / Z / D / E-B-P / arrows / Ctrl+S / space have the specified actions (0.4744ms)
✔ typing never changes labels or undo; disabled settings suppress shortcuts; global chat keys pass through (0.2661ms)
✔ local remapping is deterministic and rejects duplicates/reserved keys without altering server labels (0.5485ms)
✔ each edit reads working again; write-response pixels, queue and statistics are never reconstructed (2.8925ms)
✔ switching cubes and recovering after confirm use only GET working, never diffuse (0.4748ms)
✔ a failed edit propagates its envelope and cannot manufacture a successful redraw (0.6748ms)
✔ R17 label indexes use sort_order plus SQLite BINARY code order, independent of tree grouping (0.3522ms)
✔ local remaining-time estimate derives only from confirmation speed and handles no progress (1.7859ms)
✔ catalog color proximity uses backend colors and the task-card <30 rule (0.8133ms)
✔ viewport transforms preserve [line,sample], bounds, zoom anchors and half-open boxes (0.6537ms)
✔ component wiring has no local label map or undo history and preserves the outer conversation bar (36.6351ms)
✔ plan card renders table, scalar metadata, estimates, aria labels and chosen invalidation (16.7894ms)
✔ all destructive choices require a reason and IPC projects only plan contract fields (31.174ms)
✔ disabled controls cannot submit and history keeps the plan decision without action buttons (5.3492ms)
✔ all agent operations invoke only agent_forward with exact projection (2.3332ms)
✔ view state, URL, key and mixed-body extras cannot enter IPC (0.3323ms)
✔ structured preflight HTTP status and errors pass through unchanged (0.7963ms)
✔ workspace context projects opaque references and cannot leak display data or geometry (0.3246ms)
✔ server-listed ordinals and names are usable without reimporting files in the current UI (2.8866ms)
✔ legacy lists retain backend order while local names remain local (0.4959ms)
✔ changing cubes clears an old gesture and same-cube followups retain it (0.2865ms)
✔ only successful annotation or preprocessing steps cause authoritative result refresh (0.5062ms)
✔ workspace SSE rejects paths, unbound geometry, unknown stage and invalid revisions (1.1921ms)
✔ request failures and SSE failures share human-readable error messages (0.4665ms)
✔ curated backend explanations survive both error delivery paths (0.4489ms)
✔ AI preview focus uses the workflow reference rather than queue order or a diffusion identifier (0.4897ms)
✔ P1 A1 App owns one session shared by Composer and S01; renderers have no reducer (59.8126ms)
✔ P1 A2 A3 composer hiding and global shortcuts leave S01 input independent (1.2755ms)
✔ P1 A4 A5 smoke stays in S01 and the three columns use current session context (13.1118ms)
✔ P1 A6 A8 retired panel files and rules are absent with only six new layout classes (2.6571ms)
✔ SSE 正常流 retains order and JSON (2.9622ms)
✔ SSE 确认后挂起 retains order and JSON (0.3626ms)
✔ SSE 错误收尾 retains order and JSON (0.3162ms)
✔ SSE 空流 retains order and JSON (1.3575ms)
✔ SSE accepts CRLF, multiline data, comments and final frame at EOF (0.2828ms)
✔ SSE rejects unknown events, missing event, malformed and nonobject data (0.4869ms)
✔ SSE collector retains every rejected step beyond eight (0.5089ms)
✔ approve disables both controls and records executing until response (0.2534ms)
✔ reject immediately closes confirmation card; server result remains ordered (0.2705ms)
✔ pending check accepts ordinary dialogue and sequential checks replace pending id (0.3638ms)
✔ clarify and errors release busy state and keep messages in order (0.2482ms)
✔ summary renderer displays scalars and excludes unexpected objects (0.2661ms)
✔ plan SSE is accepted, accepts dialogue and cannot use the tool-decision path (0.2432ms)
✔ unrecognized approval dialogue keeps its card while terminal outcomes clear it (0.3666ms)
✔ plan actions preserve pending while executing and retain the decision with the original plan (0.3614ms)
✔ plan approval can suspend again at human check and all terminal events clear pending (0.2028ms)
✔ chat-selected registered cubes load through the existing fixed get operation (1.9063ms)
✔ G3 shared displayName uses the server name and preserves the legacy fallback (1.0555ms)
✔ G2 all_datasets refreshes a previously unique name without duplicating records (1.2159ms)
✔ G assistant choices and readable references use exactly the API display name (1.0667ms)
✔ retries and existing imports keep exactly one row per persisted ID (2.2575ms)
✔ batch errors retain source path and reason for the user (0.4516ms)
✔ sample value uses fixed native command and preserves annotation response (3.2821ms)
✔ CSV duplicate confirmation is an explicit second import (0.4123ms)
✔ PLS request retains explicit bound runs and only regression CV; seven result labels (0.5227ms)
✔ coefficients use one fixed read-only native operation and exact model id body (0.3765ms)
✔ extents exclude null and non-finite values without changing inputs (2.8495ms)
✔ coordinate mapping covers endpoints, inverted Y, constants and extreme finite domains (0.4115ms)
✔ nice ticks are deterministic, rounded and integer-only for counts or LVs (1.6767ms)
✔ null and non-finite curve points split paths and never interpolate gaps (0.3979ms)
✔ histogram uses sqrt sample count capped at 20, shared rounded edges and grouped counts (1.5412ms)
✔ histogram bins are left-closed with rightmost edge included; rounded inner edges agree with membership (0.7229ms)
✔ one histogram sample becomes a single nonzero-width bin; invalid values produce no bins (0.3965ms)
✔ four evaluation models include curve, scatter, residual and grouped histogram (2.1827ms)
✔ LV markers use saved recommendations verbatim rather than recomputing an elbow (0.9237ms)
✔ empty curve and all non-finite curves show explicit no-data status without axes (0.8445ms)
✔ curve missing values retain separated finite paths and single-point strokes (0.7237ms)
✔ one prediction is a square, maps constant axes to midlines and has one populated histogram bar (0.5608ms)
✔ constant references with varying predictions remain on X midline with an explicit note (0.4628ms)
✔ null metrics never enter chart coordinates or quality calculations (0.701ms)
✔ get_run failure produces four explicit unavailable plots, never blank axes (0.4327ms)
✔ missing LV artifact preserves the three prediction plots and their quality labels (0.4294ms)
✔ undefined predictions from classification runs are explicit, empty arrays remain no-data (0.4567ms)
✔ missing fields and unknown sets are excluded per chart, with an explicit reason when all are unusable (0.2858ms)
✔ half-quantitative label uses backend flag or label and never derives RPD (0.6324ms)
✔ loading has visible messages and a result can render while its curve is still loading (1.6542ms)
✔ error descriptions handle structured native errors and opaque values without secondary throws (0.9791ms)
✔ coefficient chart preserves signed values, zero reference, backend quality and tick targets (1.2033ms)
✔ coefficient refusal: unknown axis (0.294ms)
✔ coefficient refusal: dimension mismatch (0.0921ms)
✔ coefficient refusal: same dimensions unsafe operator (0.0643ms)
✔ coefficient loading, missing artifact and 404 have visible messages without secondary errors (0.1505ms)
✔ coefficient empty and invalid arrays are distinct and never draw malformed nested coefficients (0.2017ms)
✔ coefficient zero line remains inside frame for 1,1,1 (0.717ms)
✔ coefficient zero line remains inside frame for -3,-3,-3 (0.4085ms)
✔ coefficient zero line remains inside frame for 0,0,0 (0.9878ms)
✔ coefficient zero line remains inside frame for 1,2,3 (0.8503ms)
✔ coefficient zero line remains inside frame for -1,-2,-3 (0.2455ms)
✔ single coefficient is one square; nonascending wavelengths retain artifact order and disclose it (0.4698ms)
✔ six new fixed requests preserve exact bodies and strip input extras (1.4835ms)
✔ map source permits only PNG base64 and positive integer dimensions (0.3561ms)
✔ fixed palette rejects invalid RGB and preserves ordered endpoints (0.2122ms)
✔ clipping disclosure includes foreground totals and both directions (0.1193ms)
✔ stages and required scientific warning are explicit (0.1168ms)
✔ components use the client, disclose calibration, progress and independent map errors (42.785ms)
✔ registered coefficient button is lazy per model and shows pending then success or 404 state (137.7389ms)
✔ preprocess IPC list_recipes: exact projection and sole command (2.5809ms)
✔ preprocess IPC create_recipe: exact projection and sole command (1.61ms)
✔ preprocess IPC get_recipe: exact projection and sole command (0.3495ms)
✔ preprocess IPC add_version: exact projection and sole command (0.2707ms)
✔ preprocess IPC select_recipe: exact projection and sole command (0.2529ms)
✔ preprocess IPC deselect_recipe: exact projection and sole command (0.2043ms)
✔ preprocess IPC list_project_recipes: exact projection and sole command (0.2455ms)
✔ preprocess IPC create_run: exact projection and sole command (0.2712ms)
✔ preprocess IPC list_runs: exact projection and sole command (0.2423ms)
✔ preprocess IPC get_run: exact projection and sole command (0.31ms)
✔ preprocess IPC compare: exact projection and sole command (0.2386ms)
✔ preprocess IPC get_artifact: exact projection and sole command (0.1969ms)
✔ request bodies omit runtime extras, run guard/block_size, and editor state (0.2578ms)
✔ report is parsed JSON; only sample_spectra uses binary wrapper; 204 stays null (0.3056ms)
✔ recovery inspects only new succeeded summaries and matches recipe in details (2.2261ms)
✔ transport and timeout recover, business errors do not; structured details remain visible (1.8698ms)
✔ submit TRANSPORT automatically restores new matching success; unknown outcome stays pending verification (1.3304ms)
✔ legend resolves index→id→code with backend colors, missing id prefix, unlabeled title (0.3145ms)
✔ S06 component wiring: no transport outside API, no numeric engine / fake preview; global chat unchanged (63.5264ms)
✔ unsupported operations are all marked stage two / not applicable without example metrics (0.3158ms)
✔ operator directory matches explicit R15 names and excludes run B01 / unresolved reference methods (2.4021ms)
✔ axisAfter is pure, crop closed, resample replaces, decomposition removes axis (0.5869ms)
✔ crop→resample→crop supplies EACH current source, never stale saved source (0.605ms)
✔ schema-direction validation: odd SG, STRICT polynomial bound, derivative order/mode (0.5304ms)
✔ all exposed methods accept valid schema choices; unknown keys and absent components reject (2.521ms)
✔ no wavelengths disables axis operators; lo<hi, nonempty crop, target finite/increasing enforce (0.544ms)
✔ move/delete/repeat preserve order and compile legal explicit steps (0.2751ms)
✔ target creation is axis-only; chart gaps retain separate strokes and values (0.3231ms)
✔ settings screen starts with five empty text fields, an enabled egress switch, a password input and an unknown key status (16.914ms)
✔ rendered field changes and submit save the six-key config then key, and clear the password (10.2414ms)
✔ GET has_key renders both states without pre-filling a key, and blank key preserves existing credentials (2.8945ms)
✔ GET failure disables saving and fields while the rendered cancel button remains usable (3.4265ms)
✔ nonempty URL and numeric validation blocks invalid saves without inventing provider limits (7.0246ms)
✔ backend 400 code and detail are rendered and a failed config save never submits the key (3.4922ms)
✔ failed key write reports partial save, clears its input and redacts credentials in errors (2.9737ms)
✔ saving prevents duplicate submits and disposing ignores an in-flight GET (1.6992ms)
✔ App settings entry opens S11 with its embedded form, preserving UI-to-configuration reachability (0.8687ms)
✔ egress checkbox reflects the false value returned by GET (1.8233ms)
✔ unchecking egress saves a boolean false and keeps the returned switch state (1.2292ms)
✔ settings GET and two PUT operations use only settings_forward with exact bodies (4.5807ms)
✔ settings projections exclude credentials and view or route extras from config and responses (0.4798ms)
✔ settings forward preserves the backend 400 envelope unchanged (1.3087ms)
✔ egress false remains boolean through config PUT and GET projections (1.1624ms)
✔ P5 S02 uses props for four cards, recent regression runs and phase plus generation only (2.2074ms)
✔ P5 S09 regression table has only id task status and a client task filter without invented timestamps (1.6416ms)
✔ P5 S09 fetches selected run details and retains backend metrics quality and collapsed leak report (0.4824ms)
✔ P5 S09 preprocess reads only the selected dataset and preserves real time fields and empty states (0.4867ms)
✔ P5 S10 has a data-screen action and S11 embeds the settings form without fake controls (0.2993ms)
✔ P5 inserts four screen cases while preserving source anchors S03 debug text and theme boundary (0.5223ms)
✔ P2 navigation preserves App runId until the results back-to-list action (1.3475ms)
✔ P2 S04 and S03 thumbnails share BandCanvas and viewing updates workspace (0.5253ms)
✔ P2 S08 loads real regression runs and refetches run plus sweep on mount (0.3604ms)
✔ P2 S07 keeps training and internal views while results and source anchors stay intact (1.0522ms)
✔ A1 navigation retains five ordered groups and exactly ten unique screen entries (1.9653ms)
✔ A1 titles cover all eleven Screen values including the viewer below data (0.3019ms)
✔ A1 only s04 redirects its navigation highlight to s03 (0.2419ms)
✔ skin guards: annotation-skin.css (12.1457ms)
✔ skin guards: preprocess-skin.css (9.0499ms)
✔ skin guards: modeling-skin.css (7.2763ms)
ℹ tests 218
ℹ suites 0
ℹ pass 218
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 1591.031
```

## 终值 node 原文

取数命令（本机实际执行；完整原文见 [node-after.txt](E:/AI_Agent/milestone25/evidence/B/node-after.txt)）：

```powershell
node --test "src/**/*.test.ts"
```

```text
✔ block clicks retain the legacy geometry and omit label_id for erase and uncertain (3.0096ms)
✔ IPC superpixels: exact Rust variant, one command, no arbitrary route (0.4439ms)
✔ IPC diffuse: exact Rust variant, one command, no arbitrary route (0.3108ms)
✔ IPC regions: exact Rust variant, one command, no arbitrary route (0.2048ms)
✔ IPC undo: exact Rust variant, one command, no arbitrary route (0.2103ms)
✔ IPC working: exact Rust variant, one command, no arbitrary route (0.1974ms)
✔ IPC validate: exact Rust variant, one command, no arbitrary route (0.2102ms)
✔ IPC save: exact Rust variant, one command, no arbitrary route (0.2405ms)
✔ IPC versions: exact Rust variant, one command, no arbitrary route (0.2382ms)
✔ IPC version_overlay: exact Rust variant, one command, no arbitrary route (0.3024ms)
✔ IPC projects: exact Rust variant, one command, no arbitrary route (0.2261ms)
✔ IPC labels: exact Rust variant, one command, no arbitrary route (0.1514ms)
✔ IPC add_label: exact Rust variant, one command, no arbitrary route (0.2158ms)
✔ IPC catalog: exact Rust variant, one command, no arbitrary route (0.2065ms)
✔ optional defaults are left to Python; all prompt and geometry forms retain [line,sample] (0.3106ms)
✔ all three structured label bodies match Python and carry the working project id (0.2953ms)
✔ local estimates and display state cannot enter request projections (0.4731ms)
✔ structured errors keep code, field messages and context; client never swallows rejection (1.1768ms)
✔ RGB id decoding retains ids above 255 and verifies every block count (3.4862ms)
✔ hitTest is local and rejects out-of-image and fractional coordinates (0.4608ms)
✔ 3px Euclidean boundary is inclusive; drags produce no block action (0.3257ms)
✔ badges distinguish blank, uncertain, two and three kinds of marking (0.4456ms)
✔ canvas uses unscaled id loading, the existing contextmenu guard and down-time modifiers (2.9617ms)
✔ 2GiB boundary and plus one require exactly the shared extra approval (1.0492ms)
✔ draft client projects only fixed confirm fields into the tenth command (1.5372ms)
✔ mock forward fetches estimate then confirms the fetched revision (0.4908ms)
✔ fetch failure and invalid summaries block approval instead of assuming zero (1.0865ms)
✔ confirmation card renders fetched byte count, loading, refusal and second dialog (19.267ms)
✔ only HUMAN_CHECK uses the confirm card and pending-call revision stays server-owned (1.5386ms)
✔ old numeric preview call keeps the exact single-band request (2.5216ms)
✔ extended preview request projects only allowed keys and explicit full resolution (0.2498ms)
✔ S05 band changes use display state, full resolution, and retain PNG onload hotfix (1.3569ms)
✔ display modes are exclusive, preserve RGB order and reject duplicates (0.6869ms)
✔ entry defaults to backend automatic selection and displays returned RGB wavelengths (0.6061ms)
✔ default LUT is identity for all 256 intensities (0.444ms)
✔ LUT rejects nonfinite/out of range/gap under 16 and preserves last valid parameters (0.3483ms)
✔ LUT follows clamp and inverse gamma, one table for RGB, alpha unchanged and input untouched (0.3366ms)
✔ manual LUT values stay local and are independent of image request keys (0.9563ms)
✔ point coordinates retain [line,sample] and send one-pixel spectra_mean, never region (0.4004ms)
✔ point inspection returns before any edit tool and leaves null gaps visible (0.6174ms)
✔ box mean uses existing half-open endpoints, direction independent, no spectral arithmetic (0.2529ms)
✔ box inspection routes to spectra before edits and has no readiness dependency (0.3519ms)
✔ storeGesture projects exactly point, box or doodle and strips nested extras (2.2117ms)
✔ gesture projection adds no absent variant fields or optional defaults (0.3555ms)
✔ gesture client uses only annotations_draft_forward and preserves server reference (0.3436ms)
✔ gesture store failure reaches caller without a fabricated reference (0.7262ms)
✔ B1/B6 parent folder supports Windows, slash and mixed paths (1.8078ms)
✔ B1 matching is exact, case insensitive and trims only (0.3663ms)
✔ B1 background number 1 is excluded; first ordered foreground match wins (0.6224ms)
✔ B2 catalog returns the canonical code without constructing label fields (0.3198ms)
✔ B2 an absent folder matches after the refreshed label list includes the catalog label (0.2016ms)
✔ B3 matching leaves the input list and labels unchanged (0.2924ms)
✔ B4 folders are derived separately for each cube (0.2315ms)
✔ B5 single-file import with an arbitrary parent has no fallback label or catalog code (0.2585ms)
✔ C4: previous version total and current label-index counts render as separate summaries (20.8209ms)
✔ C4: zero classes and uncertainty are omitted while zero blank pixels remain visible (0.2588ms)
✔ C4: missing overwrite summary cannot suppress the confirmation dialog (0.3516ms)
✔ C1/C2/C3/C7: auto-default uses a touched ref, resets per dataset, and follows the version count (0.3279ms)
✔ C1/C3/C6: overwrite retains the confirmation gate and cancelling only dismisses the dialog (0.27ms)
✔ projection consumes save response, shows a selectable absolute path and fixed folder command (1.279ms)
✔ projection failures keep save available and explicitly explain overwrite retry (0.5846ms)
✔ click binds C; Delete and Shift are not independent commands (3.4822ms)
✔ 0 is background-only; 1–9 are numeric; unbound or out-of-range labels remain mouse-only (1.0127ms)
✔ Enter / Z / D / E-B-P / arrows / Ctrl+S / space have the specified actions (0.451ms)
✔ typing never changes labels or undo; disabled settings suppress shortcuts; global chat keys pass through (0.2443ms)
✔ local remapping is deterministic and rejects duplicates/reserved keys without altering server labels (0.6444ms)
✔ each edit reads working again; write-response pixels, queue and statistics are never reconstructed (2.5002ms)
✔ switching cubes and recovering after confirm use only GET working, never diffuse (0.3233ms)
✔ a failed edit propagates its envelope and cannot manufacture a successful redraw (0.5722ms)
✔ R17 label indexes use sort_order plus SQLite BINARY code order, independent of tree grouping (0.3853ms)
✔ local remaining-time estimate derives only from confirmation speed and handles no progress (0.2236ms)
✔ catalog color proximity uses backend colors and the task-card <30 rule (0.2699ms)
✔ viewport transforms preserve [line,sample], bounds, zoom anchors and half-open boxes (1.6099ms)
✔ component wiring has no local label map or undo history and preserves the outer conversation bar (2.2982ms)
✔ plan card renders table, scalar metadata, estimates, aria labels and chosen invalidation (21.8502ms)
✔ all destructive choices require a reason and IPC projects only plan contract fields (34.7298ms)
✔ disabled controls cannot submit and history keeps the plan decision without action buttons (5.3708ms)
✔ all agent operations invoke only agent_forward with exact projection (3.3015ms)
✔ view state, URL, key and mixed-body extras cannot enter IPC (0.2353ms)
✔ structured preflight HTTP status and errors pass through unchanged (0.6203ms)
✔ workspace context projects opaque references and cannot leak display data or geometry (0.2926ms)
✔ server-listed ordinals and names are usable without reimporting files in the current UI (3.6212ms)
✔ legacy lists retain backend order while local names remain local (0.4751ms)
✔ changing cubes clears an old gesture and same-cube followups retain it (1.374ms)
✔ only successful annotation or preprocessing steps cause authoritative result refresh (0.7744ms)
✔ workspace SSE rejects paths, unbound geometry, unknown stage and invalid revisions (1.4219ms)
✔ request failures and SSE failures share human-readable error messages (0.3842ms)
✔ curated backend explanations survive both error delivery paths (0.3715ms)
✔ AI preview focus uses the workflow reference rather than queue order or a diffusion identifier (0.4237ms)
✔ P1 A1 App owns one session shared by Composer and S01; renderers have no reducer (2.4768ms)
✔ P1 A2 A3 composer hiding and global shortcuts leave S01 input independent (0.8416ms)
✔ P1 A4 A5 smoke stays in S01 and the three columns use current session context (1.1249ms)
✔ P1 A6 A8 retired panel files and rules are absent with only six new layout classes (1.876ms)
✔ SSE 正常流 retains order and JSON (2.3435ms)
✔ SSE 确认后挂起 retains order and JSON (0.2633ms)
✔ SSE 错误收尾 retains order and JSON (0.2567ms)
✔ SSE 空流 retains order and JSON (1.1762ms)
✔ SSE accepts CRLF, multiline data, comments and final frame at EOF (0.2858ms)
✔ SSE rejects unknown events, missing event, malformed and nonobject data (0.4073ms)
✔ SSE collector retains every rejected step beyond eight (0.3995ms)
✔ approve disables both controls and records executing until response (0.2569ms)
✔ reject immediately closes confirmation card; server result remains ordered (0.2303ms)
✔ pending check accepts ordinary dialogue and sequential checks replace pending id (0.3382ms)
✔ clarify and errors release busy state and keep messages in order (0.2287ms)
✔ summary renderer displays scalars and excludes unexpected objects (0.249ms)
✔ plan SSE is accepted, accepts dialogue and cannot use the tool-decision path (0.2608ms)
✔ unrecognized approval dialogue keeps its card while terminal outcomes clear it (0.3355ms)
✔ plan actions preserve pending while executing and retain the decision with the original plan (0.3385ms)
✔ plan approval can suspend again at human check and all terminal events clear pending (0.1915ms)
✔ chat-selected registered cubes load through the existing fixed get operation (5.5729ms)
✔ catalog and recycle operations use fixed typed requests with explicit confirmation (0.6257ms)
✔ reimport confirmation is sent only from an explicit caller choice (0.3847ms)
✔ G3 shared displayName uses the server name and preserves the legacy fallback (1.4101ms)
✔ G2 all_datasets refreshes a previously unique name without duplicating records (1.0268ms)
✔ G assistant choices and readable references use exactly the API display name (0.929ms)
✔ only the absent-active recycled-key error promises a new dataset id (1.1491ms)
✔ active records and concurrent active conflicts never open the fresh-id confirmation (0.2326ms)
✔ existing and newly imported messages agree with actual response counts (0.1887ms)
✔ retries and existing imports keep exactly one row per persisted ID (1.8952ms)
✔ batch errors retain source path and reason for the user (0.4197ms)
✔ sample value uses fixed native command and preserves annotation response (2.4559ms)
✔ CSV duplicate confirmation is an explicit second import (0.3505ms)
✔ PLS request retains explicit bound runs and only regression CV; seven result labels (0.4785ms)
✔ coefficients use one fixed read-only native operation and exact model id body (0.4868ms)
✔ extents exclude null and non-finite values without changing inputs (2.5879ms)
✔ coordinate mapping covers endpoints, inverted Y, constants and extreme finite domains (0.3705ms)
✔ nice ticks are deterministic, rounded and integer-only for counts or LVs (0.4307ms)
✔ null and non-finite curve points split paths and never interpolate gaps (0.3078ms)
✔ histogram uses sqrt sample count capped at 20, shared rounded edges and grouped counts (1.2383ms)
✔ histogram bins are left-closed with rightmost edge included; rounded inner edges agree with membership (0.326ms)
✔ one histogram sample becomes a single nonzero-width bin; invalid values produce no bins (0.3137ms)
✔ four evaluation models include curve, scatter, residual and grouped histogram (2.2235ms)
✔ LV markers use saved recommendations verbatim rather than recomputing an elbow (1.0076ms)
✔ empty curve and all non-finite curves show explicit no-data status without axes (0.897ms)
✔ curve missing values retain separated finite paths and single-point strokes (0.5741ms)
✔ one prediction is a square, maps constant axes to midlines and has one populated histogram bar (0.4795ms)
✔ constant references with varying predictions remain on X midline with an explicit note (0.4863ms)
✔ null metrics never enter chart coordinates or quality calculations (0.708ms)
✔ get_run failure produces four explicit unavailable plots, never blank axes (0.4877ms)
✔ missing LV artifact preserves the three prediction plots and their quality labels (0.4287ms)
✔ undefined predictions from classification runs are explicit, empty arrays remain no-data (0.4326ms)
✔ missing fields and unknown sets are excluded per chart, with an explicit reason when all are unusable (0.2709ms)
✔ half-quantitative label uses backend flag or label and never derives RPD (0.5815ms)
✔ loading has visible messages and a result can render while its curve is still loading (0.2748ms)
✔ error descriptions handle structured native errors and opaque values without secondary throws (0.2012ms)
✔ coefficient chart preserves signed values, zero reference, backend quality and tick targets (0.6343ms)
✔ coefficient refusal: unknown axis (0.2282ms)
✔ coefficient refusal: dimension mismatch (0.0785ms)
✔ coefficient refusal: same dimensions unsafe operator (0.0953ms)
✔ coefficient loading, missing artifact and 404 have visible messages without secondary errors (0.1471ms)
✔ coefficient empty and invalid arrays are distinct and never draw malformed nested coefficients (0.3327ms)
✔ coefficient zero line remains inside frame for 1,1,1 (0.3075ms)
✔ coefficient zero line remains inside frame for -3,-3,-3 (0.1469ms)
✔ coefficient zero line remains inside frame for 0,0,0 (0.1213ms)
✔ coefficient zero line remains inside frame for 1,2,3 (0.1475ms)
✔ coefficient zero line remains inside frame for -1,-2,-3 (0.093ms)
✔ single coefficient is one square; nonascending wavelengths retain artifact order and disclose it (0.2749ms)
✔ six new fixed requests preserve exact bodies and strip input extras (1.3249ms)
✔ map source permits only PNG base64 and positive integer dimensions (0.2986ms)
✔ fixed palette rejects invalid RGB and preserves ordered endpoints (0.1701ms)
✔ clipping disclosure includes foreground totals and both directions (0.1122ms)
✔ stages and required scientific warning are explicit (0.1034ms)
✔ components use the client, disclose calibration, progress and independent map errors (0.7107ms)
✔ registered coefficient button is lazy per model and shows pending then success or 404 state (87.7995ms)
✔ preprocess IPC list_recipes: exact projection and sole command (2.1743ms)
✔ preprocess IPC create_recipe: exact projection and sole command (1.6569ms)
✔ preprocess IPC get_recipe: exact projection and sole command (0.2661ms)
✔ preprocess IPC add_version: exact projection and sole command (0.2265ms)
✔ preprocess IPC select_recipe: exact projection and sole command (0.2294ms)
✔ preprocess IPC deselect_recipe: exact projection and sole command (0.1926ms)
✔ preprocess IPC list_project_recipes: exact projection and sole command (0.1955ms)
✔ preprocess IPC create_run: exact projection and sole command (0.2167ms)
✔ preprocess IPC list_runs: exact projection and sole command (0.241ms)
✔ preprocess IPC get_run: exact projection and sole command (0.2762ms)
✔ preprocess IPC compare: exact projection and sole command (0.2324ms)
✔ preprocess IPC get_artifact: exact projection and sole command (0.2063ms)
✔ request bodies omit runtime extras, run guard/block_size, and editor state (0.2139ms)
✔ report is parsed JSON; only sample_spectra uses binary wrapper; 204 stays null (0.2233ms)
✔ recovery inspects only new succeeded summaries and matches recipe in details (2.2699ms)
✔ transport and timeout recover, business errors do not; structured details remain visible (1.9009ms)
✔ submit TRANSPORT automatically restores new matching success; unknown outcome stays pending verification (1.0992ms)
✔ legend resolves index→id→code with backend colors, missing id prefix, unlabeled title (0.3395ms)
✔ S06 component wiring: no transport outside API, no numeric engine / fake preview; global chat unchanged (2.5001ms)
✔ unsupported operations are all marked stage two / not applicable without example metrics (0.3391ms)
✔ operator directory matches explicit R15 names and excludes run B01 / unresolved reference methods (3.5633ms)
✔ axisAfter is pure, crop closed, resample replaces, decomposition removes axis (0.7073ms)
✔ crop→resample→crop supplies EACH current source, never stale saved source (0.4329ms)
✔ schema-direction validation: odd SG, STRICT polynomial bound, derivative order/mode (0.4167ms)
✔ all exposed methods accept valid schema choices; unknown keys and absent components reject (1.573ms)
✔ no wavelengths disables axis operators; lo<hi, nonempty crop, target finite/increasing enforce (0.5397ms)
✔ move/delete/repeat preserve order and compile legal explicit steps (0.2538ms)
✔ target creation is axis-only; chart gaps retain separate strokes and values (0.2915ms)
✔ settings screen starts with five empty text fields, an enabled egress switch, a password input and an unknown key status (11.743ms)
✔ rendered field changes and submit save the six-key config then key, and clear the password (5.0982ms)
✔ GET has_key renders both states without pre-filling a key, and blank key preserves existing credentials (2.0396ms)
✔ GET failure disables saving and fields while the rendered cancel button remains usable (2.3386ms)
✔ nonempty URL and numeric validation blocks invalid saves without inventing provider limits (4.0006ms)
✔ backend 400 code and detail are rendered and a failed config save never submits the key (1.5122ms)
✔ failed key write reports partial save, clears its input and redacts credentials in errors (2.453ms)
✔ saving prevents duplicate submits and disposing ignores an in-flight GET (0.7904ms)
✔ App settings entry opens S11 with its embedded form, preserving UI-to-configuration reachability (0.519ms)
✔ egress checkbox reflects the false value returned by GET (1.0551ms)
✔ unchecking egress saves a boolean false and keeps the returned switch state (0.7461ms)
✔ settings GET and two PUT operations use only settings_forward with exact bodies (1.5323ms)
✔ settings projections exclude credentials and view or route extras from config and responses (0.2038ms)
✔ settings forward preserves the backend 400 envelope unchanged (0.5918ms)
✔ egress false remains boolean through config PUT and GET projections (0.2408ms)
✔ P5 S02 uses props for four cards, recent regression runs and phase plus generation only (1.1557ms)
✔ P5 S09 regression table has only id task status and a client task filter without invented timestamps (1.1183ms)
✔ P5 S09 fetches selected run details and retains backend metrics quality and collapsed leak report (0.2493ms)
✔ P5 S09 preprocess reads only the selected dataset and preserves real time fields and empty states (0.2479ms)
✔ P5 S10 has a data-screen action and S11 embeds the settings form without fake controls (0.2085ms)
✔ P5 inserts four screen cases while preserving source anchors S03 debug text and theme boundary (0.439ms)
✔ P2 navigation preserves App runId until the results back-to-list action (1.1552ms)
✔ P2 S04 and S03 thumbnails share BandCanvas and viewing updates workspace (0.422ms)
✔ P2 S08 loads real regression runs and refetches run plus sweep on mount (0.3155ms)
✔ P2 S07 keeps training and internal views while results and source anchors stay intact (0.6105ms)
✔ A1 navigation retains five ordered groups and exactly ten unique screen entries (1.8252ms)
✔ A1 titles cover all eleven Screen values including the viewer below data (0.2353ms)
✔ A1 only s04 redirects its navigation highlight to s03 (0.2165ms)
✔ skin guards: annotation-skin.css (1.597ms)
✔ skin guards: preprocess-skin.css (0.3444ms)
✔ skin guards: modeling-skin.css (0.3819ms)
ℹ tests 223
ℹ suites 0
ℹ pass 223
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 689.6127
```

## 开工 Python collected 尾原文

取数命令（本机实际执行；完整原文见 [before-Python-collected.txt](E:/AI_Agent/milestone25/evidence/B/before-Python-collected.txt)）：

```powershell
$env:PYTHONIOENCODING='utf-8'; $task25Tmp=Join-Path $env:TEMP 't25bo'; New-Item -ItemType Directory -Force -Path $task25Tmp | Out-Null; $env:PYTEST_DEBUG_TEMPROOT=$task25Tmp; if ((Get-PSDrive C).Free -lt 3GB) { throw 'C free space below required 3GiB' }
& .venv/Scripts/python.exe -m pytest backend/tests src-python/tests --collect-only -q
```

```text
src-python/tests/test_display_falsecolor.py::test_mean_invalid_bounds_reject_without_clipping[body2]
src-python/tests/test_display_falsecolor.py::test_mean_invalid_bounds_reject_without_clipping[body3]
src-python/tests/test_display_falsecolor.py::test_mean_does_not_reuse_65536_json_value_limit
src-python/tests/test_display_falsecolor.py::test_mean_one_million_pixel_boundary[1000-200]
src-python/tests/test_display_falsecolor.py::test_mean_one_million_pixel_boundary[1001-400]
src-python/tests/test_display_falsecolor.py::test_display_requests_do_not_change_annotation_working_or_versions

============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1506 tests collected in 5.79s
```

## 终值 Python collected 尾原文

取数命令（本机实际执行；完整原文见 [Python-collected-after.txt](E:/AI_Agent/milestone25/evidence/B/Python-collected-after.txt)）：

```powershell
$env:PYTHONIOENCODING='utf-8'; $task25Tmp=Join-Path $env:TEMP 't25b5'; New-Item -ItemType Directory -Force -Path $task25Tmp | Out-Null; $env:PYTEST_DEBUG_TEMPROOT=$task25Tmp; if ((Get-PSDrive C).Free -lt 3GB) { throw 'C free space below required 3GiB' }
& .venv/Scripts/python.exe -m pytest backend/tests src-python/tests --collect-only -q
```

```text
src-python/tests/test_display_falsecolor.py::test_mean_invalid_bounds_reject_without_clipping[body2]
src-python/tests/test_display_falsecolor.py::test_mean_invalid_bounds_reject_without_clipping[body3]
src-python/tests/test_display_falsecolor.py::test_mean_does_not_reuse_65536_json_value_limit
src-python/tests/test_display_falsecolor.py::test_mean_one_million_pixel_boundary[1000-200]
src-python/tests/test_display_falsecolor.py::test_mean_one_million_pixel_boundary[1001-400]
src-python/tests/test_display_falsecolor.py::test_display_requests_do_not_change_annotation_working_or_versions

============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1544 tests collected in 2.45s
```

## 开工 backend 实跑

取数命令（本机实际执行；完整原文见 [before-Python-backend.txt](E:/AI_Agent/milestone25/evidence/B/before-Python-backend.txt)）：

```powershell
$env:PYTHONIOENCODING='utf-8'; $task25Tmp=Join-Path $env:TEMP 't25bo'; New-Item -ItemType Directory -Force -Path $task25Tmp | Out-Null; $env:PYTEST_DEBUG_TEMPROOT=$task25Tmp; if ((Get-PSDrive C).Free -lt 3GB) { throw 'C free space below required 3GiB' }
& .venv/Scripts/python.exe -m pytest backend/tests -q
```

```text
.............................................                            [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_cancel_after_first_running_block_keeps_partial_metrics
  E:\AI_Agent\.venv\Lib\site-packages\spectral\io\spyfile.py:217: DeprecationWarning: Setting the shape on a NumPy array has been deprecated in NumPy 2.5.
  As an alternative, you can create a new view using np.reshape (with copy=False if needed).
    npArray.shape = (self.nrows, self.ncols, self.nbands)

backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_cancel_after_first_running_block_keeps_partial_metrics
backend/tests/test_foundation.py::test_cancel_after_first_running_block_keeps_partial_metrics
  E:\AI_Agent\.venv\Lib\site-packages\spectral\image.py:24: DeprecationWarning: Setting the dtype on a NumPy array has been deprecated in NumPy 2.5.
  Instead of changing the dtype on an array x, create a new array with x.view(new_dtype)
    self.dtype = params.dtype

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
45 passed, 10 warnings in 7.78s
```

## 开工 src-python 实跑

取数命令（本机实际执行；完整原文见 [before-Python-source.txt](E:/AI_Agent/milestone25/evidence/B/before-Python-source.txt)）：

```powershell
$env:PYTHONIOENCODING='utf-8'; $task25Tmp=Join-Path $env:TEMP 't25bo'; New-Item -ItemType Directory -Force -Path $task25Tmp | Out-Null; $env:PYTEST_DEBUG_TEMPROOT=$task25Tmp; if ((Get-PSDrive C).Free -lt 3GB) { throw 'C free space below required 3GiB' }
& .venv/Scripts/python.exe -m pytest src-python/tests -q
```

```text
........................................................................ [  4%]
........................................................................ [  9%]
........................................................................ [ 14%]
........................................................................ [ 19%]
........................................................................ [ 24%]
........................................................................ [ 29%]
........................................................................ [ 34%]
........................................................................ [ 39%]
........................................................................ [ 44%]
.....................ss................................................. [ 49%]
........................................................................ [ 54%]
........................................................................ [ 59%]
........................................................................ [ 64%]
........................................................................ [ 68%]
........................................................................ [ 73%]
........................................................................ [ 78%]
........................................................................ [ 83%]
........................................................................ [ 88%]
........................................................................ [ 93%]
........................................................................ [ 98%]
.....................                                                    [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

src-python/tests/modeling/test_registry.py::test_all_fitted_calibrations_saved_and_block_invariant[ica-params4]
  E:\AI_Agent\.venv\Lib\site-packages\sklearn\decomposition\_fastica.py:132: ConvergenceWarning: FastICA did not converge. Consider increasing tolerance or the maximum number of iterations.
    warnings.warn(

src-python/tests/modeling/test_regression.py::test_undefined_scores_persist_null_not_zero
src-python/tests/modeling/test_regression.py::test_undefined_scores_persist_null_not_zero
src-python/tests/modeling/test_regression.py::test_undefined_scores_persist_null_not_zero
src-python/tests/modeling/test_regression.py::test_undefined_scores_persist_null_not_zero
  E:\AI_Agent\.venv\Lib\site-packages\sklearn\cross_decomposition\_pls.py:308: UserWarning: y residual is constant at iteration 0
    warnings.warn(f"y residual is constant at iteration {k}")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1459 passed, 2 skipped, 6 warnings in 562.38s (0:09:22)
```

## 终值 backend 实跑

取数命令（本机实际执行；完整原文见 [Python-backend-after.txt](E:/AI_Agent/milestone25/evidence/B/Python-backend-after.txt)）：

```powershell
$env:PYTHONIOENCODING='utf-8'; $task25Tmp=Join-Path $env:TEMP 't25b5'; New-Item -ItemType Directory -Force -Path $task25Tmp | Out-Null; $env:PYTEST_DEBUG_TEMPROOT=$task25Tmp; if ((Get-PSDrive C).Free -lt 3GB) { throw 'C free space below required 3GiB' }
& .venv/Scripts/python.exe -m pytest backend/tests -q
```

```text
.............................................                            [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_cancel_after_first_running_block_keeps_partial_metrics
  E:\AI_Agent\.venv\Lib\site-packages\spectral\io\spyfile.py:217: DeprecationWarning: Setting the shape on a NumPy array has been deprecated in NumPy 2.5.
  As an alternative, you can create a new view using np.reshape (with copy=False if needed).
    npArray.shape = (self.nrows, self.ncols, self.nbands)

backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_cancel_after_first_running_block_keeps_partial_metrics
backend/tests/test_foundation.py::test_cancel_after_first_running_block_keeps_partial_metrics
  E:\AI_Agent\.venv\Lib\site-packages\spectral\image.py:24: DeprecationWarning: Setting the dtype on a NumPy array has been deprecated in NumPy 2.5.
  Instead of changing the dtype on an array x, create a new array with x.view(new_dtype)
    self.dtype = params.dtype

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
45 passed, 10 warnings in 6.49s
```

## 终值 src-python 实跑

取数命令（本机实际执行；完整原文见 [Python-source-after.txt](E:/AI_Agent/milestone25/evidence/B/Python-source-after.txt)）：

```powershell
$env:PYTHONIOENCODING='utf-8'; $task25Tmp=Join-Path $env:TEMP 't25b5'; New-Item -ItemType Directory -Force -Path $task25Tmp | Out-Null; $env:PYTEST_DEBUG_TEMPROOT=$task25Tmp; if ((Get-PSDrive C).Free -lt 3GB) { throw 'C free space below required 3GiB' }
& .venv/Scripts/python.exe -m pytest src-python/tests -q
```

```text
........................................................................ [  4%]
........................................................................ [  9%]
........................................................................ [ 14%]
........................................................................ [ 19%]
........................................................................ [ 24%]
........................................................................ [ 28%]
........................................................................ [ 33%]
........................................................................ [ 38%]
........................................................................ [ 43%]
.....................ss................................................. [ 48%]
........................................................................ [ 52%]
........................................................................ [ 57%]
........................................................................ [ 62%]
........................................................................ [ 67%]
........................................................................ [ 72%]
........................................................................ [ 76%]
........................................................................ [ 81%]
........................................................................ [ 86%]
........................................................................ [ 91%]
........................................................................ [ 96%]
...........................................................              [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

src-python/tests/modeling/test_registry.py::test_all_fitted_calibrations_saved_and_block_invariant[ica-params4]
  E:\AI_Agent\.venv\Lib\site-packages\sklearn\decomposition\_fastica.py:132: ConvergenceWarning: FastICA did not converge. Consider increasing tolerance or the maximum number of iterations.
    warnings.warn(

src-python/tests/modeling/test_regression.py::test_undefined_scores_persist_null_not_zero
src-python/tests/modeling/test_regression.py::test_undefined_scores_persist_null_not_zero
src-python/tests/modeling/test_regression.py::test_undefined_scores_persist_null_not_zero
src-python/tests/modeling/test_regression.py::test_undefined_scores_persist_null_not_zero
  E:\AI_Agent\.venv\Lib\site-packages\sklearn\cross_decomposition\_pls.py:308: UserWarning: y residual is constant at iteration 0
    warnings.warn(f"y residual is constant at iteration {k}")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1497 passed, 2 skipped, 6 warnings in 594.55s (0:09:54)
```

## B 段验收原文

取数命令（本机实际执行；完整原文见 [recycle-acceptance.txt](E:/AI_Agent/milestone25/evidence/B/recycle-acceptance.txt)）：

```powershell
$env:PYTHONIOENCODING='utf-8'; $task25Tmp=Join-Path $env:TEMP 't25br'; New-Item -ItemType Directory -Force -Path $task25Tmp | Out-Null; $env:PYTEST_DEBUG_TEMPROOT=$task25Tmp; if ((Get-PSDrive C).Free -lt 3GB) { throw 'C free space below required 3GiB' }
& .venv/Scripts/python.exe -m pytest src-python/tests/storage/test_recycle.py -vv
```

```text
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1, pluggy-1.7.0 -- E:\AI_Agent\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: E:\AI_Agent
plugins: anyio-4.15.1
collecting ... collected 38 items

src-python/tests/storage/test_recycle.py::test_full_delete_restore PASSED [  2%]
src-python/tests/storage/test_recycle.py::test_reimport_and_conflict PASSED [  5%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[False-False-False] PASSED [  7%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[False-False-True] PASSED [ 10%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[False-True-False] PASSED [ 13%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[False-True-True] PASSED [ 15%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[True-False-False] PASSED [ 18%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[True-False-True] PASSED [ 21%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[True-True-False] PASSED [ 23%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[True-True-True] PASSED [ 26%]
src-python/tests/storage/test_recycle.py::test_reimport_confirmed_race PASSED [ 28%]
src-python/tests/storage/test_recycle.py::test_reimport_unique_is_structured PASSED [ 31%]
src-python/tests/storage/test_recycle.py::test_reimport_batch_is_atomic PASSED [ 34%]
src-python/tests/storage/test_recycle.py::test_reimport_key_includes_raw PASSED [ 36%]
src-python/tests/storage/test_recycle.py::test_expiry_and_audit PASSED   [ 39%]
src-python/tests/storage/test_recycle.py::test_preview_binding[false] PASSED [ 42%]
src-python/tests/storage/test_recycle.py::test_preview_binding[tampered] PASSED [ 44%]
src-python/tests/storage/test_recycle.py::test_preview_binding[expired] PASSED [ 47%]
src-python/tests/storage/test_recycle.py::test_preview_binding[changed] PASSED [ 50%]
src-python/tests/storage/test_recycle.py::test_move_failure_rolls_back PASSED [ 52%]
src-python/tests/storage/test_recycle.py::test_commit_failure_rolls_back PASSED [ 55%]
src-python/tests/storage/test_recycle.py::test_restore_move_failure PASSED [ 57%]
src-python/tests/storage/test_recycle.py::test_purge_waits_for_long_run PASSED [ 60%]
src-python/tests/storage/test_recycle.py::test_multi_cube_fails_closed PASSED [ 63%]
src-python/tests/storage/test_recycle.py::test_incomplete_fail_closed[missing] PASSED [ 65%]
src-python/tests/storage/test_recycle.py::test_incomplete_fail_closed[manifest] PASSED [ 68%]
src-python/tests/storage/test_recycle.py::test_incomplete_fail_closed[file] PASSED [ 71%]
src-python/tests/storage/test_recycle.py::test_orphan_mapping_rollback PASSED [ 73%]
src-python/tests/storage/test_recycle.py::test_killed_move_is_quarantined PASSED [ 76%]
src-python/tests/storage/test_recycle.py::test_busy_and_startup_gate PASSED [ 78%]
src-python/tests/storage/test_recycle.py::test_stream_lease_until_body_end PASSED [ 81%]
src-python/tests/storage/test_recycle.py::test_http_contract_and_catalog PASSED [ 84%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[/absolute] PASSED [ 86%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[../escape] PASSED [ 89%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[exports\\cube] PASSED [ 92%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[C:/escape] PASSED [ 94%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[exports/../projects] PASSED [ 97%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[./exports] PASSED [100%]

============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 38 passed, 1 warning in 14.43s ========================
```

## 裁定后定向回归

取数命令（本机实际执行；完整原文见 [reimport-ruling-targeted.txt](E:/AI_Agent/milestone25/evidence/B/reimport-ruling-targeted.txt)）：

```powershell
$env:PYTHONIOENCODING='utf-8'; $task25Tmp=Join-Path $env:TEMP 't25br'; New-Item -ItemType Directory -Force -Path $task25Tmp | Out-Null; $env:PYTEST_DEBUG_TEMPROOT=$task25Tmp; if ((Get-PSDrive C).Free -lt 3GB) { throw 'C free space below required 3GiB' }
& .venv/Scripts/python.exe -m pytest src-python/tests/storage/test_recycle.py src-python/tests/data/test_api.py -q
```

```text
.....................................................                    [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
53 passed, 1 warning in 25.74s
```

## 开工 Rust 原文

取数命令（本机实际执行；完整原文见 [before-Rust.txt](E:/AI_Agent/milestone25/evidence/B/before-Rust.txt)）：

```powershell
$env:CARGO_HOME='E:\AI_Agent\.cargo-home'; $env:CARGO_TARGET_DIR='E:\AI_Agent\src-tauri\target'; $env:CARGO_NET_OFFLINE='true'
Set-Location E:/AI_Agent/src-tauri
cargo test
```

```text
Compiling proc-macro2 v1.0.107
   Compiling unicode-ident v1.0.27
   Compiling quote v1.0.47
   Compiling windows-link v0.2.1
   Compiling serde_core v1.0.229
   Compiling cfg-if v1.0.5
   Compiling memchr v2.8.3
   Compiling itoa v1.0.18
   Compiling litemap v0.8.3
   Compiling writeable v0.6.4
   Compiling siphasher v1.0.4
   Compiling utf8_iter v1.0.4
   Compiling icu_normalizer_data v2.3.0
   Compiling icu_properties_data v2.3.0
   Compiling fastrand v2.5.0
   Compiling stable_deref_trait v1.2.1
   Compiling zmij v1.0.23
   Compiling smallvec v1.16.3
   Compiling thiserror v2.0.21
   Compiling bytes v1.12.1
   Compiling parking_lot_core v0.9.12
   Compiling serde v1.0.229
   Compiling num-conv v0.2.2
   Compiling time-core v0.1.9
   Compiling log v0.4.34
   Compiling phf_shared v0.13.1
   Compiling scopeguard v1.2.0
   Compiling deranged v0.5.9
   Compiling strsim v0.11.1
   Compiling ident_case v1.0.1
   Compiling lock_api v0.4.14
   Compiling powerfmt v0.2.1
   Compiling typeid v1.0.3
   Compiling phf_generator v0.13.1
   Compiling winnow v1.0.4
   Compiling windows-sys v0.61.2
   Compiling phf_codegen v0.13.1
   Compiling autocfg v1.5.1
   Compiling toml_writer v1.1.3+spec-1.1.0
   Compiling erased-serde v0.4.10
   Compiling aho-corasick v1.1.5
   Compiling regex-syntax v0.8.11
   Compiling web-time v1.1.0
   Compiling new_debug_unreachable v1.0.6
   Compiling http v1.5.0
   Compiling toml_parser v1.1.5+spec-1.1.0
   Compiling fnv v1.0.7
   Compiling base64 v0.23.1
   Compiling dunce v1.0.5
   Compiling alloc-no-stdlib v3.0.0
   Compiling hashbrown v0.17.1
   Compiling precomputed-hash v0.1.1
   Compiling equivalent v1.0.3
   Compiling serde_json v1.0.154
   Compiling getrandom v0.4.3
   Compiling alloc-stdlib v0.3.0
   Compiling quick-xml v0.42.0
   Compiling parking_lot v0.12.5
   Compiling anyhow v1.0.104
   Compiling dtoa v1.0.11
   Compiling percent-encoding v2.3.2
   Compiling brotli-decompressor v6.0.1
   Compiling indexmap v1.9.3
   Compiling string_cache v0.9.0
   Compiling dtoa-short v0.3.5
   Compiling form_urlencoded v1.2.2
   Compiling indexmap v2.14.2
   Compiling tendril v0.5.1
   Compiling selectors v0.38.0
   Compiling glob v0.3.4
   Compiling libc v0.2.191
   Compiling syn v3.0.9
   Compiling syn v2.0.119
   Compiling string_cache_codegen v0.6.1
   Compiling ctor v1.0.13
   Compiling bitflags v2.13.2
   Compiling camino v1.2.6
   Compiling brotli v9.0.0
   Compiling servo_arc v0.4.3
   Compiling web_atoms v0.2.6
   Compiling schemars v0.8.22
   Compiling bit-vec v0.8.0
   Compiling hashbrown v0.12.3
   Compiling rustc-hash v2.1.3
   Compiling regex-automata v0.4.18
   Compiling bit-set v0.8.0
   Compiling time v0.3.55
   Compiling tauri-utils v2.10.2
   Compiling semver v1.0.28
   Compiling toml_datetime v1.1.2+spec-1.1.0
   Compiling serde_spanned v1.1.2
   Compiling uuid v1.28.0
   Compiling toml v1.1.8+spec-1.1.0
   Compiling cfb v0.14.0
   Compiling dyn-clone v1.0.20
   Compiling foldhash v0.2.0
   Compiling shlex v2.0.1
   Compiling find-msvc-tools v0.1.14
   Compiling version_check v0.9.5
   Compiling serde-untagged v0.1.9
   Compiling option-ext v0.2.0
   Compiling windows-strings v0.5.1
   Compiling windows-result v0.4.1
   Compiling pin-project-lite v0.2.17
   Compiling rustc_version v0.4.1
   Compiling infer v0.22.0
   Compiling cc v1.8.0
   Compiling heck v0.5.0
   Compiling simd-adler32 v0.3.10
   Compiling generic-array v0.14.7
   Compiling windows-threading v0.2.1
   Compiling once_cell v1.21.4
   Compiling adler2 v2.0.1
   Compiling static_vcruntime v3.0.0
   Compiling crc32fast v1.5.2
   Compiling time-macros v0.2.32
   Compiling raw-window-handle v0.6.2
   Compiling typenum v1.20.1
   Compiling miniz_oxide v0.9.1
   Compiling crossbeam-utils v0.8.23
   Compiling winapi-util v0.1.11
   Compiling winreg v0.56.0
   Compiling regex v1.13.1
   Compiling dirs-sys v0.5.0
   Compiling same-file v1.0.6
   Compiling dirs v7.0.0
   Compiling tracing-core v0.1.36
   Compiling miniz_oxide v0.8.9
   Compiling fdeflate v0.3.7
   Compiling walkdir v2.5.0
   Compiling cookie v0.18.2
   Compiling flate2 v1.1.10
   Compiling windows-version v0.1.7
   Compiling serde_derive_internals v0.29.1
   Compiling synstructure v0.14.0
   Compiling darling_core v0.24.1
   Compiling crypto-common v0.1.7
   Compiling block-buffer v0.10.4
   Compiling futures-core v0.3.34
   Compiling bitflags v1.3.2
   Compiling socket2 v0.6.5
   Compiling mio v1.2.4
   Compiling png v0.17.16
   Compiling digest v0.10.7
   Compiling crossbeam-channel v0.5.17
   Compiling vswhom-sys v0.1.3
   Compiling tauri-runtime v2.12.2
   Compiling cpufeatures v0.2.17
   Compiling tokio v1.53.3
   Compiling wry v0.57.0
   Compiling byteorder v1.5.0
   Compiling sha2 v0.10.9
   Compiling png v0.18.1
   Compiling unicode-segmentation v1.13.3
   Compiling ico v0.5.0
   Compiling getrandom v0.3.4
   Compiling tauri-runtime-wry v2.12.2
   Compiling muda v0.20.0
   Compiling windows_x86_64_msvc v0.53.1
   Compiling futures-sink v0.3.34
   Compiling window-vibrancy v0.8.1
   Compiling http-body v1.1.0
   Compiling futures-task v0.3.34
   Compiling vswhom v0.1.0
   Compiling httparse v1.10.1
   Compiling futures-io v0.3.34
   Compiling embed-resource v3.0.12
   Compiling slab v0.4.12
   Compiling mime v0.3.17
   Compiling tower-service v0.3.3
   Compiling try-lock v0.2.5
   Compiling sync_wrapper v1.0.2
   Compiling num-traits v0.2.19
   Compiling windows-targets v0.53.5
   Compiling want v0.3.2
   Compiling tower-layer v0.3.3
   Compiling atomic-waker v1.1.2
   Compiling rfd v0.16.0
   Compiling windows-sys v0.60.2
   Compiling tauri-winres v0.3.6
   Compiling futures-util v0.3.34
   Compiling futures-channel v0.3.34
   Compiling ipnet v2.12.2
   Compiling http-body-util v0.1.5
   Compiling open v5.4.4
   Compiling zerofrom-derive v0.1.8
   Compiling yoke-derive v0.8.4
   Compiling zerovec-derive v0.11.6
   Compiling displaydoc v0.2.7
   Compiling serde_derive v1.0.229
   Compiling thiserror-impl v2.0.21
   Compiling phf_macros v0.13.1
   Compiling derive_more-impl v2.1.1
   Compiling cssparser-macros v0.7.1
   Compiling schemars_derive v0.8.22
   Compiling windows-implement v0.60.2
   Compiling windows-interface v0.59.3
   Compiling tracing-attributes v0.1.31
   Compiling webview2-com-macros v0.8.1
   Compiling darling_macro v0.24.1
   Compiling serialize-to-javascript-impl v0.1.2
   Compiling serde_repr v0.1.21
   Compiling phf v0.13.1
   Compiling cssparser v0.37.0
   Compiling windows-core v0.62.2
   Compiling darling v0.24.1
   Compiling derive_more v2.1.1
   Compiling zerofrom v0.1.8
   Compiling serde_with_macros v3.24.0
   Compiling yoke v0.8.3
   Compiling webview2-com-sys v0.39.1
   Compiling tracing v0.1.44
   Compiling zerovec v0.11.8
   Compiling zerotrie v0.2.5
   Compiling windows-numerics v0.3.1
   Compiling windows-collections v0.3.2
   Compiling windows-future v0.3.2
   Compiling softbuffer v0.4.8
   Compiling chrono v0.4.45
   Compiling markup5ever v0.39.0
   Compiling tinystr v0.8.4
   Compiling potential_utf v0.1.6
   Compiling html5ever v0.39.0
   Compiling windows v0.62.2
   Compiling icu_collections v2.3.0
   Compiling serde_with v3.24.0
   Compiling icu_locale_core v2.3.0
   Compiling tower v0.5.3
   Compiling hyper v1.12.0
   Compiling cargo-platform v0.1.9
   Compiling jsonptr v0.7.1
   Compiling dom_query v0.28.0
   Compiling plist v1.10.1
   Compiling cargo_toml v1.0.1
   Compiling dpi v0.1.2
   Compiling cargo_metadata v0.19.2
   Compiling keyboard-types v0.8.3
   Compiling serialize-to-javascript v0.1.2
   Compiling hyper-util v0.1.21
   Compiling icu_provider v2.3.1
   Compiling json-patch v4.2.0
   Compiling icu_normalizer v2.3.0
   Compiling icu_properties v2.3.0
   Compiling idna_adapter v1.2.2
   Compiling idna v1.1.0
   Compiling url v2.5.8
   Compiling urlpattern v0.6.0
   Compiling tower-http v0.6.11
   Compiling reqwest v0.13.5
   Compiling tauri-build v2.7.3
   Compiling tauri-plugin v2.7.2
   Compiling tauri-codegen v2.7.3
   Compiling tauri v2.12.4
   Compiling tauri-plugin-fs v2.7.1
   Compiling tauri-macros v2.7.3
   Compiling tauri-plugin-opener v2.7.2
   Compiling tauri-plugin-dialog v2.8.3
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
   Compiling tao v0.37.1
   Compiling webview2-com v0.39.1
   Compiling tauri-plugin-single-instance v2.5.4
    Finished `test` profile [unoptimized + debuginfo] target(s) in 1m 15s
     Running unittests src\lib.rs (target\debug\deps\spectrum_agent-fc5a2225eca9e0bc.exe)

running 48 tests
test datasets_dev::tests::no_generic_host_port_path_or_method_can_be_deserialized ... ok
test annotation::tests::parameter_edges_and_unicode_note_match_http_contract ... ok
test annotation::tests::identifiers_cannot_escape_and_version_numbers_are_not_uuids ... ok
test annotation::tests::bad_types_lengths_and_out_of_range_parameters_are_rejected ... ok
test annotation::tests::no_free_url_host_port_path_or_method_can_enter_any_operation ... ok
test annotation::tests::only_the_supplied_nonzero_handshake_port_is_used ... ok
test datasets_dev::tests::preview_legacy_url_is_unchanged_and_optional_fields_allow_rgb_without_band ... ok
test annotation::tests::project_query_is_strict_then_lowercase_but_dataset_path_is_unchanged ... ok
test datasets_dev::tests::all_operations_use_the_handshake_port_and_fixed_namespace ... ok
test annotation::tests::four_management_operations_have_literal_paths_methods_and_bodies ... ok
test annotation::tests::all_nine_operations_have_exact_paths_methods_and_bodies ... ok
test annotation::tests::omitted_parameters_stay_omitted_and_all_prompt_geometries_are_typed ... ok
test annotation::tests::unknown_operations_and_fields_are_structured_and_never_reflect_input ... ok
test datasets_dev::tests::spectra_mean_has_fixed_post_path_typed_region_and_uuid_guard ... ok
test health::route_tests::closed_routes_always_use_numeric_loopback_and_literal_paths ... ok
test preprocess::tests::actual_generation_guard_used_by_command_rejects_stale_or_nonready ... ok
test models::tests::new_ops_reject_proxy_fields_invalid_stages_and_all_id_traversal ... ok
test models::tests::registry_inference_six_fixed_operations ... ok
test models::tests::fixed_operations_and_methods ... ok
test preprocess::tests::all_twelve_destinations_methods_and_exact_bodies ... ok
test preprocess::tests::four_uuid_error_codes_cover_every_identifier_field ... ok
test preprocess::tests::manual_base64_matches_rfc4648_vectors ... ok
test preprocess::tests::builder_sets_three_hundred_seconds_without_waiting ... ok
test preprocess::tests::json_success_is_unchanged_and_post_body_is_forwarded ... ok
test annotation::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test datasets_dev::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test preprocess::tests::malformed_http_envelope_uses_generic_error ... ok
test preprocess::tests::unknown_fields_ops_types_artifact_values_and_free_destinations_are_rejected ... ok
test preprocess::tests::uuid_copy_and_port_boundary_preserve_closed_destination ... ok
test preprocess::tests::redirects_are_not_followed ... ok
test preprocess::tests::binary_payload_and_wrapper_filename_are_also_sensitive_checked ... ok
test preprocess::tests::only_204_maps_empty_body_to_null_not_200 ... ok
test preprocess::tests::raw_and_canonical_tokens_never_cross_bridge ... ok
test preprocess::tests::structured_http_error_preserves_three_fields ... ok
test annotation::tests::label_body_limit_counts_serialized_utf8_and_business_validation_stays_in_python ... ok
test annotation::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test preprocess::tests::report_stays_json_and_nonartifact_binary_is_rejected ... ok
test datasets_dev::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test preprocess::tests::identity_checks_precede_http_status_and_body ... ok
test models::tests::six_new_ops_reach_loopback_with_native_auth_and_exact_bodies ... ok
test annotation::tests::response_identity_precedes_status_and_body ... ok
test datasets_dev::tests::response_identity_precedes_status_and_body ... ok
test preprocess::tests::binary_artifact_roundtrips_and_keeps_filename ... ok
test datasets_dev::tests::declared_and_streaming_response_limits_are_enforced ... ok
test preprocess::tests::declared_and_streaming_limits_reject_above_eight_mib ... ok
test annotation::tests::declared_and_streaming_response_limits_are_enforced ... ok
test models::tests::rejects_general_proxy_extra_fields_traversal_and_oversize ... ok
test annotation::tests::an_exactly_eight_mib_json_response_is_allowed ... ok

test result: ok. 48 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.21s

     Running unittests src\main.rs (target\debug\deps\spectrum_agent-9760c85afe553455.exe)

running 8 tests
test boot::tests::before_timeout_wait_and_first_attempt_precedes_give_up ... ok
test exports_tests::export_folder_rejects_paths_and_malformed_ids ... ok
test exports_tests::export_folder_is_scoped_to_a_canonical_cube_uuid ... ok
test boot::tests::reload_boundary_4999_5000_and_5001_ms ... ok
test boot_monitor_tests::reload_budget_is_independent_and_activations_do_not_reset_it ... ok
test boot::tests::healthy_document_always_waits_across_generations ... ok
test boot::tests::final_timeout_is_fifteen_seconds_from_window_shown ... ok
test boot_monitor_tests::engine_retry_keeps_healthy_document_until_real_navigation ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\agent_settings_forward.rs (target\debug\deps\agent_settings_forward-33848812934a45f0.exe)

running 10 tests
test both_commands_reject_stale_generation_or_non_ready_phase ... ok
test settings_only_existing_get_put_operations_and_no_key_in_config ... ok
test workspace_events_keep_only_bound_scalar_references ... ok
test agent_three_operations_and_two_body_shapes_have_literal_routes ... ok
test whitelist_rejects_paths_methods_and_mixed_message_shapes ... ok
test http_errors_keep_status_and_envelope_redirects_not_followed ... ok
test settings_key_and_escaped_credentials_never_cross_error_or_success_envelopes ... ok
test identity_is_checked_before_status_length_and_body_for_both_commands ... ok
test sse_empty_done_suspended_human_check_and_error_close ... ok
test declared_and_streaming_limits_are_enforced_for_both_commands ... ok

test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s

     Running tests\annotations_draft_forward.rs (target\debug\deps\annotations_draft_forward-07265277f3718ab2.exe)

running 8 tests
test paths_methods_candidates_and_extra_fields_are_rejected ... ok
test six_literal_routes_and_methods ... ok
test binary_requires_octet_stream ... ok
test http_errors_and_redirects_preserve_status_and_context ... ok
test identity_precedes_status_body_and_limit ... ok
test raw_and_canonical_credentials_never_escape ... ok
test declared_and_streamed_limits_json_and_binary ... ok
test binary_exact_limit_and_base64_padding ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.84s

     Running tests\causality.rs (target\debug\deps\causality-36e4b6d833a263b9.exe)

running 2 tests
test midnight_files_and_preexisting_partial_line_are_handled_without_fallback ... ok
test only_new_complete_lines_with_own_integer_pid_in_utc_window_can_be_cause ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.06s

     Running tests\contracts.rs (target\debug\deps\contracts-6e34dbf97624c6bb.exe)

running 6 tests
test all_transition_pairs_and_stopping_terminal_rule ... ok
test late_generation_and_expected_exit_cannot_fail_current_attempt ... ok
test valid_handshake_values_and_integer_utc_comparison ... ok
test exact_fields_and_top_level_are_enforced ... ok
test times_reject_nonexistent_dates_leap_seconds_and_non_millisecond_formats ... ok
test metadata_types_bounds_and_exact_strings_are_enforced ... ok

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\dev_identity.rs (target\debug\deps\dev_identity-6600fcd409e08ea7.exe)

running 1 test
test same_job_creation_time_and_live_process_are_all_required ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\dev_lifecycle.rs (target\debug\deps\dev_lifecycle-e7b10eb393a2d273.exe)

running 1 test
test real_venv_dual_pid_job_cleanup_and_stale_handshake_recovery ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 6.72s

     Running tests\engine_path.rs (target\debug\deps\engine_path-4dbb2bb02eb71cdc.exe)

running 1 test
test constructor_precedes_resource_and_rejects_non_engine_or_relative_paths ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\models_forward.rs (target\debug\deps\models_forward-ab37dcf260347516.exe)

running 6 tests
test coefficient_requests_reject_invalid_missing_and_extra_fields_before_network ... ok
test refuses_extra_method_path_and_traversal_before_network ... ok
test registered_coefficients_reach_fake_engine_with_native_identity ... ok
test rejects_identity_and_sensitive_response_preserves_structured_errors ... ok
test fixed_model_operations_reach_fake_engine_with_native_identity ... ok
test bounds_responses_and_checks_decoded_secrets ... ok

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.18s

     Running tests\supervisor_stubs.rs (target\debug\deps\supervisor_stubs-83764e59d4e58d2f.exe)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\win32_failures.rs (target\debug\deps\win32_failures-62b5ecc33cd4760b.exe)

running 3 tests
test success_closes_thread_immediately_and_cleanup_is_idempotent ... ok
test five_injected_failures_use_correct_termination_wait_and_exact_handle_counts ... ok
test unconfirmed_cleanup_is_preserved_and_blocks_retry ... ok

test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.06s

   Doc-tests spectrum_agent

running 1 test
test src\health.rs - health::HealthClient::smoke (line 101) - compile fail ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.17s
```

## 终值 Rust 原文

取数命令（本机实际执行；完整原文见 [Rust-after.txt](E:/AI_Agent/milestone25/evidence/B/Rust-after.txt)）：

```powershell
$env:CARGO_HOME='E:\AI_Agent\.cargo-home'; $env:CARGO_TARGET_DIR='E:\AI_Agent\src-tauri\target'; $env:CARGO_NET_OFFLINE='true'
Set-Location E:/AI_Agent/src-tauri
cargo test
```

```text
Finished `test` profile [unoptimized + debuginfo] target(s) in 0.39s
     Running unittests src\lib.rs (target\debug\deps\spectrum_agent-fc5a2225eca9e0bc.exe)

running 54 tests
test annotation::tests::identifiers_cannot_escape_and_version_numbers_are_not_uuids ... ok
test annotation::tests::parameter_edges_and_unicode_note_match_http_contract ... ok
test annotation::tests::all_nine_operations_have_exact_paths_methods_and_bodies ... ok
test annotation::tests::project_query_is_strict_then_lowercase_but_dataset_path_is_unchanged ... ok
test annotation::tests::bad_types_lengths_and_out_of_range_parameters_are_rejected ... ok
test datasets_dev::tests::delete_contract ... ok
test annotation::tests::unknown_operations_and_fields_are_structured_and_never_reflect_input ... ok
test annotation::tests::omitted_parameters_stay_omitted_and_all_prompt_geometries_are_typed ... ok
test annotation::tests::four_management_operations_have_literal_paths_methods_and_bodies ... ok
test annotation::tests::only_the_supplied_nonzero_handshake_port_is_used ... ok
test datasets_dev::tests::catalog_contract ... ok
test annotation::tests::no_free_url_host_port_path_or_method_can_enter_any_operation ... ok
test datasets_dev::tests::delete_preview_contract ... ok
test datasets_dev::tests::import_confirmation_defaults_false ... ok
test datasets_dev::tests::no_generic_host_port_path_or_method_can_be_deserialized ... ok
test datasets_dev::tests::all_operations_use_the_handshake_port_and_fixed_namespace ... ok
test datasets_dev::tests::preview_legacy_url_is_unchanged_and_optional_fields_allow_rgb_without_band ... ok
test datasets_dev::tests::restore_contract ... ok
test models::tests::registry_inference_six_fixed_operations ... ok
test datasets_dev::tests::spectra_mean_has_fixed_post_path_typed_region_and_uuid_guard ... ok
test datasets_dev::tests::recycle_list_contract ... ok
test models::tests::fixed_operations_and_methods ... ok
test models::tests::new_ops_reject_proxy_fields_invalid_stages_and_all_id_traversal ... ok
test preprocess::tests::actual_generation_guard_used_by_command_rejects_stale_or_nonready ... ok
test health::route_tests::closed_routes_always_use_numeric_loopback_and_literal_paths ... ok
test preprocess::tests::all_twelve_destinations_methods_and_exact_bodies ... ok
test preprocess::tests::four_uuid_error_codes_cover_every_identifier_field ... ok
test preprocess::tests::manual_base64_matches_rfc4648_vectors ... ok
test annotation::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test preprocess::tests::builder_sets_three_hundred_seconds_without_waiting ... ok
test datasets_dev::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test preprocess::tests::json_success_is_unchanged_and_post_body_is_forwarded ... ok
test preprocess::tests::malformed_http_envelope_uses_generic_error ... ok
test preprocess::tests::unknown_fields_ops_types_artifact_values_and_free_destinations_are_rejected ... ok
test preprocess::tests::binary_payload_and_wrapper_filename_are_also_sensitive_checked ... ok
test annotation::tests::label_body_limit_counts_serialized_utf8_and_business_validation_stays_in_python ... ok
test preprocess::tests::redirects_are_not_followed ... ok
test preprocess::tests::uuid_copy_and_port_boundary_preserve_closed_destination ... ok
test preprocess::tests::structured_http_error_preserves_three_fields ... ok
test annotation::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test datasets_dev::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test preprocess::tests::raw_and_canonical_tokens_never_cross_bridge ... ok
test preprocess::tests::only_204_maps_empty_body_to_null_not_200 ... ok
test preprocess::tests::report_stays_json_and_nonartifact_binary_is_rejected ... ok
test datasets_dev::tests::response_identity_precedes_status_and_body ... ok
test models::tests::six_new_ops_reach_loopback_with_native_auth_and_exact_bodies ... ok
test preprocess::tests::identity_checks_precede_http_status_and_body ... ok
test annotation::tests::response_identity_precedes_status_and_body ... ok
test preprocess::tests::binary_artifact_roundtrips_and_keeps_filename ... ok
test annotation::tests::declared_and_streaming_response_limits_are_enforced ... ok
test preprocess::tests::declared_and_streaming_limits_reject_above_eight_mib ... ok
test datasets_dev::tests::declared_and_streaming_response_limits_are_enforced ... ok
test models::tests::rejects_general_proxy_extra_fields_traversal_and_oversize ... ok
test annotation::tests::an_exactly_eight_mib_json_response_is_allowed ... ok

test result: ok. 54 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.23s

     Running unittests src\main.rs (target\debug\deps\spectrum_agent-9760c85afe553455.exe)

running 8 tests
test boot::tests::before_timeout_wait_and_first_attempt_precedes_give_up ... ok
test boot::tests::final_timeout_is_fifteen_seconds_from_window_shown ... ok
test exports_tests::export_folder_is_scoped_to_a_canonical_cube_uuid ... ok
test boot_monitor_tests::reload_budget_is_independent_and_activations_do_not_reset_it ... ok
test exports_tests::export_folder_rejects_paths_and_malformed_ids ... ok
test boot::tests::reload_boundary_4999_5000_and_5001_ms ... ok
test boot_monitor_tests::engine_retry_keeps_healthy_document_until_real_navigation ... ok
test boot::tests::healthy_document_always_waits_across_generations ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\agent_settings_forward.rs (target\debug\deps\agent_settings_forward-33848812934a45f0.exe)

running 10 tests
test both_commands_reject_stale_generation_or_non_ready_phase ... ok
test settings_only_existing_get_put_operations_and_no_key_in_config ... ok
test whitelist_rejects_paths_methods_and_mixed_message_shapes ... ok
test agent_three_operations_and_two_body_shapes_have_literal_routes ... ok
test workspace_events_keep_only_bound_scalar_references ... ok
test http_errors_keep_status_and_envelope_redirects_not_followed ... ok
test settings_key_and_escaped_credentials_never_cross_error_or_success_envelopes ... ok
test sse_empty_done_suspended_human_check_and_error_close ... ok
test identity_is_checked_before_status_length_and_body_for_both_commands ... ok
test declared_and_streaming_limits_are_enforced_for_both_commands ... ok

test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.53s

     Running tests\annotations_draft_forward.rs (target\debug\deps\annotations_draft_forward-07265277f3718ab2.exe)

running 8 tests
test paths_methods_candidates_and_extra_fields_are_rejected ... ok
test six_literal_routes_and_methods ... ok
test binary_requires_octet_stream ... ok
test http_errors_and_redirects_preserve_status_and_context ... ok
test raw_and_canonical_credentials_never_escape ... ok
test identity_precedes_status_body_and_limit ... ok
test declared_and_streamed_limits_json_and_binary ... ok
test binary_exact_limit_and_base64_padding ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.80s

     Running tests\causality.rs (target\debug\deps\causality-36e4b6d833a263b9.exe)

running 2 tests
test midnight_files_and_preexisting_partial_line_are_handled_without_fallback ... ok
test only_new_complete_lines_with_own_integer_pid_in_utc_window_can_be_cause ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.05s

     Running tests\contracts.rs (target\debug\deps\contracts-6e34dbf97624c6bb.exe)

running 6 tests
test late_generation_and_expected_exit_cannot_fail_current_attempt ... ok
test valid_handshake_values_and_integer_utc_comparison ... ok
test all_transition_pairs_and_stopping_terminal_rule ... ok
test exact_fields_and_top_level_are_enforced ... ok
test metadata_types_bounds_and_exact_strings_are_enforced ... ok
test times_reject_nonexistent_dates_leap_seconds_and_non_millisecond_formats ... ok

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\dev_identity.rs (target\debug\deps\dev_identity-6600fcd409e08ea7.exe)

running 1 test
test same_job_creation_time_and_live_process_are_all_required ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\dev_lifecycle.rs (target\debug\deps\dev_lifecycle-e7b10eb393a2d273.exe)

running 1 test
test real_venv_dual_pid_job_cleanup_and_stale_handshake_recovery ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 6.34s

     Running tests\engine_path.rs (target\debug\deps\engine_path-4dbb2bb02eb71cdc.exe)

running 1 test
test constructor_precedes_resource_and_rejects_non_engine_or_relative_paths ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\models_forward.rs (target\debug\deps\models_forward-ab37dcf260347516.exe)

running 6 tests
test coefficient_requests_reject_invalid_missing_and_extra_fields_before_network ... ok
test refuses_extra_method_path_and_traversal_before_network ... ok
test registered_coefficients_reach_fake_engine_with_native_identity ... ok
test rejects_identity_and_sensitive_response_preserves_structured_errors ... ok
test fixed_model_operations_reach_fake_engine_with_native_identity ... ok
test bounds_responses_and_checks_decoded_secrets ... ok

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.18s

     Running tests\supervisor_stubs.rs (target\debug\deps\supervisor_stubs-83764e59d4e58d2f.exe)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\win32_failures.rs (target\debug\deps\win32_failures-62b5ecc33cd4760b.exe)

running 3 tests
test success_closes_thread_immediately_and_cleanup_is_idempotent ... ok
test five_injected_failures_use_correct_termination_wait_and_exact_handle_counts ... ok
test unconfirmed_cleanup_is_preserved_and_blocks_retry ... ok

test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.06s

   Doc-tests spectrum_agent

running 1 test
test src\health.rs - health::HealthClient::smoke (line 101) - compile fail ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.12s
```

## 开工 clippy

取数命令（本机实际执行；完整原文见 [before-clippy.txt](E:/AI_Agent/milestone25/evidence/B/before-clippy.txt)）：

```powershell
$env:CARGO_HOME='E:\AI_Agent\.cargo-home'; $env:CARGO_TARGET_DIR='E:\AI_Agent\src-tauri\target'; $env:CARGO_NET_OFFLINE='true'
cargo clippy --all-targets -- -D warnings
```

```text
Compiling phf_generator v0.13.1
    Checking serde_core v1.0.229
   Compiling parking_lot_core v0.9.12
   Compiling icu_normalizer_data v2.3.0
   Compiling icu_properties_data v2.3.0
   Compiling zmij v1.0.23
   Compiling serde_spanned v1.1.2
   Compiling toml_datetime v1.1.2+spec-1.1.0
   Compiling getrandom v0.4.3
   Compiling thiserror v2.0.21
   Compiling form_urlencoded v1.2.2
   Compiling zerofrom v0.1.8
   Compiling typeid v1.0.3
   Compiling plist v1.10.1
   Compiling serde_with v3.24.0
   Compiling anyhow v1.0.104
   Compiling libc v0.2.191
    Checking windows-core v0.62.2
   Compiling yoke v0.8.3
   Compiling phf_codegen v0.13.1
   Compiling string_cache_codegen v0.6.1
   Compiling uuid v1.28.0
   Compiling erased-serde v0.4.10
   Compiling vswhom-sys v0.1.3
   Compiling parking_lot v0.12.5
   Compiling toml v1.1.8+spec-1.1.0
   Compiling phf_macros v0.13.1
   Compiling serde_json v1.0.154
   Compiling vswhom v0.1.0
   Compiling zerovec v0.11.8
   Compiling zerotrie v0.2.5
   Compiling selectors v0.38.0
   Compiling crc32fast v1.5.2
   Compiling string_cache v0.9.0
   Compiling webview2-com-sys v0.39.1
   Compiling cfb v0.14.0
    Checking windows-future v0.3.2
    Checking windows-collections v0.3.2
    Checking windows-numerics v0.3.1
   Compiling flate2 v1.1.10
   Compiling serde-untagged v0.1.9
   Compiling web_atoms v0.2.6
    Checking tracing v0.1.44
    Checking crossbeam-utils v0.8.23
    Checking cookie v0.18.2
   Compiling tinystr v0.8.4
   Compiling potential_utf v0.1.6
   Compiling sha2 v0.10.9
   Compiling png v0.17.16
   Compiling png v0.18.1
   Compiling phf v0.13.1
   Compiling icu_collections v2.3.0
   Compiling icu_locale_core v2.3.0
   Compiling jsonptr v0.7.1
   Compiling cargo_metadata v0.19.2
   Compiling infer v0.22.0
   Compiling embed-resource v3.0.12
   Compiling cargo_toml v1.0.1
   Compiling cssparser v0.37.0
    Checking windows v0.62.2
    Checking crossbeam-channel v0.5.17
   Compiling json-patch v4.2.0
   Compiling tauri-winres v0.3.6
    Checking softbuffer v0.4.8
    Checking getrandom v0.3.4
    Checking windows_x86_64_msvc v0.53.1
    Checking httparse v1.10.1
   Compiling ico v0.5.0
    Checking windows-targets v0.53.5
    Checking num-traits v0.2.19
    Checking serde v1.0.229
    Checking icu_provider v2.3.1
    Checking bitflags v2.13.2
    Checking hyper v1.12.0
    Checking windows-sys v0.60.2
    Checking icu_properties v2.3.0
   Compiling markup5ever v0.39.0
    Checking icu_normalizer v2.3.0
   Compiling html5ever v0.39.0
    Checking dpi v0.1.2
    Checking keyboard-types v0.8.3
    Checking chrono v0.4.45
    Checking serialize-to-javascript v0.1.2
    Checking hyper-util v0.1.21
   Compiling dom_query v0.28.0
    Checking idna_adapter v1.2.2
    Checking idna v1.1.0
    Checking muda v0.20.0
    Checking url v2.5.8
    Checking urlpattern v0.6.0
    Checking tower-http v0.6.11
    Checking rfd v0.16.0
   Compiling schemars v0.8.22
    Checking reqwest v0.13.5
    Checking tauri-utils v2.10.2
   Compiling tauri-build v2.7.3
   Compiling tauri-plugin v2.7.2
   Compiling tauri-codegen v2.7.3
   Compiling tauri v2.12.4
   Compiling tauri-macros v2.7.3
   Compiling tauri-plugin-fs v2.7.1
   Compiling tauri-plugin-dialog v2.8.3
   Compiling tauri-plugin-opener v2.7.2
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Checking tao v0.37.1
    Checking webview2-com v0.39.1
    Checking wry v0.57.0
    Checking tauri-runtime v2.12.2
    Checking tauri-runtime-wry v2.12.2
    Checking tauri-plugin-single-instance v2.5.4
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 44.60s
```

## 终值 clippy

取数命令（本机实际执行；完整原文见 [clippy-after.txt](E:/AI_Agent/milestone25/evidence/B/clippy-after.txt)）：

```powershell
$env:CARGO_HOME='E:\AI_Agent\.cargo-home'; $env:CARGO_TARGET_DIR='E:\AI_Agent\src-tauri\target'; $env:CARGO_NET_OFFLINE='true'
cargo clippy --all-targets -- -D warnings
```

```text
Checking spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 2.04s
```

## 开工 build

取数命令（本机实际执行；完整原文见 [before-build.txt](E:/AI_Agent/milestone25/evidence/B/before-build.txt)）：

```powershell
npm run build
```

```text
> spectrum-agent@0.1.0 build
> tsc --noEmit && vite build

vite v8.3.4 building client environment for production...
transforming...
✓ 84 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.37 kB │ gzip:   0.29 kB
dist/assets/index-BR5FnqT3.css   24.92 kB │ gzip:   5.38 kB
dist/assets/index-PDGzAD1A.js   384.13 kB │ gzip: 121.40 kB

✓ built in 1.35s
```

## 终值 build

取数命令（本机实际执行；完整原文见 [build-after.txt](E:/AI_Agent/milestone25/evidence/B/build-after.txt)）：

```powershell
npm run build
```

```text
> spectrum-agent@0.1.0 build
> tsc --noEmit && vite build

vite v8.3.4 building client environment for production...
transforming...
✓ 84 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.37 kB │ gzip:   0.29 kB
dist/assets/index-BR5FnqT3.css   24.92 kB │ gzip:   5.38 kB
dist/assets/index-C0A0v0oZ.js   384.42 kB │ gzip: 121.52 kB

✓ built in 135ms
```

## 守卫独立探针复核

取数命令（本机实际执行；完整原文见 [guard-probe-after.txt](E:/AI_Agent/milestone25/evidence/B/guard-probe-after.txt)）：

```powershell
& .venv/Scripts/python.exe milestone25/evidence/A/storage_probe.py
```

```text
STORAGE_SELF_CHECK_FAILED
{
  "fixture": "E:\\AI_Agent\\.runtime\\task25\\storage-probe-45139675eeb44e86948a6ed638b4c143",
  "imported_id": "caf7cc64-d5da-4494-938d-c42eb3df1baa",
  "startup_order": [
    "directories_created",
    "self_check",
    "business_ready",
    "recycle_reconcile_started",
    "recycle_business_ready"
  ],
  "source_before": [
    {
      "path": "original.hdr",
      "sha256": "872a3e0a6ca386353e16c53d47f8a3346e363e6abc6103f8d84619130348ecbf",
      "mtime_ns": 1793803288710234500
    },
    {
      "path": "original.img",
      "sha256": "a46b67c8fb1c4c35fdfc8387c647f8c442a84e1520334a92a127f740b4c1dd5c",
      "mtime_ns": 1793803288711251000
    }
  ],
  "write_to_source": "WRITE_TO_SOURCE_DENIED",
  "delete_from_source": "WRITE_TO_SOURCE_DENIED",
  "source_overrides_whitelist": "WRITE_TO_SOURCE_DENIED",
  "guard_calls_for_one_audited_resolution": 1,
  "audit_while_business_writer_locked": "PASS",
  "injected_selfcheck_failure": "STORAGE_SELF_CHECK_FAILED",
  "business_after_failed_selfcheck": "STORAGE_SELF_CHECK_FAILED",
  "audit_decisions": {
    "ALLOW": 24,
    "DENY": 4
  },
  "audit_not_null_supply": {
    "write_audit": [
      "id",
      "ts",
      "action",
      "target_path",
      "decision",
      "reason",
      "deletion_id",
      "actor",
      "flushed_at"
    ],
    "deletion_audit": [
      "deletion_id",
      "action",
      "cube_id",
      "summary_json",
      "confirmed_by",
      "created_at"
    ]
  },
  "immutable_operations": {
    "write_audit.UPDATE": "APPEND_ONLY_AUDIT",
    "write_audit.DELETE": "APPEND_ONLY_AUDIT",
    "deletion_audit.UPDATE": "APPEND_ONLY_AUDIT",
    "deletion_audit.DELETE": "APPEND_ONLY_AUDIT"
  },
  "source_after": [
    {
      "path": "original.hdr",
      "sha256": "872a3e0a6ca386353e16c53d47f8a3346e363e6abc6103f8d84619130348ecbf",
      "mtime_ns": 1793803288710234500
    },
    {
      "path": "original.img",
      "sha256": "a46b67c8fb1c4c35fdfc8387c647f8c442a84e1520334a92a127f740b4c1dd5c",
      "mtime_ns": 1793803288711251000
    }
  ],
  "source_unchanged": true,
  "bounded_buffer": {
    "capacity": 2,
    "overflow_count": 1,
    "warnings": [
      "AUDIT_BUFFER_OVERFLOW"
    ],
    "flushed_rows": 2,
    "persistent_alert": [
      [
        "AUDIT_BUFFER_OVERFLOW",
        "EVICTED_RECORDS:1"
      ]
    ]
  }
}
```

## 生命周期与启动门禁现场 JSON

取数命令（本机实际执行；完整原文见 [lifecycle-probe.txt](E:/AI_Agent/milestone25/evidence/B/lifecycle-probe.txt)）：

```powershell
& .venv/Scripts/python.exe milestone25/evidence/B/lifecycle_probe.py
```

```text
E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
{
  "mode": "fresh synthetic ENVI + real SQLite/FK + guarded filesystem + authenticated TestClient",
  "runtime_root": "E:\\AI_Agent\\.runtime\\task25\\b-lifecycle-69560c54d2",
  "cube_id": "486620e2-6514-4261-9bcf-7e9a490a2e9f",
  "impact": {
    "cube_id": "486620e2-6514-4261-9bcf-7e9a490a2e9f",
    "annotation_versions": 1,
    "preprocess_runs": 1,
    "training_runs": 1,
    "inference_runs": 1,
    "directories": [
      {
        "path": "annotations/486620e2-6514-4261-9bcf-7e9a490a2e9f/v1",
        "bytes": 263
      },
      {
        "path": "exports/486620e2-6514-4261-9bcf-7e9a490a2e9f",
        "bytes": 273
      },
      {
        "path": "inferences/71eefdde-51ff-4110-9feb-95f939c2de02",
        "bytes": 55
      },
      {
        "path": "models/bd17924a-da50-40ef-89f1-434103dae2a4",
        "bytes": 54
      },
      {
        "path": "preprocessed/486620e2-6514-4261-9bcf-7e9a490a2e9f/45429b7a-80bc-4896-8de3-e321ec0d56ce",
        "bytes": 98
      }
    ],
    "total_bytes": 743
  },
  "source_phases": {
    "before": [
      {
        "path": "sample.hdr",
        "bytes": 174,
        "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772",
        "mtime_ns": 1793805583493471600
      },
      {
        "path": "sample.img",
        "bytes": 48,
        "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3",
        "mtime_ns": 1793805583493471600
      }
    ],
    "after_delete": [
      {
        "path": "sample.hdr",
        "bytes": 174,
        "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772",
        "mtime_ns": 1793805583493471600
      },
      {
        "path": "sample.img",
        "bytes": 48,
        "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3",
        "mtime_ns": 1793805583493471600
      }
    ],
    "after_restore": [
      {
        "path": "sample.hdr",
        "bytes": 174,
        "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772",
        "mtime_ns": 1793805583493471600
      },
      {
        "path": "sample.img",
        "bytes": 48,
        "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3",
        "mtime_ns": 1793805583493471600
      }
    ],
    "after_purge": [
      {
        "path": "sample.hdr",
        "bytes": 174,
        "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772",
        "mtime_ns": 1793805583493471600
      },
      {
        "path": "sample.img",
        "bytes": 48,
        "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3",
        "mtime_ns": 1793805583493471600
      }
    ]
  },
  "source_unchanged": true,
  "active_counts_after_delete": {
    "inference_artifact": 0,
    "inference_run": 0,
    "model_registry": 0,
    "metric": 0,
    "training_fold": 0,
    "model_artifact": 0,
    "training_run": 0,
    "sample_target": 0,
    "preprocess_artifact": 0,
    "preprocess_run": 0,
    "training_mat": 0,
    "annotation": 0,
    "sample_spectrum": 0,
    "annotation_version": 0,
    "annotation_draft": 0,
    "dataset_registry": 0
  },
  "active_counts_after_restore": {
    "inference_artifact": 1,
    "inference_run": 1,
    "model_registry": 1,
    "metric": 1,
    "training_fold": 1,
    "model_artifact": 1,
    "training_run": 1,
    "sample_target": 1,
    "preprocess_artifact": 1,
    "preprocess_run": 1,
    "training_mat": 1,
    "annotation": 1,
    "sample_spectrum": 1,
    "annotation_version": 1,
    "annotation_draft": 1,
    "dataset_registry": 1
  },
  "restored_id_unchanged": true,
  "purged": [
    "4059ef72-05a1-4310-afb7-3ddd99c93a2c"
  ],
  "deletion_audit": {
    "DELETE": 2,
    "PURGE": 1,
    "RESTORE": 1
  },
  "source_denials": [
    [
      "SOURCE_WRITE_PROBE",
      "DENY",
      "WRITE_TO_SOURCE_DENIED"
    ],
    [
      "DELETE",
      "DENY",
      "WRITE_TO_SOURCE_DENIED"
    ]
  ],
  "startup_gate": {
    "import": {
      "status": 503,
      "error": "RECYCLE_RECONCILIATION_REQUIRED"
    },
    "annotation": {
      "status": 503,
      "error": "RECYCLE_RECONCILIATION_REQUIRED"
    },
    "training": {
      "status": 503,
      "error": "RECYCLE_RECONCILIATION_REQUIRED"
    },
    "delete": {
      "status": 503,
      "error": "RECYCLE_RECONCILIATION_REQUIRED"
    }
  }
}
```

## 活跃 B / 回收 A 裁定后复测

取数命令（本机实际执行；完整原文见 [reimport-active-after-ruling.txt](E:/AI_Agent/milestone25/evidence/B/reimport-active-after-ruling.txt)）：

```powershell
& .venv/Scripts/python.exe milestone25/evidence/B/reimport_probe.py
```

```text
E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
{
  "authority": "eb1b25b",
  "mode": "fresh synthetic ENVI / real SQLite / storage guard",
  "old_id": "3304919a-7946-4e22-83cb-3a5dc0dabac5",
  "active_id": "7a763f67-9092-4b6b-a51e-da156314bff1",
  "without_confirm_new": {
    "id": "7a763f67-9092-4b6b-a51e-da156314bff1",
    "existing": true,
    "summary": {
      "total": 1,
      "imported": 0,
      "existing": 1
    }
  },
  "with_confirm_new": {
    "id": "7a763f67-9092-4b6b-a51e-da156314bff1",
    "existing": true,
    "summary": {
      "total": 1,
      "imported": 0,
      "existing": 1
    }
  }
}
```

## 环境现场

取数命令（本机实际执行；完整原文见 [environment.txt](E:/AI_Agent/milestone25/evidence/B/environment.txt)）：

```powershell
Get-Date -Format o; node --version; npm --version; .venv/Scripts/python.exe -c "import sys,sqlite3,tempfile; print(sys.version); print(sqlite3.sqlite_version); print(tempfile.gettempdir())"; rustc --version; cargo --version; Get-PSDrive C
```

```text
2026-11-04T22:49:29.5582616+08:00
v24.19.0
11.17.0
3.12.13 (main, May 10 2026, 19:35:37) [MSC v.1944 64 bit (AMD64)]
SQLite 3.50.4
OS_TEMP C:\Users\Administrator\AppData\Local\Temp
rustc 1.99.1 (58cf8f9c3 2026-10-13)
cargo 1.99.1 (5f94df478 2026-08-27)
C_FreeGiB=7.7691
```

## 开工生产写盘文件

取数命令（本机实际执行；完整原文见 [before-writer-files.txt](E:/AI_Agent/milestone25/evidence/B/before-writer-files.txt)）：

```powershell
grep -rln -E "[.]write_text[(]|[.]write_bytes[(]|np[.]save|savemat[(]|shutil[.]rmtree|[.]unlink[(]|[.]mkdir[(]|open_memmap" src-python/spectrumagent backend --include=*.py （排除 __pycache__ 与 /tests/ 后排序）
```

```text
backend/diagnostics.py
backend/handshake.py
backend/logging_config.py
backend/paths.py
backend/smoke.py
src-python/spectrumagent/agent/mat.py
src-python/spectrumagent/annotation/projection_io.py
src-python/spectrumagent/annotation/session.py
src-python/spectrumagent/api/registry.py
src-python/spectrumagent/modeling/inference.py
src-python/spectrumagent/modeling/run.py
src-python/spectrumagent/preprocess/recipes.py
src-python/spectrumagent/preprocess/run.py
src-python/spectrumagent/storage/guard.py
```

## 终值生产写盘文件

取数命令（本机实际执行；完整原文见 [writer-files-after.txt](E:/AI_Agent/milestone25/evidence/B/writer-files-after.txt)）：

```powershell
同上 grep 命令，生产文件数 = 输出行数
```

```text
backend/diagnostics.py
backend/handshake.py
backend/logging_config.py
backend/paths.py
backend/smoke.py
src-python/spectrumagent/agent/mat.py
src-python/spectrumagent/annotation/projection_io.py
src-python/spectrumagent/annotation/session.py
src-python/spectrumagent/api/registry.py
src-python/spectrumagent/modeling/inference.py
src-python/spectrumagent/modeling/run.py
src-python/spectrumagent/preprocess/recipes.py
src-python/spectrumagent/preprocess/run.py
src-python/spectrumagent/storage/guard.py
src-python/spectrumagent/storage/recycle.py
```

## 终值回收站写删出口

取数命令（本机实际执行；完整原文见 [recycle-writers.txt](E:/AI_Agent/milestone25/evidence/B/recycle-writers.txt)）：

```powershell
grep -rn -E "unlink|rmtree|[.]rename[(]|os[.]replace|storage[.]replace|[.]write_text[(]" src-python/spectrumagent/storage/recycle.py
```

```text
326:        storage.replace(source, destination)
332:            storage.rmtree(folder)
379:                    storage.resolve_write(folder / 'manifest.json', kind='RECYCLE_MANIFEST').write_text(encode(manifest), 'utf-8')
564:                        storage.rmtree(self.paths.trash / deletion)
```

## 既有 migrations 关联 cube 列

取数命令（本机实际执行；完整原文见 [before-cube-columns.txt](E:/AI_Agent/milestone25/evidence/B/before-cube-columns.txt)）：

```powershell
grep -nH -E "cube_ids? +TEXT" src-python/spectrumagent/{annotation,preprocess,modeling,agent}/migrations.py
```

```text
src-python/spectrumagent/annotation/migrations.py:51:  cube_id         TEXT NOT NULL,
src-python/spectrumagent/annotation/migrations.py:70:  cube_id     TEXT NOT NULL,
src-python/spectrumagent/annotation/migrations.py:89:  cube_id     TEXT NOT NULL,
src-python/spectrumagent/preprocess/migrations.py:35:  cube_id      TEXT NOT NULL,                -- 输入数据集（dataset_registry.id）
src-python/spectrumagent/modeling/migrations.py:4: id TEXT PRIMARY KEY, cube_ids TEXT NOT NULL, annotation_version_ids TEXT NOT NULL,
src-python/spectrumagent/modeling/migrations.py:33: cube_id TEXT NOT NULL REFERENCES dataset_registry(id),
src-python/spectrumagent/modeling/migrations.py:50: cube_id TEXT NOT NULL REFERENCES dataset_registry(id),
src-python/spectrumagent/agent/migrations.py:84:  cube_id            TEXT PRIMARY KEY REFERENCES dataset_registry(id),
src-python/spectrumagent/agent/migrations.py:101:  cube_id               TEXT NOT NULL,                        -- 服务端：confirm 入参
```

## B 段后锚点漂移记录

取数命令（本机实际执行；完整原文见 [anchors-after-B.txt](E:/AI_Agent/milestone25/evidence/B/anchors-after-B.txt)）：

```powershell
& .runtime/task25/B-current-opening/anchor-commands.ps1
```

```text
src/App.tsx:54:  const [records, setRecords] = useState<DatasetRecord[]>([]);
src/App.tsx:60:  const [selected, setSelected] = useState<DatasetRecord | null>(null);
src/App.tsx:85:    setWorkspace({}); setRecords([]); setRefreshVersions({}); setNavigation(null); setWorkspaceName(''); setPreviewCandidates({});
src/components/datasets/DatasetPanel.tsx:48:        setRecords(previous => mergeRecords(previous, result.all_datasets));
src/components/datasets/types.ts:15:  all_datasets: DatasetRecord[];
src/components/datasets/types.ts:37:export type DatasetTransport = {
src/components/datasets/types.ts:50:export function mergeRecords(previous: DatasetRecord[], incoming: DatasetRecord[]): DatasetRecord[] {
src/components/datasets/types.ts:51:  const merged = new Map(previous.map(record => [record.id, record]));
src/components/datasets/types.ts:52:  for (const record of incoming) merged.set(record.id, record);
src/components/datasets/types.ts:53:  return [...merged.values()];
src-python/spectrumagent/api/schemas.py:36:    all_datasets: list[DatasetRecord]
src/components/datasets/display_names.test.ts:14:test('G2 all_datasets refreshes a previously unique name without duplicating records', () => {
src-python/spectrumagent/api/registry.py:121:            db.execute("CREATE TABLE IF NOT EXISTS dataset_registry (id TEXT PRIMARY KEY, header_key TEXT NOT NULL, raw INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(header_key,raw))")
src-python/spectrumagent/api/registry.py:177:            active = db.execute('SELECT id,payload FROM dataset_registry WHERE header_key=? AND raw=?',
src-python/spectrumagent/api/registry.py:199:            db.execute('INSERT INTO dataset_registry (id,header_key,raw,payload,project_id) VALUES (?,?,?,?,?)',
src-python/spectrumagent/api/registry.py:231:            all_records = [batch_records.get(identifier) or DatasetRecord(id=identifier,
src-python/spectrumagent/api/registry.py:258:    def readable(self, identifier, raw=None):
src-python/spectrumagent/api/registry.py:262:            current = read_header(Path(stored.header_path), Path(stored.data_path), raw=mode)
src/components/datasets/api.ts:6:export type Request = { op: 'import'; path: string; raw: boolean; confirm_new?: boolean } | ({ op: 'preview'; id: string } & PreviewOptions)
src/components/datasets/api.ts:44:  const result = await open({ directory: true, multiple: true, filters: [{ name: 'Hyperspectral', extensions: ['hdr', 'img', 'raw', 'bin', 'json', 'txt'] }] });
src-tauri/src/datasets_dev.rs:51:#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
src-tauri/src/datasets_dev.rs:52:pub enum DatasetRequest {
backend/database.py:10:    connection.execute("PRAGMA foreign_keys=ON")
backend/paths.py:8:NAS_SOURCE_ROOT: Path | None = None
backend/paths.py:9:NAS_OUTPUT_ROOT: Path | None = None
backend/paths.py:40:    def database(self) -> Path:
backend/paths.py:44:    def snapshots(self) -> Path:
backend/paths.py:48:    def preprocessed(self) -> Path:
backend/paths.py:52:    def exports(self) -> Path:
src-python/spectrumagent/agent/state.py:166:        return json.loads(self.session(session_id)["context_json"])
src-python/spectrumagent/agent/state.py:173:            db.execute("UPDATE agent_session SET context_json=? WHERE id=?", (value, session_id))
src-python/spectrumagent/agent/llm.py:136:_DENY_TEXT = re.compile(r"[a-z]:|\\|/[^\s/]+|\.(?:img|hdr|mat)\b|\blabel_map\b", re.I)
src-python/spectrumagent/agent/mat.py:52:                if not path.resolve().is_relative_to(self.paths.exports.resolve()):
src-python/spectrumagent/agent/mat.py:88:        if relative.is_absolute() or ".." in relative.parts or "\\" in row["relative_path"] or ":" in row["relative_path"] or not path.resolve().is_relative_to(self.paths.exports.resolve()):
src-python/spectrumagent/agent/mat.py:190:            if not temporary.resolve().is_relative_to(self.paths.exports.resolve()):
src-python/spectrumagent/annotation/session.py:387:                        db.execute("DELETE FROM annotation WHERE version_id=?", (version_id,))
src-python/spectrumagent/annotation/session.py:388:                        db.execute("DELETE FROM sample_spectrum WHERE version_id=?", (version_id,))
src-python/spectrumagent/annotation/session.py:389:                        db.execute("DELETE FROM training_mat WHERE annotation_version_id=?", (version_id,))
src-python/spectrumagent/annotation/session.py:405:                    storage.rmtree(directory)
src-python/spectrumagent/modeling/migrations.py:68:    deferred = db.execute("PRAGMA defer_foreign_keys").fetchone()[0]
src-python/spectrumagent/modeling/migrations.py:69:    db.execute("SAVEPOINT modeling_132")
src-python/spectrumagent/modeling/migrations.py:81:                db.execute(f"INSERT INTO {name}_132 ({fields}) SELECT {fields} FROM {name}")
src-python/spectrumagent/modeling/migrations.py:82:            db.execute("PRAGMA defer_foreign_keys=ON")
src-python/spectrumagent/modeling/migrations.py:84:                db.execute(f"DROP TABLE {name}")
src-python/spectrumagent/modeling/migrations.py:86:                db.execute(f"ALTER TABLE {name}_132 RENAME TO {name}")
src-python/spectrumagent/modeling/migrations.py:97:            db.execute("PRAGMA defer_foreign_keys=ON")
src-python/spectrumagent/modeling/migrations.py:98:        db.execute("RELEASE modeling_132")
src-python/spectrumagent/modeling/migrations.py:101:        db.execute("RELEASE modeling_132")
src-python/spectrumagent/modeling/migrations.py:102:        db.execute(f"PRAGMA defer_foreign_keys={int(deferred)}")
src-python/spectrumagent/annotation/projection_io.py:21:    return paths.root / "projects" / str(UUID(str(project_id))) / "projection.json"
src-python/spectrumagent/annotation/projection_io.py:73:    root = paths.exports.resolve()
src-python/spectrumagent/annotation/projection_io.py:74:    folder = root / cube_id
src-python/spectrumagent/api/registry.py:219:                        db.execute("UPDATE dataset_registry SET payload=? WHERE id=?", (json.dumps(stored.as_dict(), ensure_ascii=False), row[0]))
backend/paths.py:56:    def trash(self) -> Path:
src-python/spectrumagent/storage/guard.py:329:def resolve_write(path, *, kind):
src-python/spectrumagent/storage/guard.py:333:def resolve_delete(path):
src-python/spectrumagent/storage/guard.py:337:def mkdir(path, *, parents=False, exist_ok=False):
src-python/spectrumagent/storage/guard.py:341:def unlink(path, *, missing_ok=False):
src-python/spectrumagent/storage/guard.py:345:def rmtree(path):
src-python/spectrumagent/storage/guard.py:349:def replace(source, destination):
```
