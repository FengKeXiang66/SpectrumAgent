# TASK-25 C 段交付：活跃目录、确认交互与项目路径设置

执行模式：Windows PowerShell，本地 .venv Python、Node 源码 glob、Rust debug 完整 test / all-targets clippy、tsc --noEmit + Vite。未安装依赖、未 push。本报告与 C 源码同一提交，提交号以收口 git log 为准。

权威卡为 3091c13（302 行）。本轮从 1383f3e 的干净工作区核验并启动开工基线；接口缺口按原始提示词「要改接口契约先停下问」上报，备卡方只提交文档 3091c13，用户明确解除即停。新增 settings 锚点已复核，直到开工 Python 完整基线结束都未改被测源码，因此两次文档版本之间源码仍同 d8bb622。执行方未改任务卡。before-contract-proposal.md 是已由 3091c13 解决的历史草稿，不表示当前仍阻断 C。

## 交付行为

- App 在 Ready / generation_id 下自动加载全部 catalog 分页；换代保留清空，再重新拉取。controller 同时校验代次和请求序号，旧成功、旧失败和已取消请求均不能覆盖当前列表。失败可见且可手动重试。
- records 改存 CatalogRecord 摘要，没有伪造完整数据集。失效源保留并标「源文件不可用」，查看 / 标注 / 预处理禁用，建模仅接受当前可用摘要。打开工作台前再读 catalog 校验可用性，随后 get 单个详情；不从旧完整 payload 接着计算。详情导航同样检查当前代次与选择序号。
- 导入仅把 result.datasets 接入当前集合；catalog 接管全局显示名刷新，只更新当前可见 id，不把未选择项铺进列表。all_datasets 和 mergeRecords 保留，G2 原测试未改。汇总采用真实 summary，三个已有项显示「本次选中 3 个（新增 0 / 已有 3）」。
- 活跃 / 已删除筛选、影响清单确认框、恢复确认与冲突原因均接通。删除确认前只调用 deletePreview；四类计数、目录、字节数、30 天可恢复及占用不立即释放全部可见。最终 delete / restore 仅从人点确认按钮后的路径调用；没有注册任何新 Agent 工具。取消或卸载会取消等待中的决定。
- 重新导入只在 REIMPORT_CONFIRMATION_REQUIRED 出现时显示默认选中的全新数据集选项，明确新 id、从头标注、旧份 30 天、双份空间；点确认才再次发送 confirm_new=true。活跃已有和 REIMPORT_ACTIVE_EXISTS 不弹该框、不自动重试。
- S11 展示回收站总字节数、条目数、各条目预计释放日期、隔离 / 不完整说明、到期启动清理及长任务推迟规则；禁运清单包含「NAS 路径与文件名」。已到期和 INCOMPLETE 条目禁止恢复入口。
- S03 独立源路径 / 输出根输入、浏览、程序只读徽标、项目默认保存、?src=/?out= 预填；两个路径都把 smb:// 归一成 UNC 字符串。S11 读取同一项目保存值与实际 data_root。当前支持与后续格式只用说明文字，没有新增格式入口。
- 严格按 §4.1 新增项目路径 GET/PUT，Python / Rust / TS / OpenAPI 同步。PUT body 仅两个非 null 字符串，project_id 仅路径参数；UUID、项目存在性、未知字段与类型错误均拒绝。空串表示未配置，GET output_enabled 始终是服务端 false，data_root 始终实际 paths.root。
- 路径只保存在独立 project_path_settings；PUT 只更新本地 SQLite，沿用受守卫的 connect_database，不读取 / 创建 / 修改两个配置路径，不启用输出根、不改变产物落盘。app.py:93/:110 前缀白名单未重复添加。
- 路径成功返回 UI 是必要能力，因此 Rust 对 PUT 的两个路径采用「错误响应不得回显」保护；成功设置响应允许展示路径。原凭据与身份 token 仍受全响应拒绝保护，且新增 JSON 字符串递归检查覆盖反斜杠转义。伪造 boot_id 在读取状态 / 解析响应之前拒绝。GET 无提交路径字段，后端项目错误和验证错误均不带路径。
- 项目路径未加入 LLM 上下文、工具出参或日志，safe_name 与 llm.py 的兜底未改。实际模型请求序列化使用 MockTransport 检查，不冒充真实外部模型调用；浏览器夹具也不冒充真实 NAS 连接。

## 持久化逐列供值与写目标

| 表 / 列 | 供值 | 写目标 |
|---|---|---|
| project_path_settings.project_id | 经 UUID 校验的 URL 参数，并验证 project 存在 | 本地 paths.database |
| source_path / output_root | PUT 两个 StrictStr，经 SMB 字符串归一；空串明确写入 | 仅作为 SQLite 值，不作可写根或文件目标 |
| updated_at | 服务端带时区 UTC 时间 | 同一短写事务 |

四列均显式供值，无 DEFAULT。GET 无行时返回两个空串，不创建源目录或输出目录。dataset_registry.payload 与 llm_settings 未混存；项目配置不加入 cube 回收链。

生产直接文件写点 grep 仍为 15 个文件，新 project_paths.py 没有直接文件系统写出口。新增表使用既有 connect_database（本地数据根）打开数据库；所有既有文件守卫代码未放宽。

## 回归与新增用例

| 执行模式 / 取数命令 | 开工 | 收口 |
|---|---|---|
| node --test "src/**/*.test.ts" | 223 pass / 0 fail | 241 pass / 0 fail，新增 18 |
| python -m pytest backend/tests src-python/tests --collect-only -q | 1544 collected | 1561 collected，新增 17 |
| python -m pytest backend/tests -q | 45 pass | 45 pass |
| python -m pytest src-python/tests -q | 1497 pass / 2 skip | 1514 pass / 2 skip |
| cargo test，按完整 stdout 数 test result | 13 组，全绿；主组 54 | 13 组，全绿；主组 54，agent_settings_forward 10→12 |
| cargo clippy --all-targets -- -D warnings | 0 error | 0 error |
| npm run build（含 tsc --noEmit） | 通过 | 通过 |
| 生产文件写点 grep / cube_ids? TEXT 定义 grep | 15 文件 / 9 行 | 15 文件 / 9 行 |

Python collected 与 pass 不混用：1561 = backend 45 + src 1514 + 原有 skip 2。开工 src 完整耗时 732.56s，收口 611.98s；Python 既有 6 条 warning 原文保留，未压制。Node 未裸跑，两个归档快照不进入发现域。

| 新增用例组 | 什么情况下会红 |
|---|---|
| catalog.test.ts，6 例 | 冷启动漏分页、隐藏失效源、旧代次成功 / 失败覆盖新列表、失败不提示或不能重试、三个已有项把全库铺入、显示名不刷新、空页造成死循环 |
| actions.test.ts，7 例 | 确认前删除、取消 / 卸载仍删除、消费 all_datasets、活跃项误弹新建确认、未点确认就重导入、竞态被静默复用、恢复拒绝原因缺失、INCOMPLETE / 到期项仍恢复、S11 缺占用或日期 |
| project-paths.test.ts，5 例 | SMB 或查询预填错误、两个输入互相覆盖、保存附带多余字段、浏览取消改值、S11 不显示保存值、错误时仍保存、卸载后旧请求更新、重复保存、IPC 目的操作错误 |
| test_project_paths.py，17 参数化执行项 | 空值 / 往返 / 列供值错误、未知字段 / null / 非字符串获准、非法 / 未知项目获准、SMB 未归一或凭据被回显、源哈希 / mtime / payload / guard 根变化、重启丢配置、日志 / 摘要 / LLM wire 泄漏、未认证仍保存 |
| Rust 新增 2 例 | GET/PUT URL / method / body 不精确、未知字段获准、成功设置无法展示路径、错误 JSON 转义路径泄漏、伪造 boot_id 获准 |

原有前端 223 项仍全过。两份源码连线测试的三处旧用例随真实行为调整：openScreen 接受摘要引用；workspace 更新移到 get / available 校验之后；S11 新增有真实请求的占用刷新按钮。保留原有断言意图并补强可用性和请求断言，没有删测试或为凑数改数量。G2 文件逐字未改。Python 旧用例均未改。

## 中间失败与环境记录

- 首轮旧 Node 为 217 pass / 6 fail，原因是旧测试用源码正则固定三处已改变的结构，以及循环生成按钮使显式导航锚点消失。按钮改回显式写法，三处结构断言更新为真实新语义后，223/223 通过。全部失败原文在 node-first.txt。
- 新增前端首轮 240 pass / 1 fail：设置 GET 失败时表单根本不渲染，测试却寻找禁用的提交按钮；改为断言提交入口不存在且调用保存不发请求。另一次 tsc 因测试对空数组 deepEqual 的类型收窄产生 never[]，改为不收窄类型的 length 断言。均为新测试修正，随后 241/241 与构建通过，失败原文保留。
- 主动运行的全库 cargo fmt --check 出现既有未格式化文件及新增代码差异，见 rust-format-first.txt；没有借机格式化其他模块。只对 C 修改的三个 Rust 文件执行 rustfmt，其单文件 --check 通过；本卡必跑 cargo test / clippy 均通过。
- 每轮 pytest 前都实际检查 C 盘 Free >= 3 GiB，否则 throw。开工工具原文 C_FreeGiB=5.173；收口全量工具原文 C_FreeGiB=7.607。仅清理已结束 B 段 t25b5 与已结束 C 开工 t25co，单一 PowerShell 中核对 OS Temp 下完整绝对路径、精确名称和非 ReparsePoint 后删除；未删除任何真实源目录。收口使用 OS_TEMP/t25cf，不把 basetemp 指向 E 盘。

## 交付边界与待办

C 功能已收口，D 尚未开工。全量 FR-A12 的挂载 / 凭据 / NAS 可达性 / NAS 实际输出、未授权格式、安装包、真实 NAS 实机验证不在本段。既定 D1–D6 历史债保留；本次没有新增产品口径。D 仍须独立开工基线和卡 §5 的逐条汇总验收。

按即停条款上报全部新锚点：[anchor-drift.md](E:/AI_Agent/milestone25/evidence/C/anchor-drift.md)。执行方未改任务卡；C 提交后停在 D 前，请备卡方按提交 HEAD 统一更新 §0.2 与正文重复引用后解阻。

## 改动文件清单

- [src-python/spectrumagent/api/openapi.json](E:/AI_Agent/src-python/spectrumagent/api/openapi.json)
- [src-python/spectrumagent/api/project_paths.py](E:/AI_Agent/src-python/spectrumagent/api/project_paths.py)
- [src-python/spectrumagent/api/settings.py](E:/AI_Agent/src-python/spectrumagent/api/settings.py)
- [src-python/spectrumagent/app.py](E:/AI_Agent/src-python/spectrumagent/app.py)
- [src-python/tests/agent/test_project_paths.py](E:/AI_Agent/src-python/tests/agent/test_project_paths.py)
- [src-tauri/src/agent.rs](E:/AI_Agent/src-tauri/src/agent.rs)
- [src-tauri/src/settings.rs](E:/AI_Agent/src-tauri/src/settings.rs)
- [src-tauri/tests/agent_settings_forward.rs](E:/AI_Agent/src-tauri/tests/agent_settings_forward.rs)
- [src/App.tsx](E:/AI_Agent/src/App.tsx)
- [src/components/annotation/AnnotationWorkbench.tsx](E:/AI_Agent/src/components/annotation/AnnotationWorkbench.tsx)
- [src/components/assistant/presentation.ts](E:/AI_Agent/src/components/assistant/presentation.ts)
- [src/components/assistant/useSession.ts](E:/AI_Agent/src/components/assistant/useSession.ts)
- [src/components/datasets/DatasetPanel.tsx](E:/AI_Agent/src/components/datasets/DatasetPanel.tsx)
- [src/components/datasets/RecycleView.ts](E:/AI_Agent/src/components/datasets/RecycleView.ts)
- [src/components/datasets/actions.test.ts](E:/AI_Agent/src/components/datasets/actions.test.ts)
- [src/components/datasets/actions.ts](E:/AI_Agent/src/components/datasets/actions.ts)
- [src/components/datasets/api.ts](E:/AI_Agent/src/components/datasets/api.ts)
- [src/components/datasets/catalog.test.ts](E:/AI_Agent/src/components/datasets/catalog.test.ts)
- [src/components/datasets/catalog.ts](E:/AI_Agent/src/components/datasets/catalog.ts)
- [src/components/datasets/datasets.css](E:/AI_Agent/src/components/datasets/datasets.css)
- [src/components/datasets/paths.ts](E:/AI_Agent/src/components/datasets/paths.ts)
- [src/components/datasets/types.ts](E:/AI_Agent/src/components/datasets/types.ts)
- [src/components/modeling/InferencePanel.tsx](E:/AI_Agent/src/components/modeling/InferencePanel.tsx)
- [src/components/modeling/ModelPanel.tsx](E:/AI_Agent/src/components/modeling/ModelPanel.tsx)
- [src/components/settings/ProjectPathsPanel.tsx](E:/AI_Agent/src/components/settings/ProjectPathsPanel.tsx)
- [src/components/settings/ProjectPathsView.ts](E:/AI_Agent/src/components/settings/ProjectPathsView.ts)
- [src/components/settings/project-path-form.ts](E:/AI_Agent/src/components/settings/project-path-form.ts)
- [src/components/settings/project-paths.test.ts](E:/AI_Agent/src/components/settings/project-paths.test.ts)
- [src/components/settings/settings-forward.ts](E:/AI_Agent/src/components/settings/settings-forward.ts)
- [src/screens/S02.tsx](E:/AI_Agent/src/screens/S02.tsx)
- [src/screens/S09.tsx](E:/AI_Agent/src/screens/S09.tsx)
- [src/screens/S11.tsx](E:/AI_Agent/src/screens/S11.tsx)
- [src/screens/light-screens.test.ts](E:/AI_Agent/src/screens/light-screens.test.ts)
- [src/screens/split-screens.test.ts](E:/AI_Agent/src/screens/split-screens.test.ts)

测试证据和辅助材料逐文件位于 [evidence/C](E:/AI_Agent/milestone25/evidence/C)，包括开工 / 收口原文、完整 collected 列表、失败历史、锚点命令与截图。归档脚本和夹具不在产品入口内。

## 开工与收口取数命令

```powershell
# Windows PowerShell，仓库根 E:/AI_Agent。开工日志原写 .runtime/task25/C-opening 后逐文件复制为 evidence/C/before-*。
node --test "src/**/*.test.ts"
npm run build
if ((Get-PSDrive C).Free -lt 3GB) { throw 'C below 3 GiB' }
$task25CTmp = Join-Path $env:TEMP 't25co' # 收口改为 t25cf
New-Item -ItemType Directory -Force $task25CTmp | Out-Null
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTEST_DEBUG_TEMPROOT = $task25CTmp
& .venv/Scripts/python.exe -m pytest backend/tests src-python/tests --collect-only -q
& .venv/Scripts/python.exe -m pytest backend/tests -q
& .venv/Scripts/python.exe -m pytest src-python/tests -q
# 以下 Rust 命令 workdir=E:/AI_Agent/src-tauri
$env:CARGO_HOME = 'E:/AI_Agent/.cargo-home'
$env:CARGO_TARGET_DIR = 'E:/AI_Agent/src-tauri/target'
$env:CARGO_NET_OFFLINE = 'true'
cargo test
cargo clippy --all-targets -- -D warnings
# 根目录 grep，命令全文见 anchor-commands.ps1；写点发现域固定生产 .py。
& 'C:/Program Files/Git/usr/bin/grep.exe' -rln -E '[.]write_text[(]|[.]write_bytes[(]|np[.]save|savemat[(]|shutil[.]rmtree|[.]unlink[(]|[.]mkdir[(]|open_memmap' src-python/spectrumagent backend --include=*.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -E 'cube_ids? +TEXT' src-python/spectrumagent/annotation/migrations.py src-python/spectrumagent/preprocess/migrations.py src-python/spectrumagent/modeling/migrations.py src-python/spectrumagent/agent/migrations.py
```

写点输出排除 __pycache__ 与 /tests/ 并排序；它是出口发现模式的文件数，不是 SQL 表数。OpenAPI 由组合应用重新生成，原 schema 快照相等与字节断言未改，收口全量覆盖。

## 原文：开工基线

原始文件：[before-versions.txt](E:/AI_Agent/milestone25/evidence/C/before-versions.txt)

```text
3.12.13 (main, May 10 2026, 19:35:37) [MSC v.1944 64 bit (AMD64)]
SQLite 3.50.4
v24.19.0
11.17.0
rustc 1.99.1 (58cf8f9c3 2026-10-13)
cargo 1.99.1 (5f94df478 2026-08-27)
```

原始文件：[opening-head.txt](E:/AI_Agent/milestone25/evidence/C/opening-head.txt)

```text
3091c13 docs(task25): C 段 §4.1 项目路径保存接口契约（即停裁定选项 1）
```

原始文件：[before-anchors.txt](E:/AI_Agent/milestone25/evidence/C/before-anchors.txt)

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

原始文件：[opening-settings-at-3091c13.txt](E:/AI_Agent/milestone25/evidence/C/opening-settings-at-3091c13.txt)

```text
settings-forward.ts at 3091c13:5:export type SettingsRequest = { op: 'get_llm' } | { op: 'put_llm'; body: LLMConfig } | { op: 'put_key'; key: string };
settings-forward.ts at 3091c13:13:  getLLM: (): SettingsRequest => ({ op: 'get_llm' }),
settings-forward.ts at 3091c13:14:  putLLM: (body: LLMConfig): SettingsRequest => ({ op: 'put_llm', body: configFields(body) }),
settings-forward.ts at 3091c13:15:  putKey: (key: string): SettingsRequest => ({ op: 'put_key', key }),
settings-forward.ts at 3091c13:20:  const forward = <T>(request: SettingsRequest) => send<T>('settings_forward', { request });
api/settings.py at 3091c13:13:def make_router(database):
api/settings.py at 3091c13:14:    router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
api/settings.py at 3091c13:19:    @router.get("/llm")
api/settings.py at 3091c13:23:    @router.put("/llm")
api/settings.py at 3091c13:28:    @router.put("/llm/key")
settings.rs at 3091c13:12:#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
settings.rs at 3091c13:13:pub enum SettingsRequest {
settings.rs at 3091c13:46:    pub fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
settings.rs at 3091c13:63:    let secrets = match request {
settings.rs at 3091c13:64:        SettingsRequest::PutKey { key } => vec![key.as_str()],
```

原始文件：[before-node.txt](E:/AI_Agent/milestone25/evidence/C/before-node.txt)

```text
✔ block clicks retain the legacy geometry and omit label_id for erase and uncertain (7.0494ms)
✔ IPC superpixels: exact Rust variant, one command, no arbitrary route (0.4249ms)
✔ IPC diffuse: exact Rust variant, one command, no arbitrary route (0.2902ms)
✔ IPC regions: exact Rust variant, one command, no arbitrary route (0.21ms)
✔ IPC undo: exact Rust variant, one command, no arbitrary route (0.2321ms)
✔ IPC working: exact Rust variant, one command, no arbitrary route (0.3106ms)
✔ IPC validate: exact Rust variant, one command, no arbitrary route (0.2143ms)
✔ IPC save: exact Rust variant, one command, no arbitrary route (0.2499ms)
✔ IPC versions: exact Rust variant, one command, no arbitrary route (0.2411ms)
✔ IPC version_overlay: exact Rust variant, one command, no arbitrary route (0.3128ms)
✔ IPC projects: exact Rust variant, one command, no arbitrary route (0.2527ms)
✔ IPC labels: exact Rust variant, one command, no arbitrary route (0.1606ms)
✔ IPC add_label: exact Rust variant, one command, no arbitrary route (0.2133ms)
✔ IPC catalog: exact Rust variant, one command, no arbitrary route (0.1529ms)
✔ optional defaults are left to Python; all prompt and geometry forms retain [line,sample] (0.4307ms)
✔ all three structured label bodies match Python and carry the working project id (0.2231ms)
✔ local estimates and display state cannot enter request projections (0.4377ms)
✔ structured errors keep code, field messages and context; client never swallows rejection (0.9916ms)
✔ RGB id decoding retains ids above 255 and verifies every block count (3.6649ms)
✔ hitTest is local and rejects out-of-image and fractional coordinates (0.392ms)
✔ 3px Euclidean boundary is inclusive; drags produce no block action (0.3256ms)
✔ badges distinguish blank, uncertain, two and three kinds of marking (0.3874ms)
✔ canvas uses unscaled id loading, the existing contextmenu guard and down-time modifiers (1.9274ms)
✔ 2GiB boundary and plus one require exactly the shared extra approval (1.0521ms)
✔ draft client projects only fixed confirm fields into the tenth command (1.209ms)
✔ mock forward fetches estimate then confirms the fetched revision (0.5325ms)
✔ fetch failure and invalid summaries block approval instead of assuming zero (1.2328ms)
✔ confirmation card renders fetched byte count, loading, refusal and second dialog (11.2243ms)
✔ only HUMAN_CHECK uses the confirm card and pending-call revision stays server-owned (1.1246ms)
✔ old numeric preview call keeps the exact single-band request (1.996ms)
✔ extended preview request projects only allowed keys and explicit full resolution (0.2199ms)
✔ S05 band changes use display state, full resolution, and retain PNG onload hotfix (1.1493ms)
✔ display modes are exclusive, preserve RGB order and reject duplicates (0.4818ms)
✔ entry defaults to backend automatic selection and displays returned RGB wavelengths (0.5486ms)
✔ default LUT is identity for all 256 intensities (0.4778ms)
✔ LUT rejects nonfinite/out of range/gap under 16 and preserves last valid parameters (0.4248ms)
✔ LUT follows clamp and inverse gamma, one table for RGB, alpha unchanged and input untouched (0.4034ms)
✔ manual LUT values stay local and are independent of image request keys (0.7679ms)
✔ point coordinates retain [line,sample] and send one-pixel spectra_mean, never region (0.3648ms)
✔ point inspection returns before any edit tool and leaves null gaps visible (0.583ms)
✔ box mean uses existing half-open endpoints, direction independent, no spectral arithmetic (0.2273ms)
✔ box inspection routes to spectra before edits and has no readiness dependency (0.365ms)
✔ storeGesture projects exactly point, box or doodle and strips nested extras (2.2425ms)
✔ gesture projection adds no absent variant fields or optional defaults (0.3006ms)
✔ gesture client uses only annotations_draft_forward and preserves server reference (0.3263ms)
✔ gesture store failure reaches caller without a fabricated reference (0.611ms)
✔ B1/B6 parent folder supports Windows, slash and mixed paths (1.316ms)
✔ B1 matching is exact, case insensitive and trims only (0.2983ms)
✔ B1 background number 1 is excluded; first ordered foreground match wins (0.1905ms)
✔ B2 catalog returns the canonical code without constructing label fields (0.199ms)
✔ B2 an absent folder matches after the refreshed label list includes the catalog label (0.1366ms)
✔ B3 matching leaves the input list and labels unchanged (0.1865ms)
✔ B4 folders are derived separately for each cube (0.2605ms)
✔ B5 single-file import with an arbitrary parent has no fallback label or catalog code (0.2416ms)
✔ C4: previous version total and current label-index counts render as separate summaries (23.7574ms)
✔ C4: zero classes and uncertainty are omitted while zero blank pixels remain visible (0.3415ms)
✔ C4: missing overwrite summary cannot suppress the confirmation dialog (0.371ms)
✔ C1/C2/C3/C7: auto-default uses a touched ref, resets per dataset, and follows the version count (0.2844ms)
✔ C1/C3/C6: overwrite retains the confirmation gate and cancelling only dismisses the dialog (0.2471ms)
✔ projection consumes save response, shows a selectable absolute path and fixed folder command (1.1667ms)
✔ projection failures keep save available and explicitly explain overwrite retry (0.5202ms)
✔ click binds C; Delete and Shift are not independent commands (3.0888ms)
✔ 0 is background-only; 1–9 are numeric; unbound or out-of-range labels remain mouse-only (1.0985ms)
✔ Enter / Z / D / E-B-P / arrows / Ctrl+S / space have the specified actions (0.9343ms)
✔ typing never changes labels or undo; disabled settings suppress shortcuts; global chat keys pass through (0.3505ms)
✔ local remapping is deterministic and rejects duplicates/reserved keys without altering server labels (1.9871ms)
✔ each edit reads working again; write-response pixels, queue and statistics are never reconstructed (2.0999ms)
✔ switching cubes and recovering after confirm use only GET working, never diffuse (0.4482ms)
✔ a failed edit propagates its envelope and cannot manufacture a successful redraw (0.6086ms)
✔ R17 label indexes use sort_order plus SQLite BINARY code order, independent of tree grouping (0.3878ms)
✔ local remaining-time estimate derives only from confirmation speed and handles no progress (1.3524ms)
✔ catalog color proximity uses backend colors and the task-card <30 rule (0.3559ms)
✔ viewport transforms preserve [line,sample], bounds, zoom anchors and half-open boxes (0.551ms)
✔ component wiring has no local label map or undo history and preserves the outer conversation bar (2.081ms)
✔ plan card renders table, scalar metadata, estimates, aria labels and chosen invalidation (23.7001ms)
✔ all destructive choices require a reason and IPC projects only plan contract fields (31.9787ms)
✔ disabled controls cannot submit and history keeps the plan decision without action buttons (4.7903ms)
✔ all agent operations invoke only agent_forward with exact projection (2.9887ms)
✔ view state, URL, key and mixed-body extras cannot enter IPC (0.3916ms)
✔ structured preflight HTTP status and errors pass through unchanged (1.7052ms)
✔ workspace context projects opaque references and cannot leak display data or geometry (0.3563ms)
✔ server-listed ordinals and names are usable without reimporting files in the current UI (2.7156ms)
✔ legacy lists retain backend order while local names remain local (0.4527ms)
✔ changing cubes clears an old gesture and same-cube followups retain it (1.1726ms)
✔ only successful annotation or preprocessing steps cause authoritative result refresh (0.4381ms)
✔ workspace SSE rejects paths, unbound geometry, unknown stage and invalid revisions (1.0068ms)
✔ request failures and SSE failures share human-readable error messages (0.3523ms)
✔ curated backend explanations survive both error delivery paths (0.3355ms)
✔ AI preview focus uses the workflow reference rather than queue order or a diffusion identifier (0.3964ms)
✔ P1 A1 App owns one session shared by Composer and S01; renderers have no reducer (3.2039ms)
✔ P1 A2 A3 composer hiding and global shortcuts leave S01 input independent (1.1589ms)
✔ P1 A4 A5 smoke stays in S01 and the three columns use current session context (1.0186ms)
✔ P1 A6 A8 retired panel files and rules are absent with only six new layout classes (2.0258ms)
✔ SSE 正常流 retains order and JSON (3.5099ms)
✔ SSE 确认后挂起 retains order and JSON (0.4685ms)
✔ SSE 错误收尾 retains order and JSON (0.9242ms)
✔ SSE 空流 retains order and JSON (0.3207ms)
✔ SSE accepts CRLF, multiline data, comments and final frame at EOF (1.3248ms)
✔ SSE rejects unknown events, missing event, malformed and nonobject data (0.4319ms)
✔ SSE collector retains every rejected step beyond eight (0.4293ms)
✔ approve disables both controls and records executing until response (0.248ms)
✔ reject immediately closes confirmation card; server result remains ordered (0.2366ms)
✔ pending check accepts ordinary dialogue and sequential checks replace pending id (0.3048ms)
✔ clarify and errors release busy state and keep messages in order (0.2298ms)
✔ summary renderer displays scalars and excludes unexpected objects (0.2403ms)
✔ plan SSE is accepted, accepts dialogue and cannot use the tool-decision path (0.1951ms)
✔ unrecognized approval dialogue keeps its card while terminal outcomes clear it (0.2786ms)
✔ plan actions preserve pending while executing and retain the decision with the original plan (0.3234ms)
✔ plan approval can suspend again at human check and all terminal events clear pending (0.1672ms)
✔ chat-selected registered cubes load through the existing fixed get operation (2.7103ms)
✔ catalog and recycle operations use fixed typed requests with explicit confirmation (1.5215ms)
✔ reimport confirmation is sent only from an explicit caller choice (0.4094ms)
✔ G3 shared displayName uses the server name and preserves the legacy fallback (0.9638ms)
✔ G2 all_datasets refreshes a previously unique name without duplicating records (0.89ms)
✔ G assistant choices and readable references use exactly the API display name (0.7921ms)
✔ only the absent-active recycled-key error promises a new dataset id (1.8719ms)
✔ active records and concurrent active conflicts never open the fresh-id confirmation (0.3353ms)
✔ existing and newly imported messages agree with actual response counts (0.2533ms)
✔ retries and existing imports keep exactly one row per persisted ID (3.5136ms)
✔ batch errors retain source path and reason for the user (0.5255ms)
✔ sample value uses fixed native command and preserves annotation response (2.1905ms)
✔ CSV duplicate confirmation is an explicit second import (0.3291ms)
✔ PLS request retains explicit bound runs and only regression CV; seven result labels (0.369ms)
✔ coefficients use one fixed read-only native operation and exact model id body (0.2769ms)
✔ extents exclude null and non-finite values without changing inputs (3.4511ms)
✔ coordinate mapping covers endpoints, inverted Y, constants and extreme finite domains (0.3416ms)
✔ nice ticks are deterministic, rounded and integer-only for counts or LVs (1.8623ms)
✔ null and non-finite curve points split paths and never interpolate gaps (0.3818ms)
✔ histogram uses sqrt sample count capped at 20, shared rounded edges and grouped counts (1.168ms)
✔ histogram bins are left-closed with rightmost edge included; rounded inner edges agree with membership (1.3151ms)
✔ one histogram sample becomes a single nonzero-width bin; invalid values produce no bins (1.4688ms)
✔ four evaluation models include curve, scatter, residual and grouped histogram (2.6933ms)
✔ LV markers use saved recommendations verbatim rather than recomputing an elbow (1.6798ms)
✔ empty curve and all non-finite curves show explicit no-data status without axes (0.7729ms)
✔ curve missing values retain separated finite paths and single-point strokes (1.2284ms)
✔ one prediction is a square, maps constant axes to midlines and has one populated histogram bar (0.412ms)
✔ constant references with varying predictions remain on X midline with an explicit note (0.3874ms)
✔ null metrics never enter chart coordinates or quality calculations (0.6334ms)
✔ get_run failure produces four explicit unavailable plots, never blank axes (0.3917ms)
✔ missing LV artifact preserves the three prediction plots and their quality labels (0.3537ms)
✔ undefined predictions from classification runs are explicit, empty arrays remain no-data (1.1114ms)
✔ missing fields and unknown sets are excluded per chart, with an explicit reason when all are unusable (0.3253ms)
✔ half-quantitative label uses backend flag or label and never derives RPD (1.4432ms)
✔ loading has visible messages and a result can render while its curve is still loading (0.3226ms)
✔ error descriptions handle structured native errors and opaque values without secondary throws (0.2219ms)
✔ coefficient chart preserves signed values, zero reference, backend quality and tick targets (0.7055ms)
✔ coefficient refusal: unknown axis (0.2152ms)
✔ coefficient refusal: dimension mismatch (0.0946ms)
✔ coefficient refusal: same dimensions unsafe operator (0.0755ms)
✔ coefficient loading, missing artifact and 404 have visible messages without secondary errors (0.1519ms)
✔ coefficient empty and invalid arrays are distinct and never draw malformed nested coefficients (0.1926ms)
✔ coefficient zero line remains inside frame for 1,1,1 (0.2948ms)
✔ coefficient zero line remains inside frame for -3,-3,-3 (0.1282ms)
✔ coefficient zero line remains inside frame for 0,0,0 (0.1192ms)
✔ coefficient zero line remains inside frame for 1,2,3 (0.1403ms)
✔ coefficient zero line remains inside frame for -1,-2,-3 (0.0827ms)
✔ single coefficient is one square; nonascending wavelengths retain artifact order and disclose it (0.2708ms)
✔ six new fixed requests preserve exact bodies and strip input extras (1.3046ms)
✔ map source permits only PNG base64 and positive integer dimensions (0.2679ms)
✔ fixed palette rejects invalid RGB and preserves ordered endpoints (0.171ms)
✔ clipping disclosure includes foreground totals and both directions (0.1137ms)
✔ stages and required scientific warning are explicit (0.0987ms)
✔ components use the client, disclose calibration, progress and independent map errors (0.6068ms)
✔ registered coefficient button is lazy per model and shows pending then success or 404 state (100.2892ms)
✔ preprocess IPC list_recipes: exact projection and sole command (2.0327ms)
✔ preprocess IPC create_recipe: exact projection and sole command (0.3161ms)
✔ preprocess IPC get_recipe: exact projection and sole command (0.872ms)
✔ preprocess IPC add_version: exact projection and sole command (0.2445ms)
✔ preprocess IPC select_recipe: exact projection and sole command (0.1828ms)
✔ preprocess IPC deselect_recipe: exact projection and sole command (0.1687ms)
✔ preprocess IPC list_project_recipes: exact projection and sole command (0.2ms)
✔ preprocess IPC create_run: exact projection and sole command (0.224ms)
✔ preprocess IPC list_runs: exact projection and sole command (0.1876ms)
✔ preprocess IPC get_run: exact projection and sole command (0.257ms)
✔ preprocess IPC compare: exact projection and sole command (0.2126ms)
✔ preprocess IPC get_artifact: exact projection and sole command (0.151ms)
✔ request bodies omit runtime extras, run guard/block_size, and editor state (0.1654ms)
✔ report is parsed JSON; only sample_spectra uses binary wrapper; 204 stays null (0.1725ms)
✔ recovery inspects only new succeeded summaries and matches recipe in details (3.5695ms)
✔ transport and timeout recover, business errors do not; structured details remain visible (0.6668ms)
✔ submit TRANSPORT automatically restores new matching success; unknown outcome stays pending verification (0.9877ms)
✔ legend resolves index→id→code with backend colors, missing id prefix, unlabeled title (0.2779ms)
✔ S06 component wiring: no transport outside API, no numeric engine / fake preview; global chat unchanged (1.8244ms)
✔ unsupported operations are all marked stage two / not applicable without example metrics (0.2677ms)
✔ operator directory matches explicit R15 names and excludes run B01 / unresolved reference methods (2.8308ms)
✔ axisAfter is pure, crop closed, resample replaces, decomposition removes axis (0.8958ms)
✔ crop→resample→crop supplies EACH current source, never stale saved source (0.4953ms)
✔ schema-direction validation: odd SG, STRICT polynomial bound, derivative order/mode (0.4499ms)
✔ all exposed methods accept valid schema choices; unknown keys and absent components reject (2.5764ms)
✔ no wavelengths disables axis operators; lo<hi, nonempty crop, target finite/increasing enforce (0.5404ms)
✔ move/delete/repeat preserve order and compile legal explicit steps (0.2765ms)
✔ target creation is axis-only; chart gaps retain separate strokes and values (0.3435ms)
✔ settings screen starts with five empty text fields, an enabled egress switch, a password input and an unknown key status (10.8994ms)
✔ rendered field changes and submit save the six-key config then key, and clear the password (5.446ms)
✔ GET has_key renders both states without pre-filling a key, and blank key preserves existing credentials (2.0658ms)
✔ GET failure disables saving and fields while the rendered cancel button remains usable (2.5836ms)
✔ nonempty URL and numeric validation blocks invalid saves without inventing provider limits (3.6452ms)
✔ backend 400 code and detail are rendered and a failed config save never submits the key (1.4952ms)
✔ failed key write reports partial save, clears its input and redacts credentials in errors (2.4351ms)
✔ saving prevents duplicate submits and disposing ignores an in-flight GET (0.8428ms)
✔ App settings entry opens S11 with its embedded form, preserving UI-to-configuration reachability (0.5476ms)
✔ egress checkbox reflects the false value returned by GET (1.0783ms)
✔ unchecking egress saves a boolean false and keeps the returned switch state (0.709ms)
✔ settings GET and two PUT operations use only settings_forward with exact bodies (2.1568ms)
✔ settings projections exclude credentials and view or route extras from config and responses (0.325ms)
✔ settings forward preserves the backend 400 envelope unchanged (0.7366ms)
✔ egress false remains boolean through config PUT and GET projections (0.3156ms)
✔ P5 S02 uses props for four cards, recent regression runs and phase plus generation only (1.4123ms)
✔ P5 S09 regression table has only id task status and a client task filter without invented timestamps (1.1331ms)
✔ P5 S09 fetches selected run details and retains backend metrics quality and collapsed leak report (0.3364ms)
✔ P5 S09 preprocess reads only the selected dataset and preserves real time fields and empty states (0.3381ms)
✔ P5 S10 has a data-screen action and S11 embeds the settings form without fake controls (0.3011ms)
✔ P5 inserts four screen cases while preserving source anchors S03 debug text and theme boundary (0.4852ms)
✔ P2 navigation preserves App runId until the results back-to-list action (1.0345ms)
✔ P2 S04 and S03 thumbnails share BandCanvas and viewing updates workspace (0.5554ms)
✔ P2 S08 loads real regression runs and refetches run plus sweep on mount (0.416ms)
✔ P2 S07 keeps training and internal views while results and source anchors stay intact (0.7314ms)
✔ A1 navigation retains five ordered groups and exactly ten unique screen entries (1.3393ms)
✔ A1 titles cover all eleven Screen values including the viewer below data (0.1456ms)
✔ A1 only s04 redirects its navigation highlight to s03 (0.1375ms)
✔ skin guards: annotation-skin.css (1.5368ms)
✔ skin guards: preprocess-skin.css (0.3026ms)
✔ skin guards: modeling-skin.css (0.2983ms)
ℹ tests 223
ℹ suites 0
ℹ pass 223
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 720.7047
```

原始文件：[before-Python-collected.txt](E:/AI_Agent/milestone25/evidence/C/before-Python-collected.txt)

```text
src-python/tests/test_display_falsecolor.py::test_mean_does_not_reuse_65536_json_value_limit
src-python/tests/test_display_falsecolor.py::test_mean_one_million_pixel_boundary[1000-200]
src-python/tests/test_display_falsecolor.py::test_mean_one_million_pixel_boundary[1001-400]
src-python/tests/test_display_falsecolor.py::test_display_requests_do_not_change_annotation_working_or_versions

============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1544 tests collected in 2.85s
```

原始文件：[before-Python-backend.txt](E:/AI_Agent/milestone25/evidence/C/before-Python-backend.txt)

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
45 passed, 10 warnings in 5.85s
```

原始文件：[before-Python-src.txt](E:/AI_Agent/milestone25/evidence/C/before-Python-src.txt)

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
1497 passed, 2 skipped, 6 warnings in 732.56s (0:12:12)
```

原始文件：[before-Rust.txt](E:/AI_Agent/milestone25/evidence/C/before-Rust.txt)

```text
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.50s
     Running unittests src\lib.rs (target\debug\deps\spectrum_agent-fc5a2225eca9e0bc.exe)

running 54 tests
test annotation::tests::identifiers_cannot_escape_and_version_numbers_are_not_uuids ... ok
test annotation::tests::bad_types_lengths_and_out_of_range_parameters_are_rejected ... ok
test annotation::tests::parameter_edges_and_unicode_note_match_http_contract ... ok
test annotation::tests::omitted_parameters_stay_omitted_and_all_prompt_geometries_are_typed ... ok
test annotation::tests::all_nine_operations_have_exact_paths_methods_and_bodies ... ok
test annotation::tests::four_management_operations_have_literal_paths_methods_and_bodies ... ok
test annotation::tests::only_the_supplied_nonzero_handshake_port_is_used ... ok
test annotation::tests::project_query_is_strict_then_lowercase_but_dataset_path_is_unchanged ... ok
test annotation::tests::no_free_url_host_port_path_or_method_can_enter_any_operation ... ok
test datasets_dev::tests::delete_contract ... ok
test datasets_dev::tests::all_operations_use_the_handshake_port_and_fixed_namespace ... ok
test datasets_dev::tests::catalog_contract ... ok
test annotation::tests::unknown_operations_and_fields_are_structured_and_never_reflect_input ... ok
test datasets_dev::tests::import_confirmation_defaults_false ... ok
test datasets_dev::tests::delete_preview_contract ... ok
test datasets_dev::tests::no_generic_host_port_path_or_method_can_be_deserialized ... ok
test datasets_dev::tests::restore_contract ... ok
test datasets_dev::tests::preview_legacy_url_is_unchanged_and_optional_fields_allow_rgb_without_band ... ok
test datasets_dev::tests::recycle_list_contract ... ok
test models::tests::new_ops_reject_proxy_fields_invalid_stages_and_all_id_traversal ... ok
test datasets_dev::tests::spectra_mean_has_fixed_post_path_typed_region_and_uuid_guard ... ok
test models::tests::registry_inference_six_fixed_operations ... ok
test health::route_tests::closed_routes_always_use_numeric_loopback_and_literal_paths ... ok
test models::tests::fixed_operations_and_methods ... ok
test preprocess::tests::actual_generation_guard_used_by_command_rejects_stale_or_nonready ... ok
test preprocess::tests::all_twelve_destinations_methods_and_exact_bodies ... ok
test preprocess::tests::four_uuid_error_codes_cover_every_identifier_field ... ok
test preprocess::tests::builder_sets_three_hundred_seconds_without_waiting ... ok
test preprocess::tests::manual_base64_matches_rfc4648_vectors ... ok
test datasets_dev::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test preprocess::tests::malformed_http_envelope_uses_generic_error ... ok
test annotation::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test preprocess::tests::json_success_is_unchanged_and_post_body_is_forwarded ... ok
test preprocess::tests::unknown_fields_ops_types_artifact_values_and_free_destinations_are_rejected ... ok
test preprocess::tests::binary_payload_and_wrapper_filename_are_also_sensitive_checked ... ok
test preprocess::tests::uuid_copy_and_port_boundary_preserve_closed_destination ... ok
test annotation::tests::label_body_limit_counts_serialized_utf8_and_business_validation_stays_in_python ... ok
test preprocess::tests::structured_http_error_preserves_three_fields ... ok
test preprocess::tests::redirects_are_not_followed ... ok
test preprocess::tests::raw_and_canonical_tokens_never_cross_bridge ... ok
test datasets_dev::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test annotation::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test preprocess::tests::only_204_maps_empty_body_to_null_not_200 ... ok
test preprocess::tests::report_stays_json_and_nonartifact_binary_is_rejected ... ok
test annotation::tests::response_identity_precedes_status_and_body ... ok
test preprocess::tests::identity_checks_precede_http_status_and_body ... ok
test datasets_dev::tests::response_identity_precedes_status_and_body ... ok
test models::tests::six_new_ops_reach_loopback_with_native_auth_and_exact_bodies ... ok
test preprocess::tests::binary_artifact_roundtrips_and_keeps_filename ... ok
test preprocess::tests::declared_and_streaming_limits_reject_above_eight_mib ... ok
test datasets_dev::tests::declared_and_streaming_response_limits_are_enforced ... ok
test annotation::tests::declared_and_streaming_response_limits_are_enforced ... ok
test models::tests::rejects_general_proxy_extra_fields_traversal_and_oversize ... ok
test annotation::tests::an_exactly_eight_mib_json_response_is_allowed ... ok

test result: ok. 54 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.25s

     Running unittests src\main.rs (target\debug\deps\spectrum_agent-9760c85afe553455.exe)

running 8 tests
test boot::tests::before_timeout_wait_and_first_attempt_precedes_give_up ... ok
test boot::tests::final_timeout_is_fifteen_seconds_from_window_shown ... ok
test boot::tests::healthy_document_always_waits_across_generations ... ok
test boot::tests::reload_boundary_4999_5000_and_5001_ms ... ok
test boot_monitor_tests::reload_budget_is_independent_and_activations_do_not_reset_it ... ok
test exports_tests::export_folder_is_scoped_to_a_canonical_cube_uuid ... ok
test exports_tests::export_folder_rejects_paths_and_malformed_ids ... ok
test boot_monitor_tests::engine_retry_keeps_healthy_document_until_real_navigation ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\agent_settings_forward.rs (target\debug\deps\agent_settings_forward-33848812934a45f0.exe)

running 10 tests
test both_commands_reject_stale_generation_or_non_ready_phase ... ok
test workspace_events_keep_only_bound_scalar_references ... ok
test settings_only_existing_get_put_operations_and_no_key_in_config ... ok
test agent_three_operations_and_two_body_shapes_have_literal_routes ... ok
test whitelist_rejects_paths_methods_and_mixed_message_shapes ... ok
test http_errors_keep_status_and_envelope_redirects_not_followed ... ok
test settings_key_and_escaped_credentials_never_cross_error_or_success_envelopes ... ok
test sse_empty_done_suspended_human_check_and_error_close ... ok
test identity_is_checked_before_status_length_and_body_for_both_commands ... ok
test declared_and_streaming_limits_are_enforced_for_both_commands ... ok

test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.52s

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

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.81s

     Running tests\causality.rs (target\debug\deps\causality-36e4b6d833a263b9.exe)

running 2 tests
test midnight_files_and_preexisting_partial_line_are_handled_without_fallback ... ok
test only_new_complete_lines_with_own_integer_pid_in_utc_window_can_be_cause ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.04s

     Running tests\contracts.rs (target\debug\deps\contracts-6e34dbf97624c6bb.exe)

running 6 tests
test late_generation_and_expected_exit_cannot_fail_current_attempt ... ok
test all_transition_pairs_and_stopping_terminal_rule ... ok
test exact_fields_and_top_level_are_enforced ... ok
test valid_handshake_values_and_integer_utc_comparison ... ok
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

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 6.10s

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

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.19s

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

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.08s
```

原始文件：[before-clippy.txt](E:/AI_Agent/milestone25/evidence/C/before-clippy.txt)

```text
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.40s
```

原始文件：[before-build.txt](E:/AI_Agent/milestone25/evidence/C/before-build.txt)

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

✓ built in 147ms
```

原始文件：[before-write-files.txt](E:/AI_Agent/milestone25/evidence/C/before-write-files.txt)

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

原始文件：[before-cube-columns.txt](E:/AI_Agent/milestone25/evidence/C/before-cube-columns.txt)

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

## 原文：收口回归

原始文件：[node-after.txt](E:/AI_Agent/milestone25/evidence/C/node-after.txt)

```text
✔ block clicks retain the legacy geometry and omit label_id for erase and uncertain (4.8705ms)
✔ IPC superpixels: exact Rust variant, one command, no arbitrary route (0.2919ms)
✔ IPC diffuse: exact Rust variant, one command, no arbitrary route (0.1894ms)
✔ IPC regions: exact Rust variant, one command, no arbitrary route (0.1184ms)
✔ IPC undo: exact Rust variant, one command, no arbitrary route (0.1216ms)
✔ IPC working: exact Rust variant, one command, no arbitrary route (0.1305ms)
✔ IPC validate: exact Rust variant, one command, no arbitrary route (0.1561ms)
✔ IPC save: exact Rust variant, one command, no arbitrary route (0.2304ms)
✔ IPC versions: exact Rust variant, one command, no arbitrary route (0.2317ms)
✔ IPC version_overlay: exact Rust variant, one command, no arbitrary route (0.9996ms)
✔ IPC projects: exact Rust variant, one command, no arbitrary route (0.2471ms)
✔ IPC labels: exact Rust variant, one command, no arbitrary route (0.1735ms)
✔ IPC add_label: exact Rust variant, one command, no arbitrary route (0.1992ms)
✔ IPC catalog: exact Rust variant, one command, no arbitrary route (0.1737ms)
✔ optional defaults are left to Python; all prompt and geometry forms retain [line,sample] (0.2708ms)
✔ all three structured label bodies match Python and carry the working project id (0.1643ms)
✔ local estimates and display state cannot enter request projections (0.3079ms)
✔ structured errors keep code, field messages and context; client never swallows rejection (1.7211ms)
✔ RGB id decoding retains ids above 255 and verifies every block count (3.1932ms)
✔ hitTest is local and rejects out-of-image and fractional coordinates (0.3602ms)
✔ 3px Euclidean boundary is inclusive; drags produce no block action (0.2533ms)
✔ badges distinguish blank, uncertain, two and three kinds of marking (0.4432ms)
✔ canvas uses unscaled id loading, the existing contextmenu guard and down-time modifiers (1.7953ms)
✔ 2GiB boundary and plus one require exactly the shared extra approval (1.0868ms)
✔ draft client projects only fixed confirm fields into the tenth command (1.2911ms)
✔ mock forward fetches estimate then confirms the fetched revision (0.4376ms)
✔ fetch failure and invalid summaries block approval instead of assuming zero (0.7917ms)
✔ confirmation card renders fetched byte count, loading, refusal and second dialog (9.8406ms)
✔ only HUMAN_CHECK uses the confirm card and pending-call revision stays server-owned (1.329ms)
✔ old numeric preview call keeps the exact single-band request (1.8832ms)
✔ extended preview request projects only allowed keys and explicit full resolution (1.2734ms)
✔ S05 band changes use display state, full resolution, and retain PNG onload hotfix (1.7395ms)
✔ display modes are exclusive, preserve RGB order and reject duplicates (0.6358ms)
✔ entry defaults to backend automatic selection and displays returned RGB wavelengths (0.7782ms)
✔ default LUT is identity for all 256 intensities (0.5426ms)
✔ LUT rejects nonfinite/out of range/gap under 16 and preserves last valid parameters (0.5879ms)
✔ LUT follows clamp and inverse gamma, one table for RGB, alpha unchanged and input untouched (0.4255ms)
✔ manual LUT values stay local and are independent of image request keys (1.629ms)
✔ point coordinates retain [line,sample] and send one-pixel spectra_mean, never region (0.5073ms)
✔ point inspection returns before any edit tool and leaves null gaps visible (0.7597ms)
✔ box mean uses existing half-open endpoints, direction independent, no spectral arithmetic (0.2742ms)
✔ box inspection routes to spectra before edits and has no readiness dependency (0.4801ms)
✔ storeGesture projects exactly point, box or doodle and strips nested extras (2.1047ms)
✔ gesture projection adds no absent variant fields or optional defaults (0.2769ms)
✔ gesture client uses only annotations_draft_forward and preserves server reference (0.3097ms)
✔ gesture store failure reaches caller without a fabricated reference (0.6159ms)
✔ B1/B6 parent folder supports Windows, slash and mixed paths (1.4753ms)
✔ B1 matching is exact, case insensitive and trims only (0.2531ms)
✔ B1 background number 1 is excluded; first ordered foreground match wins (0.2216ms)
✔ B2 catalog returns the canonical code without constructing label fields (0.2373ms)
✔ B2 an absent folder matches after the refreshed label list includes the catalog label (0.1781ms)
✔ B3 matching leaves the input list and labels unchanged (0.2127ms)
✔ B4 folders are derived separately for each cube (0.1617ms)
✔ B5 single-file import with an arbitrary parent has no fallback label or catalog code (0.1915ms)
✔ C4: previous version total and current label-index counts render as separate summaries (24.8834ms)
✔ C4: zero classes and uncertainty are omitted while zero blank pixels remain visible (0.3042ms)
✔ C4: missing overwrite summary cannot suppress the confirmation dialog (0.3794ms)
✔ C1/C2/C3/C7: auto-default uses a touched ref, resets per dataset, and follows the version count (0.3479ms)
✔ C1/C3/C6: overwrite retains the confirmation gate and cancelling only dismisses the dialog (0.2692ms)
✔ projection consumes save response, shows a selectable absolute path and fixed folder command (1.1617ms)
✔ projection failures keep save available and explicitly explain overwrite retry (0.5497ms)
✔ click binds C; Delete and Shift are not independent commands (1.901ms)
✔ 0 is background-only; 1–9 are numeric; unbound or out-of-range labels remain mouse-only (0.7231ms)
✔ Enter / Z / D / E-B-P / arrows / Ctrl+S / space have the specified actions (0.3782ms)
✔ typing never changes labels or undo; disabled settings suppress shortcuts; global chat keys pass through (0.2012ms)
✔ local remapping is deterministic and rejects duplicates/reserved keys without altering server labels (0.4793ms)
✔ each edit reads working again; write-response pixels, queue and statistics are never reconstructed (2.0394ms)
✔ switching cubes and recovering after confirm use only GET working, never diffuse (0.3488ms)
✔ a failed edit propagates its envelope and cannot manufacture a successful redraw (0.5186ms)
✔ R17 label indexes use sort_order plus SQLite BINARY code order, independent of tree grouping (1.1884ms)
✔ local remaining-time estimate derives only from confirmation speed and handles no progress (0.1794ms)
✔ catalog color proximity uses backend colors and the task-card <30 rule (0.2196ms)
✔ viewport transforms preserve [line,sample], bounds, zoom anchors and half-open boxes (0.6819ms)
✔ component wiring has no local label map or undo history and preserves the outer conversation bar (1.9268ms)
✔ plan card renders table, scalar metadata, estimates, aria labels and chosen invalidation (16.0262ms)
✔ all destructive choices require a reason and IPC projects only plan contract fields (38.3013ms)
✔ disabled controls cannot submit and history keeps the plan decision without action buttons (7.9002ms)
✔ all agent operations invoke only agent_forward with exact projection (2.1451ms)
✔ view state, URL, key and mixed-body extras cannot enter IPC (0.2931ms)
✔ structured preflight HTTP status and errors pass through unchanged (0.6702ms)
✔ workspace context projects opaque references and cannot leak display data or geometry (0.2472ms)
✔ server-listed ordinals and names are usable without reimporting files in the current UI (2.5945ms)
✔ legacy lists retain backend order while local names remain local (0.4456ms)
✔ changing cubes clears an old gesture and same-cube followups retain it (0.246ms)
✔ only successful annotation or preprocessing steps cause authoritative result refresh (0.346ms)
✔ workspace SSE rejects paths, unbound geometry, unknown stage and invalid revisions (0.9547ms)
✔ request failures and SSE failures share human-readable error messages (0.3776ms)
✔ curated backend explanations survive both error delivery paths (0.3795ms)
✔ AI preview focus uses the workflow reference rather than queue order or a diffusion identifier (0.396ms)
✔ P1 A1 App owns one session shared by Composer and S01; renderers have no reducer (2.3316ms)
✔ P1 A2 A3 composer hiding and global shortcuts leave S01 input independent (0.9721ms)
✔ P1 A4 A5 smoke stays in S01 and the three columns use current session context (0.8987ms)
✔ P1 A6 A8 retired panel files and rules are absent with only six new layout classes (1.7062ms)
✔ SSE 正常流 retains order and JSON (3.4076ms)
✔ SSE 确认后挂起 retains order and JSON (0.2769ms)
✔ SSE 错误收尾 retains order and JSON (3.7851ms)
✔ SSE 空流 retains order and JSON (0.2111ms)
✔ SSE accepts CRLF, multiline data, comments and final frame at EOF (0.2678ms)
✔ SSE rejects unknown events, missing event, malformed and nonobject data (0.5123ms)
✔ SSE collector retains every rejected step beyond eight (0.4721ms)
✔ approve disables both controls and records executing until response (0.2747ms)
✔ reject immediately closes confirmation card; server result remains ordered (0.2622ms)
✔ pending check accepts ordinary dialogue and sequential checks replace pending id (0.3486ms)
✔ clarify and errors release busy state and keep messages in order (0.2822ms)
✔ summary renderer displays scalars and excludes unexpected objects (0.2603ms)
✔ plan SSE is accepted, accepts dialogue and cannot use the tool-decision path (0.2304ms)
✔ unrecognized approval dialogue keeps its card while terminal outcomes clear it (0.3379ms)
✔ plan actions preserve pending while executing and retain the decision with the original plan (0.3914ms)
✔ plan approval can suspend again at human check and all terminal events clear pending (0.4022ms)
✔ C delete preview opens the impact dialog; only its confirm button sends strict deletion (32.9402ms)
✔ C cancelling or unmounting a deletion confirmation never sends deletion (1.5467ms)
✔ C existing active import never asks confirmation and ignores all_datasets in the UI (0.8175ms)
✔ C only REIMPORT_CONFIRMATION_REQUIRED prompts, with a selected new-id choice and no request until click (1.7277ms)
✔ C reimport cancellation and concurrent active-record conflict never silently retry or reuse (1.9849ms)
✔ C restore requires the UI button, renders refusal reason, and incomplete items cannot restore (1.1598ms)
✔ C S11 recycle summary includes retained space, count, per-item dates and incomplete cleanup refusal (5.9026ms)
✔ chat-selected registered cubes load through the existing fixed get operation (2.0048ms)
✔ catalog and recycle operations use fixed typed requests with explicit confirmation (0.4661ms)
✔ reimport confirmation is sent only from an explicit caller choice (0.4482ms)
✔ C cold catalog follows every page and retains unavailable sources as visible summaries (7.2038ms)
✔ C engine generation clears immediately and an older response cannot replace the new catalog (1.7786ms)
✔ C stale failures and disposed requests cannot overwrite a current success (1.5167ms)
✔ C current catalog failure is shown and explicit retry recovers (1.0685ms)
✔ C three existing imports append only that batch; catalog refreshes global names without expanding visible scope (0.9504ms)
✔ C broken pagination fails instead of looping or silently hiding catalog rows (1.6116ms)
✔ G3 shared displayName uses the server name and preserves the legacy fallback (1.8255ms)
✔ G2 all_datasets refreshes a previously unique name without duplicating records (1.0082ms)
✔ G assistant choices and readable references use exactly the API display name (1.945ms)
✔ only the absent-active recycled-key error promises a new dataset id (1.2075ms)
✔ active records and concurrent active conflicts never open the fresh-id confirmation (0.3084ms)
✔ existing and newly imported messages agree with actual response counts (0.2729ms)
✔ retries and existing imports keep exactly one row per persisted ID (2.0728ms)
✔ batch errors retain source path and reason for the user (0.4461ms)
✔ sample value uses fixed native command and preserves annotation response (2.0807ms)
✔ CSV duplicate confirmation is an explicit second import (0.32ms)
✔ PLS request retains explicit bound runs and only regression CV; seven result labels (0.3677ms)
✔ coefficients use one fixed read-only native operation and exact model id body (0.2663ms)
✔ extents exclude null and non-finite values without changing inputs (5.5392ms)
✔ coordinate mapping covers endpoints, inverted Y, constants and extreme finite domains (0.3204ms)
✔ nice ticks are deterministic, rounded and integer-only for counts or LVs (0.3841ms)
✔ null and non-finite curve points split paths and never interpolate gaps (0.2765ms)
✔ histogram uses sqrt sample count capped at 20, shared rounded edges and grouped counts (1.2233ms)
✔ histogram bins are left-closed with rightmost edge included; rounded inner edges agree with membership (0.3793ms)
✔ one histogram sample becomes a single nonzero-width bin; invalid values produce no bins (0.3827ms)
✔ four evaluation models include curve, scatter, residual and grouped histogram (2.1742ms)
✔ LV markers use saved recommendations verbatim rather than recomputing an elbow (0.8012ms)
✔ empty curve and all non-finite curves show explicit no-data status without axes (0.5779ms)
✔ curve missing values retain separated finite paths and single-point strokes (0.4902ms)
✔ one prediction is a square, maps constant axes to midlines and has one populated histogram bar (0.5464ms)
✔ constant references with varying predictions remain on X midline with an explicit note (0.6646ms)
✔ null metrics never enter chart coordinates or quality calculations (0.756ms)
✔ get_run failure produces four explicit unavailable plots, never blank axes (0.4616ms)
✔ missing LV artifact preserves the three prediction plots and their quality labels (0.4155ms)
✔ undefined predictions from classification runs are explicit, empty arrays remain no-data (0.4709ms)
✔ missing fields and unknown sets are excluded per chart, with an explicit reason when all are unusable (0.3042ms)
✔ half-quantitative label uses backend flag or label and never derives RPD (1.1114ms)
✔ loading has visible messages and a result can render while its curve is still loading (0.2692ms)
✔ error descriptions handle structured native errors and opaque values without secondary throws (0.1739ms)
✔ coefficient chart preserves signed values, zero reference, backend quality and tick targets (0.6321ms)
✔ coefficient refusal: unknown axis (0.1913ms)
✔ coefficient refusal: dimension mismatch (0.0703ms)
✔ coefficient refusal: same dimensions unsafe operator (0.176ms)
✔ coefficient loading, missing artifact and 404 have visible messages without secondary errors (0.1461ms)
✔ coefficient empty and invalid arrays are distinct and never draw malformed nested coefficients (0.1875ms)
✔ coefficient zero line remains inside frame for 1,1,1 (0.2519ms)
✔ coefficient zero line remains inside frame for -3,-3,-3 (0.2013ms)
✔ coefficient zero line remains inside frame for 0,0,0 (0.1599ms)
✔ coefficient zero line remains inside frame for 1,2,3 (0.1506ms)
✔ coefficient zero line remains inside frame for -1,-2,-3 (0.0855ms)
✔ single coefficient is one square; nonascending wavelengths retain artifact order and disclose it (0.3622ms)
✔ six new fixed requests preserve exact bodies and strip input extras (1.3013ms)
✔ map source permits only PNG base64 and positive integer dimensions (0.2665ms)
✔ fixed palette rejects invalid RGB and preserves ordered endpoints (0.1611ms)
✔ clipping disclosure includes foreground totals and both directions (0.112ms)
✔ stages and required scientific warning are explicit (0.1087ms)
✔ components use the client, disclose calibration, progress and independent map errors (0.7016ms)
✔ registered coefficient button is lazy per model and shows pending then success or 404 state (116.8829ms)
✔ preprocess IPC list_recipes: exact projection and sole command (2.3742ms)
✔ preprocess IPC create_recipe: exact projection and sole command (1.614ms)
✔ preprocess IPC get_recipe: exact projection and sole command (0.2299ms)
✔ preprocess IPC add_version: exact projection and sole command (0.2163ms)
✔ preprocess IPC select_recipe: exact projection and sole command (0.2103ms)
✔ preprocess IPC deselect_recipe: exact projection and sole command (0.1792ms)
✔ preprocess IPC list_project_recipes: exact projection and sole command (0.1978ms)
✔ preprocess IPC create_run: exact projection and sole command (0.2024ms)
✔ preprocess IPC list_runs: exact projection and sole command (0.2001ms)
✔ preprocess IPC get_run: exact projection and sole command (0.2528ms)
✔ preprocess IPC compare: exact projection and sole command (0.1949ms)
✔ preprocess IPC get_artifact: exact projection and sole command (0.1831ms)
✔ request bodies omit runtime extras, run guard/block_size, and editor state (0.1877ms)
✔ report is parsed JSON; only sample_spectra uses binary wrapper; 204 stays null (0.1937ms)
✔ recovery inspects only new succeeded summaries and matches recipe in details (2.6354ms)
✔ transport and timeout recover, business errors do not; structured details remain visible (1.5044ms)
✔ submit TRANSPORT automatically restores new matching success; unknown outcome stays pending verification (1.0676ms)
✔ legend resolves index→id→code with backend colors, missing id prefix, unlabeled title (0.2769ms)
✔ S06 component wiring: no transport outside API, no numeric engine / fake preview; global chat unchanged (9.9387ms)
✔ unsupported operations are all marked stage two / not applicable without example metrics (0.2909ms)
✔ operator directory matches explicit R15 names and excludes run B01 / unresolved reference methods (1.4424ms)
✔ axisAfter is pure, crop closed, resample replaces, decomposition removes axis (0.3668ms)
✔ crop→resample→crop supplies EACH current source, never stale saved source (0.2967ms)
✔ schema-direction validation: odd SG, STRICT polynomial bound, derivative order/mode (0.2877ms)
✔ all exposed methods accept valid schema choices; unknown keys and absent components reject (1.0792ms)
✔ no wavelengths disables axis operators; lo<hi, nonempty crop, target finite/increasing enforce (0.301ms)
✔ move/delete/repeat preserve order and compile legal explicit steps (0.1415ms)
✔ target creation is axis-only; chart gaps retain separate strokes and values (0.1614ms)
✔ settings screen starts with five empty text fields, an enabled egress switch, a password input and an unknown key status (10.598ms)
✔ rendered field changes and submit save the six-key config then key, and clear the password (5.1473ms)
✔ GET has_key renders both states without pre-filling a key, and blank key preserves existing credentials (2.768ms)
✔ GET failure disables saving and fields while the rendered cancel button remains usable (3.121ms)
✔ nonempty URL and numeric validation blocks invalid saves without inventing provider limits (3.5653ms)
✔ backend 400 code and detail are rendered and a failed config save never submits the key (1.4295ms)
✔ failed key write reports partial save, clears its input and redacts credentials in errors (2.3428ms)
✔ saving prevents duplicate submits and disposing ignores an in-flight GET (0.8392ms)
✔ App settings entry opens S11 with its embedded form, preserving UI-to-configuration reachability (0.6173ms)
✔ egress checkbox reflects the false value returned by GET (1.1583ms)
✔ unchecking egress saves a boolean false and keeps the returned switch state (0.8548ms)
✔ C SMB and URL prefills become UNC strings, preserving independent empty and absent fields (2.6265ms)
✔ C rendered source and output inputs edit independently and save only the project defaults (15.4545ms)
✔ C browse targets only its field, cancel preserves values, and S11 summary displays saved values without editing (1.7016ms)
✔ C path form failure disables saving; disposal rejects stale GET and double save is suppressed (0.9296ms)
✔ C project path IPC uses fixed ops, strips view extras, normalizes both paths and propagates refusal (1.5184ms)
✔ settings GET and two PUT operations use only settings_forward with exact bodies (2.3257ms)
✔ settings projections exclude credentials and view or route extras from config and responses (0.3146ms)
✔ settings forward preserves the backend 400 envelope unchanged (0.5031ms)
✔ egress false remains boolean through config PUT and GET projections (0.2149ms)
✔ P5 S02 uses props for four cards, recent regression runs and phase plus generation only (1.5219ms)
✔ P5 S09 regression table has only id task status and a client task filter without invented timestamps (1.2328ms)
✔ P5 S09 fetches selected run details and retains backend metrics quality and collapsed leak report (0.3839ms)
✔ P5 S09 preprocess reads only the selected dataset and preserves real time fields and empty states (0.3838ms)
✔ P5 S10 has a data-screen action and S11 embeds the settings form without fake controls (0.3654ms)
✔ P5 inserts four screen cases while preserving source anchors S03 debug text and theme boundary (0.5749ms)
✔ P2 navigation preserves App runId until the results back-to-list action (0.9038ms)
✔ P2 S04 and S03 thumbnails share BandCanvas and viewing updates workspace (0.5307ms)
✔ P2 S08 loads real regression runs and refetches run plus sweep on mount (0.2716ms)
✔ P2 S07 keeps training and internal views while results and source anchors stay intact (0.4719ms)
✔ A1 navigation retains five ordered groups and exactly ten unique screen entries (1.3474ms)
✔ A1 titles cover all eleven Screen values including the viewer below data (0.1514ms)
✔ A1 only s04 redirects its navigation highlight to s03 (0.735ms)
✔ skin guards: annotation-skin.css (1.691ms)
✔ skin guards: preprocess-skin.css (0.3565ms)
✔ skin guards: modeling-skin.css (0.3542ms)
ℹ tests 241
ℹ suites 0
ℹ pass 241
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 789.8815
```

原始文件：[Python-collected-after.txt](E:/AI_Agent/milestone25/evidence/C/Python-collected-after.txt)

```text
src-python/tests/test_display_falsecolor.py::test_mean_does_not_reuse_65536_json_value_limit
src-python/tests/test_display_falsecolor.py::test_mean_one_million_pixel_boundary[1000-200]
src-python/tests/test_display_falsecolor.py::test_mean_one_million_pixel_boundary[1001-400]
src-python/tests/test_display_falsecolor.py::test_display_requests_do_not_change_annotation_working_or_versions

============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1561 tests collected in 2.36s
```

原始文件：[Python-backend-after.txt](E:/AI_Agent/milestone25/evidence/C/Python-backend-after.txt)

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
45 passed, 10 warnings in 6.39s
```

原始文件：[Python-src-after.txt](E:/AI_Agent/milestone25/evidence/C/Python-src-after.txt)

```text
........................................................................ [  4%]
........................................................................ [  9%]
........................................................................ [ 14%]
........................................................................ [ 18%]
........................................................................ [ 23%]
........................................................................ [ 28%]
........................................................................ [ 33%]
........................................................................ [ 37%]
........................................................................ [ 42%]
......................................ss................................ [ 47%]
........................................................................ [ 52%]
........................................................................ [ 56%]
........................................................................ [ 61%]
........................................................................ [ 66%]
........................................................................ [ 71%]
........................................................................ [ 75%]
........................................................................ [ 80%]
........................................................................ [ 85%]
........................................................................ [ 90%]
........................................................................ [ 94%]
........................................................................ [ 99%]
....                                                                     [100%]
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
1514 passed, 2 skipped, 6 warnings in 611.98s (0:10:11)
```

原始文件：[Rust-after.txt](E:/AI_Agent/milestone25/evidence/C/Rust-after.txt)

```text
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `test` profile [unoptimized + debuginfo] target(s) in 6.79s
     Running unittests src\lib.rs (target\debug\deps\spectrum_agent-fc5a2225eca9e0bc.exe)

running 54 tests
test annotation::tests::parameter_edges_and_unicode_note_match_http_contract ... ok
test annotation::tests::bad_types_lengths_and_out_of_range_parameters_are_rejected ... ok
test annotation::tests::only_the_supplied_nonzero_handshake_port_is_used ... ok
test datasets_dev::tests::catalog_contract ... ok
test annotation::tests::project_query_is_strict_then_lowercase_but_dataset_path_is_unchanged ... ok
test annotation::tests::identifiers_cannot_escape_and_version_numbers_are_not_uuids ... ok
test annotation::tests::omitted_parameters_stay_omitted_and_all_prompt_geometries_are_typed ... ok
test annotation::tests::unknown_operations_and_fields_are_structured_and_never_reflect_input ... ok
test datasets_dev::tests::delete_preview_contract ... ok
test annotation::tests::four_management_operations_have_literal_paths_methods_and_bodies ... ok
test annotation::tests::all_nine_operations_have_exact_paths_methods_and_bodies ... ok
test annotation::tests::no_free_url_host_port_path_or_method_can_enter_any_operation ... ok
test datasets_dev::tests::all_operations_use_the_handshake_port_and_fixed_namespace ... ok
test datasets_dev::tests::delete_contract ... ok
test datasets_dev::tests::import_confirmation_defaults_false ... ok
test datasets_dev::tests::no_generic_host_port_path_or_method_can_be_deserialized ... ok
test datasets_dev::tests::recycle_list_contract ... ok
test datasets_dev::tests::preview_legacy_url_is_unchanged_and_optional_fields_allow_rgb_without_band ... ok
test datasets_dev::tests::restore_contract ... ok
test datasets_dev::tests::spectra_mean_has_fixed_post_path_typed_region_and_uuid_guard ... ok
test health::route_tests::closed_routes_always_use_numeric_loopback_and_literal_paths ... ok
test models::tests::fixed_operations_and_methods ... ok
test models::tests::new_ops_reject_proxy_fields_invalid_stages_and_all_id_traversal ... ok
test preprocess::tests::actual_generation_guard_used_by_command_rejects_stale_or_nonready ... ok
test models::tests::registry_inference_six_fixed_operations ... ok
test preprocess::tests::four_uuid_error_codes_cover_every_identifier_field ... ok
test preprocess::tests::all_twelve_destinations_methods_and_exact_bodies ... ok
test preprocess::tests::builder_sets_three_hundred_seconds_without_waiting ... ok
test preprocess::tests::manual_base64_matches_rfc4648_vectors ... ok
test annotation::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test datasets_dev::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test preprocess::tests::malformed_http_envelope_uses_generic_error ... ok
test preprocess::tests::json_success_is_unchanged_and_post_body_is_forwarded ... ok
test preprocess::tests::binary_payload_and_wrapper_filename_are_also_sensitive_checked ... ok
test preprocess::tests::unknown_fields_ops_types_artifact_values_and_free_destinations_are_rejected ... ok
test preprocess::tests::uuid_copy_and_port_boundary_preserve_closed_destination ... ok
test preprocess::tests::redirects_are_not_followed ... ok
test annotation::tests::label_body_limit_counts_serialized_utf8_and_business_validation_stays_in_python ... ok
test preprocess::tests::raw_and_canonical_tokens_never_cross_bridge ... ok
test datasets_dev::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test preprocess::tests::structured_http_error_preserves_three_fields ... ok
test preprocess::tests::only_204_maps_empty_body_to_null_not_200 ... ok
test annotation::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test preprocess::tests::report_stays_json_and_nonartifact_binary_is_rejected ... ok
test datasets_dev::tests::response_identity_precedes_status_and_body ... ok
test annotation::tests::response_identity_precedes_status_and_body ... ok
test preprocess::tests::identity_checks_precede_http_status_and_body ... ok
test models::tests::six_new_ops_reach_loopback_with_native_auth_and_exact_bodies ... ok
test preprocess::tests::binary_artifact_roundtrips_and_keeps_filename ... ok
test datasets_dev::tests::declared_and_streaming_response_limits_are_enforced ... ok
test preprocess::tests::declared_and_streaming_limits_reject_above_eight_mib ... ok
test annotation::tests::declared_and_streaming_response_limits_are_enforced ... ok
test models::tests::rejects_general_proxy_extra_fields_traversal_and_oversize ... ok
test annotation::tests::an_exactly_eight_mib_json_response_is_allowed ... ok

test result: ok. 54 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.23s

     Running unittests src\main.rs (target\debug\deps\spectrum_agent-9760c85afe553455.exe)

running 8 tests
test boot::tests::before_timeout_wait_and_first_attempt_precedes_give_up ... ok
test exports_tests::export_folder_rejects_paths_and_malformed_ids ... ok
test boot::tests::final_timeout_is_fifteen_seconds_from_window_shown ... ok
test boot_monitor_tests::engine_retry_keeps_healthy_document_until_real_navigation ... ok
test exports_tests::export_folder_is_scoped_to_a_canonical_cube_uuid ... ok
test boot::tests::healthy_document_always_waits_across_generations ... ok
test boot_monitor_tests::reload_budget_is_independent_and_activations_do_not_reset_it ... ok
test boot::tests::reload_boundary_4999_5000_and_5001_ms ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\agent_settings_forward.rs (target\debug\deps\agent_settings_forward-33848812934a45f0.exe)

running 12 tests
test both_commands_reject_stale_generation_or_non_ready_phase ... ok
test project_paths_fixed_contract_empty_values_and_unknown_fields ... ok
test agent_three_operations_and_two_body_shapes_have_literal_routes ... ok
test settings_only_existing_get_put_operations_and_no_key_in_config ... ok
test whitelist_rejects_paths_methods_and_mixed_message_shapes ... ok
test workspace_events_keep_only_bound_scalar_references ... ok
test http_errors_keep_status_and_envelope_redirects_not_followed ... ok
test sse_empty_done_suspended_human_check_and_error_close ... ok
test settings_key_and_escaped_credentials_never_cross_error_or_success_envelopes ... ok
test identity_is_checked_before_status_length_and_body_for_both_commands ... ok
test project_paths_visible_in_success_but_rejected_in_error_envelopes_and_identity_checked_first ... ok
test declared_and_streaming_limits_are_enforced_for_both_commands ... ok

test result: ok. 12 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.54s

     Running tests\annotations_draft_forward.rs (target\debug\deps\annotations_draft_forward-07265277f3718ab2.exe)

running 8 tests
test paths_methods_candidates_and_extra_fields_are_rejected ... ok
test six_literal_routes_and_methods ... ok
test binary_requires_octet_stream ... ok
test raw_and_canonical_credentials_never_escape ... ok
test identity_precedes_status_body_and_limit ... ok
test http_errors_and_redirects_preserve_status_and_context ... ok
test declared_and_streamed_limits_json_and_binary ... ok
test binary_exact_limit_and_base64_padding ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.82s

     Running tests\causality.rs (target\debug\deps\causality-36e4b6d833a263b9.exe)

running 2 tests
test midnight_files_and_preexisting_partial_line_are_handled_without_fallback ... ok
test only_new_complete_lines_with_own_integer_pid_in_utc_window_can_be_cause ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.03s

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

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 6.28s

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

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.19s

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

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.08s
```

原始文件：[clippy-after.txt](E:/AI_Agent/milestone25/evidence/C/clippy-after.txt)

```text
    Checking spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 2.49s
```

原始文件：[build-after.txt](E:/AI_Agent/milestone25/evidence/C/build-after.txt)

```text

> spectrum-agent@0.1.0 build
> tsc --noEmit && vite build

vite v8.3.4 building client environment for production...
transforming...
✓ 93 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.37 kB │ gzip:   0.28 kB
dist/assets/index-C-133kLj.css   26.75 kB │ gzip:   5.83 kB
dist/assets/index-lKAs0dnO.js   402.00 kB │ gzip: 127.00 kB

✓ built in 180ms
```

原始文件：[write-files-after.txt](E:/AI_Agent/milestone25/evidence/C/write-files-after.txt)

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

原始文件：[cube-columns-after.txt](E:/AI_Agent/milestone25/evidence/C/cube-columns-after.txt)

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

原始文件：[project-paths-first.txt](E:/AI_Agent/milestone25/evidence/C/project-paths-first.txt)

```text
.................                                                        [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
17 passed, 1 warning in 7.79s
```

原始文件：[openapi-update.txt](E:/AI_Agent/milestone25/evidence/C/openapi-update.txt)

```text
OpenAPI updated; project GET/PUT paths: True
```

原始文件：[anchors-after-C.txt](E:/AI_Agent/milestone25/evidence/C/anchors-after-C.txt)

```text
src/App.tsx:56:  const [records, setRecords] = useState<CatalogRecord[]>([]);
src/App.tsx:111:    setWorkspace({}); setRecords([]); setRefreshVersions({}); setNavigation(null); setWorkspaceName(''); setPreviewCandidates({});
src/components/datasets/actions.ts:47:          await callbacks.imported(result.datasets);
src/components/datasets/types.ts:15:  all_datasets: DatasetRecord[];
src/components/datasets/types.ts:38:export type DatasetTransport = {
src/components/datasets/types.ts:51:export function mergeRecords(previous: DatasetRecord[], incoming: DatasetRecord[]): DatasetRecord[] {
src/components/datasets/types.ts:52:  const merged = new Map(previous.map(record => [record.id, record]));
src/components/datasets/types.ts:53:  for (const record of incoming) merged.set(record.id, record);
src/components/datasets/types.ts:54:  return [...merged.values()];
src-python/spectrumagent/api/schemas.py:36:    all_datasets: list[DatasetRecord]
src/components/datasets/display_names.test.ts:14:test('G2 all_datasets refreshes a previously unique name without duplicating records', () => {
src-python/spectrumagent/api/registry.py:121:            db.execute("CREATE TABLE IF NOT EXISTS dataset_registry (id TEXT PRIMARY KEY, header_key TEXT NOT NULL, raw INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(header_key,raw))")
src-python/spectrumagent/api/registry.py:177:            active = db.execute('SELECT id,payload FROM dataset_registry WHERE header_key=? AND raw=?',
src-python/spectrumagent/api/registry.py:199:            db.execute('INSERT INTO dataset_registry (id,header_key,raw,payload,project_id) VALUES (?,?,?,?,?)',
src-python/spectrumagent/api/registry.py:231:            all_records = [batch_records.get(identifier) or DatasetRecord(id=identifier,
src-python/spectrumagent/api/registry.py:258:    def readable(self, identifier, raw=None):
src-python/spectrumagent/api/registry.py:262:            current = read_header(Path(stored.header_path), Path(stored.data_path), raw=mode)
src/components/datasets/api.ts:7:export type Request = { op: 'import'; path: string; raw: boolean; confirm_new?: boolean } | ({ op: 'preview'; id: string } & PreviewOptions)
src/components/datasets/api.ts:45:  const result = await open({ directory: true, multiple: true, filters: [{ name: 'Hyperspectral', extensions: ['hdr', 'img', 'raw', 'bin', 'json', 'txt'] }] });
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
src-tauri/src/settings.rs:12:#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
src-tauri/src/settings.rs:13:pub enum SettingsRequest {
src-tauri/src/settings.rs:69:    pub fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
src-tauri/src/settings.rs:107:        let paths: Vec<&str> = [fields.source_path.as_str(), fields.output_root.as_str()]
src-tauri/src/settings.rs:113:    let secrets = match request {
src-tauri/src/settings.rs:114:        SettingsRequest::PutKey { key } => vec![key.as_str()],
src/components/settings/settings-forward.ts:8:export type SettingsRequest = { op: 'get_llm' } | { op: 'put_llm'; body: LLMConfig } | { op: 'put_key'; key: string }
src/components/settings/settings-forward.ts:28:  const forward = <T>(request: SettingsRequest) => send<T>('settings_forward', { request });
src-python/spectrumagent/api/settings.py:14:def make_router(paths):
src-python/spectrumagent/api/settings.py:16:    router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
src-python/spectrumagent/api/settings.py:22:    @router.get("/llm")
src-python/spectrumagent/api/settings.py:26:    @router.put("/llm")
src-python/spectrumagent/api/settings.py:31:    @router.put("/llm/key")
src-python/spectrumagent/app.py:54:    app.include_router(make_settings_router(paths))
src-python/spectrumagent/app.py:93:        if request.url.path.startswith("/api/v1/settings") or request.url.path.startswith("/api/v1/agent"):
src-python/spectrumagent/app.py:110:        if (request.url.path in LABEL_PATHS or request.url.path == "/api/v1/datasets" or request.url.path.startswith("/api/v1/datasets/") or request.url.path.startswith('/api/v1/recycle') or request.url.path.startswith("/api/v1/preprocess") or request.url.path.startswith("/api/v1/settings") or request.url.path.startswith("/api/v1/agent") or request.url.path.startswith("/api/v1/annotations/") or request.url.path.startswith("/api/v1/models")) and response.status_code != 401:
src-python/spectrumagent/api/openapi.json:644:    "/api/v1/settings/projects/{project_id}/paths": {
src-python/spectrumagent/api/openapi.json:738:    "/api/v1/settings/llm": {
src-python/spectrumagent/api/openapi.json:794:    "/api/v1/settings/llm/key": {
src/components/datasets/types.ts:11:};
src/components/datasets/types.ts:17:};
src/components/datasets/types.ts:38:export type DatasetTransport = {
src/components/datasets/types.ts:39:  get: (id: string) => Promise<DatasetRecord>;
src/components/datasets/types.ts:40:  chooseDirectories: () => Promise<string[] | null>;
src/components/datasets/types.ts:41:  importDirectory: (path: string, raw: boolean, confirmNew?: boolean) => Promise<ImportResponse>;
src/components/datasets/types.ts:42:  catalog: (limit?: number, offset?: number) => Promise<CatalogPage>;
src/components/datasets/types.ts:43:  deletePreview: (id: string) => Promise<DeletePreview>;
src/components/datasets/types.ts:44:  delete: (id: string, previewToken: string, confirm: boolean) => Promise<DeleteResult>;
src/components/datasets/types.ts:45:  recycleList: () => Promise<RecycleList>;
src/components/datasets/types.ts:46:  restore: (deletionId: string, confirm: boolean) => Promise<{ deletion_id: string; cube_id: string; restored: boolean }>;
src/components/datasets/types.ts:47:  preview: (id: string, selection: number | PreviewOptions) => Promise<Preview>;
src/components/datasets/types.ts:48:  spectraMean: (id: string, region: SpectrumRegion) => Promise<MeanSpectrum>;
src/components/datasets/types.ts:49:};
```

## 界面实测证据

[浏览器验收步骤与边界](E:/AI_Agent/milestone25/evidence/C/browser-acceptance.md)；下图为合成 IPC 环境中的实际组件界面。

![删除影响清单](E:/AI_Agent/milestone25/evidence/C/ui-delete-preview.png)

![S11 项目路径与回收站占用](E:/AI_Agent/milestone25/evidence/C/ui-settings-summary.png)
