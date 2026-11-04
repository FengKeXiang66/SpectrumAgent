# TASK-25 D 段交付：逐条验收与完整回归

D 段验收通过。新增 7 个参数化执行项，补齐带身份校验的 HTTP 全生命周期、全部业务表孤儿扫描、真实终止进程后的新引擎启动恢复；生产源码、任务卡、既有测试均未修改。A / B / C 已分别提交 9ad8268 / d8bb622 / cb97eeb，本报告与 D 测试、证据同一提交；D 提交号以收口 git log 为准，未 push。

唯一权威卡为 dfa67a7（315 行，按 cb97eeb 校准）。开工 git status 干净；按 §0.1 跑本段当前基线，按 §0.2 全表 grep -n，范围类逐行展开。D 收口锚点全文与开工完全一致，无待备卡方校准的新行号。执行方没有改写任务卡。

执行模式：Windows PowerShell；本地 .venv Python 3.12.13 / SQLite 3.50.4；Node 只用源码 glob；Rust debug 全套 test / all-targets clippy；构建 tsc --noEmit + Vite。Python 按 backend/tests、src-python/tests 分段实跑，collected 单独取数；没有裸跑 node --test，没有安装依赖。所有源数据与故障目录均为新建合成夹具。

## 改动文件清单

- [新增 D 自动验收测试](E:/AI_Agent/src-python/tests/storage/test_task25_acceptance.py)：HTTP 删除→恢复→再次删除→服务端时钟到期清理；源目录清单 / 文件内容哈希 / mtime；项目资产与不可变审计；全部业务表标量与 JSON 数组引用扫描；四类未声明外键反证；真实杀进程 + 新解释器启动隔离，以及持久映射窗口 + 新解释器启动归位。
- [D 证据目录](E:/AI_Agent/milestone25/evidence/D)：开工 / 收口原文、专项原文、两次失败历史、可重跑命令、UI 夹具 / AX 步骤 / IPC 记录 / 截图、逐文件写点与锚点复核。完整逐文件列表见本报告末尾。
- [本报告](E:/AI_Agent/milestone25/REPORT-D.md)。未改任何产品接口、生产代码、旧测试、旧阶段证据或权威卡。

## 数字口径与回归

| 执行模式 / 取数命令 | D 开工 | D 收口 |
|---|---|---|
| node --test "src/**/*.test.ts" | 241 pass / 0 fail | 241 pass / 0 fail |
| python -m pytest backend/tests src-python/tests --collect-only -q | 1561 collected | 1568 collected，新增 7 |
| python -m pytest backend/tests -q | 45 pass | 45 pass |
| python -m pytest src-python/tests -q | 1514 pass / 2 skip | 1521 pass / 2 skip |
| cargo test，逐行数 test result | 13 组全绿 | 13 组全绿（从本轮 stdout 计得，非写死阈值） |
| cargo clippy --all-targets -- -D warnings | 通过，0 error | 通过，0 error |
| npm run build（tsc --noEmit + Vite） | 通过 | 通过 |
| 卡内模式 grep 的生产写点发现域 | 15 文件 | 15 文件 |

1568 collected = backend 45 + src 1521 pass + src 原有 2 skip。1561 与更早的 1489 / 1506 / 1544 均为各阶段事实，不作跨段阈值。新测试 7 项另计；既有测试修改 / 删除均为 0，未通过删改用例凑数字。专项 pytest 的 7 / 87、前端专项 21 属于完整回归的子集，不能加总冒充新增测试。

全部环境变量、工作目录、命令与原文文件对应见 [COMMANDS.md](E:/AI_Agent/milestone25/evidence/D/COMMANDS.md)。Python 开工前 C 空闲 8180072448 bytes，收口前 8158597120 bytes；完整开工运行结束后只清本轮已结束的 OS Temp/t25do，先核绝对路径、父路径及重解析点。没有删除源数据、用户产物或回收站。

## §5 A 组：只读红线

| 验收项 | 取数命令 / 原文 | 判定与含义 |
|---|---|---|
| 删除 / 恢复 / 清理源目录零改动 | python -m pytest src-python/tests/storage/test_task25_acceptance.py -vv -s；acceptance.txt 的 D_ACCEPTANCE_LIFECYCLE | before / after_delete / after_restore / after_purge 完全相同；文件列含 size / SHA-256 / mtime_ns，并包括根目录和子目录项，能发现新建空目录 |
| 写源、删源拒绝并留痕 | 同上；source_denials | 实际调用 resolve_write(...).write_text 与 storage.unlink，各在触发文件写前抛 WRITE_TO_SOURCE_DENIED；审计动作 D_SOURCE_WRITE / DELETE 均 DENY，源内容仍相同 |
| 全部 unlink / rmtree 收口 | COMMANDS.md 的原始 grep；production-delete-grep.txt / guard-call-sites.txt | 所有业务调用使用 storage.unlink / rmtree；守卫内封装执行 resolve_delete 后的底层动作，自检 probe.unlink 在 startup=True 的 _resolve 后执行，不是未授权业务出口 |
| 审计 INSERT 不递归 | python milestone25/evidence/A/storage_probe.py；guard-probe.txt；backend-focused.txt 的独立通道测试 | 一次被审计 resolve 只调用守卫 1 次；持有业务 DB writer 时独立审计仍成功；不是把审计错误吞掉 |
| 建 trash → 自检 → 放行业务 | 同上 startup_order；D 新启动测试 events | directories_created → self_check → business_ready；回收协调器另外须等 recycle_reconcile_started → recycle_business_ready 才放行业务。events 中重复初始化事件原样保留，未删成理想顺序 |
| 注入自检失败即拒写 | guard-probe.txt / backend-focused.txt | injected_selfcheck_failure 与 business_after_failed_selfcheck 均 STORAGE_SELF_CHECK_FAILED；日志出现 STORAGE_SELF_CHECK_FAILED 是预期故障注入，不是遗留未通过项 |
| 有界缓存与审计只增 | guard-probe.txt / backend-focused.txt | 容量 2 反证溢出、告警 AUDIT_BUFFER_OVERFLOW、刷入 2 条并标 flushed_at；UPDATE / DELETE 原始 SQL 均被 APPEND_ONLY_AUDIT 拒绝 |

## 生产写目标逐文件复核

取数：COMMANDS.md 中卡内写点模式 grep，再排除 /tests/，文件去重；完整原文 production-write-grep.txt / after-write-files.txt，边界调用上下文 guard-call-sites.txt。以下 15 文件与开工一致。卡内 grep 不包含所有 DB open，因此另列 connect_database 与审计私有通道，避免把发现域当成全部实现。

| 文件 | 目标根与判定 |
|---|---|
| backend/diagnostics.py | paths.testdata 及其临时子目录，属于 paths.root；诊断原有 GeoTIFF 打包自检，不是新增格式入口 |
| backend/handshake.py | paths.run 下 handshake 临时文件 / 正式文件 / 清理，属于 paths.root；写、replace 两端、unlink 受守卫 |
| backend/logging_config.py | paths.logs 下每日 jsonl，属于 paths.root；首次 open 与每次 LOG_APPEND 都授权 |
| backend/paths.py | create_directories 是卡 §2.3 明确初始化例外：validate_bootstrap 后先建 trash 等本地目录，再 initialize 自检；没有业务阶段的旁路 |
| backend/smoke.py | 原有 paths.testdata 合成 ENVI，属于 paths.root；save_image 调用前授权；没有写用户源数据 |
| agent/mat.py | paths.exports 下本 cube/version 产物和临时目录，属于 paths.root；memmap / savemat 前授权，临时清理仍守卫 |
| annotation/projection_io.py | root/projects/<project_id>/projection.json 与 root/exports/<cube_id>；均本地根内，项目配置不进入 cube 删除链 |
| annotation/session.py | AppPaths.snapshots 实际为 root/annotations，按 snapshot_ref 精确选版本目录；临时、备份、覆盖清理均守卫，保留 unreferenced/keep.json |
| api/registry.py | 本地 paths.database.parent 建目录，connect_database 受守卫；NAS/source 只读取并登记为保护源 |
| modeling/inference.py | root/inferences/<run_id>，memmap / np.save / map JSON / 失败清理均守卫 |
| modeling/run.py | root/models/<run_id>，模型 JSON / 失败清理均守卫 |
| preprocess/recipes.py | 本地 paths.database.parent，SQLite 经 connect_database 授权 |
| preprocess/run.py | root/preprocessed/<cube_id>/<run_id>；np.savez 的 stream 已由 resolve_write(...).open('wb') 取得；改名两端与失败清理守卫 |
| storage/guard.py | 单一业务写 / 删出口；系统临时目录为另一个允许根，配置输出根当前 None；_audit_connect 仅固定本地 audit_database、复核根和源边界，不调用业务守卫以防递归 |
| storage/recycle.py | root/trash/<deletion_id>、隔离 root/trash/_orphan、恢复到原本地产物目录；所有 move 调 storage.replace、清理调 storage.rmtree，manifest 写 resolve_write |

backend/database.py 虽不命中原始文件写点模式，SQLite open 明确通过守卫，PRAGMA foreign_keys=ON。project_path_settings 只写该 SQLite 的显式四列；source_path / output_root 只为值，不成为文件写目标，output_enabled 服务端 false、实际产物仍 paths.root。

## §5 B 组：回收站

共同取数命令 `python -m pytest src-python/tests/storage/test_task25_acceptance.py -vv -s`，原文 acceptance.txt；并用 `python -m pytest src-python/tests/storage/test_guard.py src-python/tests/storage/test_recycle.py src-python/tests/data/test_api.py src-python/tests/agent/test_project_paths.py -vv` 补查现有全部专项，原文 backend-focused.txt。

| 验收项 | 结果及对应断言 |
|---|---|
| 删除：DB 主行与所有关联业务行移出 | HTTP 200 且 boot_id / pid 身份头正确；按卡 TABLES 顺序清单对应业务行均 0，全部业务表扫描 findings=[] / foreign_key_check=[] |
| 文件原位置无 JSON、回收站齐全 | 每个 preview 产物根原位不存在；trash 下逐个文件比 SHA-256 / mtime；annotations/<cube>/v1/annotation.json 存在；项目 projection 与未引用快照 keep.json 保留 |
| 30 天占用不提前释放 | 未到期 purge 返回 []、批次目录存在；recycle total_bytes 等于实际 trash 文件大小之和，包含恢复 manifest，不错误等同 preview 产物 bytes |
| 恢复 id 与历史全复原 | HTTP restore 返回同 cube id；全部原始业务行逐行等于 before，标注版本、预处理、训练、推理台账和产物均复原；项目路径、标签 / recipe / skill 与不可变审计均保持 |
| 同路径冲突拒绝并审计 | backend-focused 的 test_reimport_and_conflict 通过；额外 reimport-isolation.txt 实测 RESTORE_CONFLICT(409) 与 RESTORE_DENIED，未覆写新活跃记录 |
| 到期物理清理与不可变审计 | 服务端 clock 推进 31 天，purge 精确返回该 deletion_id，物理目录不存在，该批 recycle_item 清空；DELETE=2 / RESTORE=1 / PURGE=1，旧审计前缀逐行相同，UPDATE / DELETE 触发器拒绝 |
| 真正 move 后、commit 前杀进程 | 子进程完成 storage.replace 后写 marker 并阻塞；父进程 kill，返回码 1。SQLite 回滚，bin / item 未提交、业务原行完整；父进程不调用 reconcile，新解释器 create_app 自动完成隔离 |
| 无映射隔离 | 全部原产物文件在原位或单个 _orphan 目录中找到，SHA-256 / mtime 相同；ORPHAN_QUARANTINE=1、健康记录 / cube / 同键保护生效；不自动归位、不自动删除 |
| 有映射归位 | 独立构造“有效 bin 行不存在而持久 recycle_item 映射仍在”的恢复窗口，新解释器启动归位全部产物、清空该 trash 文件夹，ORPHAN_ROLLBACK=1；这是映射窗口注入，不冒充第二次真实杀进程 |
| 对账 gate 与隔离后拒写 | 新引擎构造后显式注入 ready=false，用真实身份 HTTP 验证导入 / 标注 / 训练 / 再删除四项均 503；不是声称服务构造前已可发 HTTP。隔离完成后另直接调用 get / import / preview / delete 仍 503，防止只检查 ready 而漏 cube / key |
| 映射损坏 / 目录缺失 / 并发长任务 | backend-focused 中 INCOMPLETE、路径篡改、move / restore / commit 失败补偿、跨 cube 训练拒单删、stream lease 与 busy 测试全部通过；没有为了验收放宽守卫或 DraftStore 锁 |

## 孤儿检查（与不可变历史区分）

扫描器从 sqlite_master 发现所有当前业务表，不只遍历删除 TABLES；检查 cube_id / version_id / annotation_version_id / preprocess_run_id / model_id / run_id，及 cube_ids / annotation_version_ids / preprocess_run_ids JSON 数组。输出每张表行数、实际检查的引用值数、FK 与 findings；同时递归验证 agent_session.context_json 不含已删 cube / version / run。

llm_call、agent_round、agent_step、agent_plan_action 与 recycle_* 是刻意保留的历史 / 存档，单独列入 excluded_archives。测试真实插入含旧 cube id 的不可变审计行，删 / 恢复 / 清理后逐行比较不变，不能把保留历史误判为业务悬空，也没有清掉它们来让扫描变绿。

四条反证另造不属于固定删除清单、且没有声明外键的 d_reference_probe 表，分别种 cube_id / version_id / run_id / cube_ids 孤儿：PRAGMA foreign_key_check 都为 []，扫描器仍必须发现 missing-object；若只做 FK 检查或只扫描删除清单会红。原文 orphan-counterexamples.json 从 acceptance.txt JSON 原样解析，仅格式化缩进。

## §5 C 组：列表、重新导入与项目路径

前端取数命令 `node --test src/components/datasets/catalog.test.ts src/components/datasets/actions.test.ts src/components/datasets/display_names.test.ts src/components/settings/project-paths.test.ts`；21 pass 原文 frontend-focused.txt。后台四象限 / 竞态 / SQL 冲突 / 整批原子性原文 backend-focused.txt。

| 验收项 | 当前执行证据 |
|---|---|
| 冷启动 + 换代自动加载，旧响应不覆盖 | catalog 测试通过；浏览器冷启动有 4 条，含可见失效源；暂扣第 2 代目录响应 → 第 3 代加载 → 释放旧响应，仍显示第 3 代四条 |
| 三个已有项仅合并本批 | catalog / actions 测试构造 all_datasets 含未选项，断言只追加 result.datasets；浏览器显示“本次选中 3 个（新增 0 / 已有 3）”，原四条不增加。冷启动本应显示全活跃集合，因此页面四条不减少，不拿这个界面现象冒充批次隔离的唯一证明 |
| G2 保持 | display_names.test.ts:14 原测试未改且绿；catalog 刷新重名，旧 all_datasets 契约保留 |
| 有活跃、无回收站 | 四象限用例的 raw 键 / confirm 两态均通过，existing=true / imported=0，id 保持，前端无新建确认 |
| 有活跃、有回收站 | 四象限和 D isolation probe 均通过，未带 / 带 confirm_new 都返回相同活跃 id；浏览器再次导入不弹新建确认，显示已有 |
| 无活跃、有回收站 | 无确认 409 REIMPORT_CONFIRMATION_REQUIRED；人点确认后 id 新建且 existing=false / imported=1；isolation probe 逐表检查全部关联业务台账为 0、无新 id 的旧快照 / exports / preprocess 路径，旧内容仍留 trash |
| 两者皆无 | 四象限首次导入新 id，summary 与实际新增一致 |
| 并发出现活跃 | 双 Registry / 两个真实读事务 Barrier 测试，一个成功，一个 REIMPORT_ACTIVE_EXISTS(409)；UNIQUE 冲突结构化且整批预检原子测试通过 |
| 确认文案仅无活跃+有回收站 | actions 测试校验不提前发确认请求、取消 / 卸载不写、竞态不静默重试；浏览器新建选项默认选中且写清 id / 从头标注 / 30 天 / 双份空间 |
| S03 / S11 路径只存配置 | 前端表单 5 项与 Python project_paths 17 参数化项全绿；Rust settings forward 新契约 / 伪造身份拒绝包含完整 cargo test；OpenAPI 原测试全绿；页面 UNC 预填、保存及 S11 当前值一致，output_enabled false / data_root 实际本地根 |
| 路径不出域 | Python 专项以 MockTransport 检查实际 LLM 序列化请求体、工具摘要、日志均不含项目路径；不是实际外部模型调用；不新增工具、不打开输出根 |

浏览器使用真实 App 组件与合成内存 IPC，未启动 sidecar、未连接 NAS / LLM、未触碰用户文件。源码夹具 browser-harness.tsx 可复跑；原始 AX 步骤 ui-steps.json、页面公开 IPC 记录 ui-ipc-ledger.json、截图 ui-generation-race.png / ui-delete-preview.png / ui-settings-summary.png。所有点击经 cua_repl 可见控件，未通过脚本改变 React 状态。

![D 合成 IPC 页面：S11 路径 / 回收站 / 禁运清单](E:/AI_Agent/milestone25/evidence/D/ui-settings-summary.png)

## 新增测试什么情况下会红

| 新增执行项 | 反证触发条件 |
|---|---|
| HTTP lifecycle，1 项 | 源文件或目录变化；写源 / 删源未拒或漏审计；业务 / JSON 引用残留；误删项目 / 历史审计；恢复行 / 文件 / id 丢失；30 天内清理；到期不清理；篡改 append-only 审计成功 |
| orphan scanner，4 参数化项 | 仅依赖 FK 或固定 TABLES，无法发现未声明外键表中的标量 / JSON 数组悬空 |
| fresh engine recovery，2 参数化项 | 未真正到 move 窗口；新解释器没自动对账；有映射没归位；无映射误删 / 自动归位 / 未隔离；原产物丢失；gate 或 cube / key fail-closed 漏判 |

没有空断言。D 独立 isolation probe 还会在新 id 继承旧台账、活跃已有仍弹确认 / 生成新 id、恢复覆盖新 id 或拒绝不审计时红；此探针不在 pytest collected 内，不冒充新增第 8 项。

## 失败历史与限制

首次补充验收 2 failed / 5 passed，次轮 1 failed / 6 passed，均保留原文。三处错误均在新增验收：把 preview 产物 bytes 当含 manifest 的实际 trash 占用；把 registry.get 返回元组当 DatasetRecord；把到期批次清理错误断言为全库 recycle_item 必须为 0（先前恢复批次历史仍合法保留）。分别改为实际磁盘占用、registry.record、按 purged deletion_id 查询。没有修改生产代码来迎合错误测试，最终独立专项及完整回归全绿。

静态 grep 的首次带反斜杠命令在 Windows 参数传递报 Unmatched (；随即改为 -f write-pattern.txt 读取原始模式并检查退出码，最终有效输出完整保留。此前失败的空输出没有被用作“无写点”证据。浏览器曾用 label 精确定位 select 未匹配，按实际 DOM select 重定位成功；不是产品保存或恢复失败。

暂存后全域 git diff --cached --check 报出首轮 pytest 失败原文的两处空白行尾，以及前后 cargo 原文各一个末尾空行，证据 raw-log-whitespace-check.txt。保留终端原文，不修剪日志冒充原始输出；对新增 .py / .md / .ps1 / .tsx / .html / .json 单独执行同一 whitespace 检查，exit=0。verify-scope.txt 中 Tracked_diff_check 是暂存前对已跟踪 diff 的检查，不能替代这里的新文件检查。

未决项：本卡 A / B / C / D 验收没有未通过项，无锚点漂移，无待用户裁定的接口。两条原有 Python skip 与现有 warning 原样保留，未伪报已运行。git 的全局 ignore 配置访问 warning 原样保留，不影响 status 的空 stdout。

遗留债仍严格按 §1：FR-A12 / FR-A13 全量、NAS 只读挂载 / 凭据 / 连通性、实际输出根与 run manifest 另立卡；新格式、检索、其他域与报告导出不在本轮范围。D 未做真实 NAS、打包安装态或外部 LLM 联调，不用浏览器夹具 / MockTransport 冒充。当前输出根仅保存、不生效，产物仍本地 paths.root。

## 原文附件（开工与收口均为本轮实跑）

完整 collected 名单分别在 before-Python-collected.txt / after-Python-collected.txt；报告仅截最后一行，不把 collected 当 pass。其他如下均贴完整 stdout/stderr。相关命令统一见 COMMANDS.md，逐项结果可直接对照。

### before-head.txt

完整文件：[before-head.txt](E:/AI_Agent/milestone25/evidence/D/before-head.txt)

```text
dfa67a7 docs(task25): 按 cb97eeb 全量校准锚点与 C 段基线（解除 D 段即停）
```

### before-status-start.txt

完整文件：[before-status-start.txt](E:/AI_Agent/milestone25/evidence/D/before-status-start.txt)

```text

```

### before-status-stderr.txt

完整文件：[before-status-stderr.txt](E:/AI_Agent/milestone25/evidence/D/before-status-stderr.txt)

```text
warning: unable to access 'C:\Users\Administrator/.config/git/ignore': Permission denied
warning: unable to access 'C:\Users\Administrator/.config/git/ignore': Permission denied
```

### before-versions.txt

完整文件：[before-versions.txt](E:/AI_Agent/milestone25/evidence/D/before-versions.txt)

```text
3.12.13 (main, May 10 2026, 19:35:37) [MSC v.1944 64 bit (AMD64)]
SQLite 3.50.4
v24.19.0
11.17.0
rustc 1.99.1 (58cf8f9c3 2026-10-13)
cargo 1.99.1 (5f94df478 2026-08-27)
```

### before-node.txt

完整文件：[before-node.txt](E:/AI_Agent/milestone25/evidence/D/before-node.txt)

```text
✔ block clicks retain the legacy geometry and omit label_id for erase and uncertain (2.8725ms)
✔ IPC superpixels: exact Rust variant, one command, no arbitrary route (0.4454ms)
✔ IPC diffuse: exact Rust variant, one command, no arbitrary route (0.3207ms)
✔ IPC regions: exact Rust variant, one command, no arbitrary route (0.2156ms)
✔ IPC undo: exact Rust variant, one command, no arbitrary route (0.231ms)
✔ IPC working: exact Rust variant, one command, no arbitrary route (0.2214ms)
✔ IPC validate: exact Rust variant, one command, no arbitrary route (0.2059ms)
✔ IPC save: exact Rust variant, one command, no arbitrary route (0.2342ms)
✔ IPC versions: exact Rust variant, one command, no arbitrary route (0.2653ms)
✔ IPC version_overlay: exact Rust variant, one command, no arbitrary route (0.2946ms)
✔ IPC projects: exact Rust variant, one command, no arbitrary route (3.0282ms)
✔ IPC labels: exact Rust variant, one command, no arbitrary route (0.2488ms)
✔ IPC add_label: exact Rust variant, one command, no arbitrary route (0.2157ms)
✔ IPC catalog: exact Rust variant, one command, no arbitrary route (0.1385ms)
✔ optional defaults are left to Python; all prompt and geometry forms retain [line,sample] (0.2745ms)
✔ all three structured label bodies match Python and carry the working project id (0.1827ms)
✔ local estimates and display state cannot enter request projections (0.3346ms)
✔ structured errors keep code, field messages and context; client never swallows rejection (0.7982ms)
✔ RGB id decoding retains ids above 255 and verifies every block count (3.6477ms)
✔ hitTest is local and rejects out-of-image and fractional coordinates (0.3756ms)
✔ 3px Euclidean boundary is inclusive; drags produce no block action (0.2946ms)
✔ badges distinguish blank, uncertain, two and three kinds of marking (0.3847ms)
✔ canvas uses unscaled id loading, the existing contextmenu guard and down-time modifiers (1.8171ms)
✔ 2GiB boundary and plus one require exactly the shared extra approval (1.297ms)
✔ draft client projects only fixed confirm fields into the tenth command (1.1102ms)
✔ mock forward fetches estimate then confirms the fetched revision (0.4292ms)
✔ fetch failure and invalid summaries block approval instead of assuming zero (0.9125ms)
✔ confirmation card renders fetched byte count, loading, refusal and second dialog (9.8641ms)
✔ only HUMAN_CHECK uses the confirm card and pending-call revision stays server-owned (1.0699ms)
✔ old numeric preview call keeps the exact single-band request (1.8149ms)
✔ extended preview request projects only allowed keys and explicit full resolution (0.21ms)
✔ S05 band changes use display state, full resolution, and retain PNG onload hotfix (1.1809ms)
✔ display modes are exclusive, preserve RGB order and reject duplicates (0.5339ms)
✔ entry defaults to backend automatic selection and displays returned RGB wavelengths (0.5296ms)
✔ default LUT is identity for all 256 intensities (0.4816ms)
✔ LUT rejects nonfinite/out of range/gap under 16 and preserves last valid parameters (0.4315ms)
✔ LUT follows clamp and inverse gamma, one table for RGB, alpha unchanged and input untouched (0.3932ms)
✔ manual LUT values stay local and are independent of image request keys (0.8947ms)
✔ point coordinates retain [line,sample] and send one-pixel spectra_mean, never region (0.4492ms)
✔ point inspection returns before any edit tool and leaves null gaps visible (0.6507ms)
✔ box mean uses existing half-open endpoints, direction independent, no spectral arithmetic (0.2625ms)
✔ box inspection routes to spectra before edits and has no readiness dependency (0.418ms)
✔ storeGesture projects exactly point, box or doodle and strips nested extras (1.9944ms)
✔ gesture projection adds no absent variant fields or optional defaults (0.2692ms)
✔ gesture client uses only annotations_draft_forward and preserves server reference (0.3048ms)
✔ gesture store failure reaches caller without a fabricated reference (0.5895ms)
✔ B1/B6 parent folder supports Windows, slash and mixed paths (1.2967ms)
✔ B1 matching is exact, case insensitive and trims only (0.2666ms)
✔ B1 background number 1 is excluded; first ordered foreground match wins (0.19ms)
✔ B2 catalog returns the canonical code without constructing label fields (0.1992ms)
✔ B2 an absent folder matches after the refreshed label list includes the catalog label (0.1506ms)
✔ B3 matching leaves the input list and labels unchanged (0.2259ms)
✔ B4 folders are derived separately for each cube (0.1488ms)
✔ B5 single-file import with an arbitrary parent has no fallback label or catalog code (0.2169ms)
✔ C4: previous version total and current label-index counts render as separate summaries (29.613ms)
✔ C4: zero classes and uncertainty are omitted while zero blank pixels remain visible (0.3069ms)
✔ C4: missing overwrite summary cannot suppress the confirmation dialog (0.3337ms)
✔ C1/C2/C3/C7: auto-default uses a touched ref, resets per dataset, and follows the version count (0.2694ms)
✔ C1/C3/C6: overwrite retains the confirmation gate and cancelling only dismisses the dialog (0.2672ms)
✔ projection consumes save response, shows a selectable absolute path and fixed folder command (1.1778ms)
✔ projection failures keep save available and explicitly explain overwrite retry (0.6371ms)
✔ click binds C; Delete and Shift are not independent commands (2.0259ms)
✔ 0 is background-only; 1–9 are numeric; unbound or out-of-range labels remain mouse-only (0.7537ms)
✔ Enter / Z / D / E-B-P / arrows / Ctrl+S / space have the specified actions (0.343ms)
✔ typing never changes labels or undo; disabled settings suppress shortcuts; global chat keys pass through (0.2039ms)
✔ local remapping is deterministic and rejects duplicates/reserved keys without altering server labels (0.4588ms)
✔ each edit reads working again; write-response pixels, queue and statistics are never reconstructed (2.1573ms)
✔ switching cubes and recovering after confirm use only GET working, never diffuse (0.4668ms)
✔ a failed edit propagates its envelope and cannot manufacture a successful redraw (0.7705ms)
✔ R17 label indexes use sort_order plus SQLite BINARY code order, independent of tree grouping (0.3711ms)
✔ local remaining-time estimate derives only from confirmation speed and handles no progress (1.7188ms)
✔ catalog color proximity uses backend colors and the task-card <30 rule (1.058ms)
✔ viewport transforms preserve [line,sample], bounds, zoom anchors and half-open boxes (0.5847ms)
✔ component wiring has no local label map or undo history and preserves the outer conversation bar (1.9225ms)
✔ plan card renders table, scalar metadata, estimates, aria labels and chosen invalidation (17.821ms)
✔ all destructive choices require a reason and IPC projects only plan contract fields (36.4105ms)
✔ disabled controls cannot submit and history keeps the plan decision without action buttons (5.126ms)
✔ all agent operations invoke only agent_forward with exact projection (2.2538ms)
✔ view state, URL, key and mixed-body extras cannot enter IPC (0.2799ms)
✔ structured preflight HTTP status and errors pass through unchanged (0.6617ms)
✔ workspace context projects opaque references and cannot leak display data or geometry (0.2687ms)
✔ server-listed ordinals and names are usable without reimporting files in the current UI (2.5152ms)
✔ legacy lists retain backend order while local names remain local (0.4813ms)
✔ changing cubes clears an old gesture and same-cube followups retain it (0.2333ms)
✔ only successful annotation or preprocessing steps cause authoritative result refresh (0.3468ms)
✔ workspace SSE rejects paths, unbound geometry, unknown stage and invalid revisions (0.9654ms)
✔ request failures and SSE failures share human-readable error messages (0.3757ms)
✔ curated backend explanations survive both error delivery paths (0.3147ms)
✔ AI preview focus uses the workflow reference rather than queue order or a diffusion identifier (0.3658ms)
✔ P1 A1 App owns one session shared by Composer and S01; renderers have no reducer (2.1585ms)
✔ P1 A2 A3 composer hiding and global shortcuts leave S01 input independent (0.9706ms)
✔ P1 A4 A5 smoke stays in S01 and the three columns use current session context (0.8909ms)
✔ P1 A6 A8 retired panel files and rules are absent with only six new layout classes (1.706ms)
✔ SSE 正常流 retains order and JSON (2.4861ms)
✔ SSE 确认后挂起 retains order and JSON (0.2832ms)
✔ SSE 错误收尾 retains order and JSON (0.2779ms)
✔ SSE 空流 retains order and JSON (1.353ms)
✔ SSE accepts CRLF, multiline data, comments and final frame at EOF (0.2373ms)
✔ SSE rejects unknown events, missing event, malformed and nonobject data (0.4044ms)
✔ SSE collector retains every rejected step beyond eight (0.4014ms)
✔ approve disables both controls and records executing until response (0.1965ms)
✔ reject immediately closes confirmation card; server result remains ordered (0.2036ms)
✔ pending check accepts ordinary dialogue and sequential checks replace pending id (0.2713ms)
✔ clarify and errors release busy state and keep messages in order (0.214ms)
✔ summary renderer displays scalars and excludes unexpected objects (0.2697ms)
✔ plan SSE is accepted, accepts dialogue and cannot use the tool-decision path (0.2369ms)
✔ unrecognized approval dialogue keeps its card while terminal outcomes clear it (0.3019ms)
✔ plan actions preserve pending while executing and retain the decision with the original plan (0.3009ms)
✔ plan approval can suspend again at human check and all terminal events clear pending (0.1627ms)
✔ C delete preview opens the impact dialog; only its confirm button sends strict deletion (46.9612ms)
✔ C cancelling or unmounting a deletion confirmation never sends deletion (1.4731ms)
✔ C existing active import never asks confirmation and ignores all_datasets in the UI (0.775ms)
✔ C only REIMPORT_CONFIRMATION_REQUIRED prompts, with a selected new-id choice and no request until click (2.1493ms)
✔ C reimport cancellation and concurrent active-record conflict never silently retry or reuse (2.0235ms)
✔ C restore requires the UI button, renders refusal reason, and incomplete items cannot restore (1.0944ms)
✔ C S11 recycle summary includes retained space, count, per-item dates and incomplete cleanup refusal (6.2785ms)
✔ chat-selected registered cubes load through the existing fixed get operation (2.1586ms)
✔ catalog and recycle operations use fixed typed requests with explicit confirmation (0.6077ms)
✔ reimport confirmation is sent only from an explicit caller choice (0.5043ms)
✔ C cold catalog follows every page and retains unavailable sources as visible summaries (1.7642ms)
✔ C engine generation clears immediately and an older response cannot replace the new catalog (0.6076ms)
✔ C stale failures and disposed requests cannot overwrite a current success (0.2528ms)
✔ C current catalog failure is shown and explicit retry recovers (0.3456ms)
✔ C three existing imports append only that batch; catalog refreshes global names without expanding visible scope (0.6525ms)
✔ C broken pagination fails instead of looping or silently hiding catalog rows (2.1218ms)
✔ G3 shared displayName uses the server name and preserves the legacy fallback (1.0834ms)
✔ G2 all_datasets refreshes a previously unique name without duplicating records (1.055ms)
✔ G assistant choices and readable references use exactly the API display name (0.8789ms)
✔ only the absent-active recycled-key error promises a new dataset id (1.0974ms)
✔ active records and concurrent active conflicts never open the fresh-id confirmation (0.3138ms)
✔ existing and newly imported messages agree with actual response counts (0.2807ms)
✔ retries and existing imports keep exactly one row per persisted ID (1.7854ms)
✔ batch errors retain source path and reason for the user (0.437ms)
✔ sample value uses fixed native command and preserves annotation response (5.5452ms)
✔ CSV duplicate confirmation is an explicit second import (0.2969ms)
✔ PLS request retains explicit bound runs and only regression CV; seven result labels (0.3371ms)
✔ coefficients use one fixed read-only native operation and exact model id body (0.2225ms)
✔ extents exclude null and non-finite values without changing inputs (3.6064ms)
✔ coordinate mapping covers endpoints, inverted Y, constants and extreme finite domains (0.3365ms)
✔ nice ticks are deterministic, rounded and integer-only for counts or LVs (0.559ms)
✔ null and non-finite curve points split paths and never interpolate gaps (0.3649ms)
✔ histogram uses sqrt sample count capped at 20, shared rounded edges and grouped counts (3.0792ms)
✔ histogram bins are left-closed with rightmost edge included; rounded inner edges agree with membership (0.373ms)
✔ one histogram sample becomes a single nonzero-width bin; invalid values produce no bins (0.3134ms)
✔ four evaluation models include curve, scatter, residual and grouped histogram (2.0187ms)
✔ LV markers use saved recommendations verbatim rather than recomputing an elbow (1.7339ms)
✔ empty curve and all non-finite curves show explicit no-data status without axes (1.7256ms)
✔ curve missing values retain separated finite paths and single-point strokes (0.5551ms)
✔ one prediction is a square, maps constant axes to midlines and has one populated histogram bar (0.4484ms)
✔ constant references with varying predictions remain on X midline with an explicit note (0.4ms)
✔ null metrics never enter chart coordinates or quality calculations (0.6896ms)
✔ get_run failure produces four explicit unavailable plots, never blank axes (1.3107ms)
✔ missing LV artifact preserves the three prediction plots and their quality labels (0.4517ms)
✔ undefined predictions from classification runs are explicit, empty arrays remain no-data (0.4452ms)
✔ missing fields and unknown sets are excluded per chart, with an explicit reason when all are unusable (0.2941ms)
✔ half-quantitative label uses backend flag or label and never derives RPD (1.2183ms)
✔ loading has visible messages and a result can render while its curve is still loading (0.3582ms)
✔ error descriptions handle structured native errors and opaque values without secondary throws (0.5066ms)
✔ coefficient chart preserves signed values, zero reference, backend quality and tick targets (0.7168ms)
✔ coefficient refusal: unknown axis (0.2033ms)
✔ coefficient refusal: dimension mismatch (0.0959ms)
✔ coefficient refusal: same dimensions unsafe operator (0.0725ms)
✔ coefficient loading, missing artifact and 404 have visible messages without secondary errors (0.1635ms)
✔ coefficient empty and invalid arrays are distinct and never draw malformed nested coefficients (0.9775ms)
✔ coefficient zero line remains inside frame for 1,1,1 (0.2915ms)
✔ coefficient zero line remains inside frame for -3,-3,-3 (0.1296ms)
✔ coefficient zero line remains inside frame for 0,0,0 (0.1259ms)
✔ coefficient zero line remains inside frame for 1,2,3 (0.1546ms)
✔ coefficient zero line remains inside frame for -1,-2,-3 (0.0903ms)
✔ single coefficient is one square; nonascending wavelengths retain artifact order and disclose it (0.6397ms)
✔ six new fixed requests preserve exact bodies and strip input extras (1.2446ms)
✔ map source permits only PNG base64 and positive integer dimensions (0.2686ms)
✔ fixed palette rejects invalid RGB and preserves ordered endpoints (0.1624ms)
✔ clipping disclosure includes foreground totals and both directions (0.1089ms)
✔ stages and required scientific warning are explicit (0.1069ms)
✔ components use the client, disclose calibration, progress and independent map errors (0.6181ms)
✔ registered coefficient button is lazy per model and shows pending then success or 404 state (104.6652ms)
✔ preprocess IPC list_recipes: exact projection and sole command (4.0953ms)
✔ preprocess IPC create_recipe: exact projection and sole command (0.4571ms)
✔ preprocess IPC get_recipe: exact projection and sole command (0.2184ms)
✔ preprocess IPC add_version: exact projection and sole command (0.1752ms)
✔ preprocess IPC select_recipe: exact projection and sole command (0.1898ms)
✔ preprocess IPC deselect_recipe: exact projection and sole command (0.186ms)
✔ preprocess IPC list_project_recipes: exact projection and sole command (0.229ms)
✔ preprocess IPC create_run: exact projection and sole command (0.2215ms)
✔ preprocess IPC list_runs: exact projection and sole command (0.2323ms)
✔ preprocess IPC get_run: exact projection and sole command (0.3095ms)
✔ preprocess IPC compare: exact projection and sole command (0.2151ms)
✔ preprocess IPC get_artifact: exact projection and sole command (0.1649ms)
✔ request bodies omit runtime extras, run guard/block_size, and editor state (0.1728ms)
✔ report is parsed JSON; only sample_spectra uses binary wrapper; 204 stays null (0.1927ms)
✔ recovery inspects only new succeeded summaries and matches recipe in details (3.1547ms)
✔ transport and timeout recover, business errors do not; structured details remain visible (0.6007ms)
✔ submit TRANSPORT automatically restores new matching success; unknown outcome stays pending verification (1.0071ms)
✔ legend resolves index→id→code with backend colors, missing id prefix, unlabeled title (0.2522ms)
✔ S06 component wiring: no transport outside API, no numeric engine / fake preview; global chat unchanged (1.8605ms)
✔ unsupported operations are all marked stage two / not applicable without example metrics (0.3137ms)
✔ operator directory matches explicit R15 names and excludes run B01 / unresolved reference methods (1.828ms)
✔ axisAfter is pure, crop closed, resample replaces, decomposition removes axis (0.3645ms)
✔ crop→resample→crop supplies EACH current source, never stale saved source (0.307ms)
✔ schema-direction validation: odd SG, STRICT polynomial bound, derivative order/mode (0.3426ms)
✔ all exposed methods accept valid schema choices; unknown keys and absent components reject (1.4277ms)
✔ no wavelengths disables axis operators; lo<hi, nonempty crop, target finite/increasing enforce (0.3134ms)
✔ move/delete/repeat preserve order and compile legal explicit steps (0.1504ms)
✔ target creation is axis-only; chart gaps retain separate strokes and values (0.1832ms)
✔ settings screen starts with five empty text fields, an enabled egress switch, a password input and an unknown key status (13.28ms)
✔ rendered field changes and submit save the six-key config then key, and clear the password (6.6401ms)
✔ GET has_key renders both states without pre-filling a key, and blank key preserves existing credentials (2.0867ms)
✔ GET failure disables saving and fields while the rendered cancel button remains usable (2.5047ms)
✔ nonempty URL and numeric validation blocks invalid saves without inventing provider limits (3.4992ms)
✔ backend 400 code and detail are rendered and a failed config save never submits the key (1.6885ms)
✔ failed key write reports partial save, clears its input and redacts credentials in errors (2.9493ms)
✔ saving prevents duplicate submits and disposing ignores an in-flight GET (0.8094ms)
✔ App settings entry opens S11 with its embedded form, preserving UI-to-configuration reachability (1.2849ms)
✔ egress checkbox reflects the false value returned by GET (3.0138ms)
✔ unchecking egress saves a boolean false and keeps the returned switch state (0.745ms)
✔ C SMB and URL prefills become UNC strings, preserving independent empty and absent fields (1.6129ms)
✔ C rendered source and output inputs edit independently and save only the project defaults (11.6752ms)
✔ C browse targets only its field, cancel preserves values, and S11 summary displays saved values without editing (0.7737ms)
✔ C path form failure disables saving; disposal rejects stale GET and double save is suppressed (0.7099ms)
✔ C project path IPC uses fixed ops, strips view extras, normalizes both paths and propagates refusal (0.5289ms)
✔ settings GET and two PUT operations use only settings_forward with exact bodies (1.2662ms)
✔ settings projections exclude credentials and view or route extras from config and responses (0.2123ms)
✔ settings forward preserves the backend 400 envelope unchanged (0.419ms)
✔ egress false remains boolean through config PUT and GET projections (0.1938ms)
✔ P5 S02 uses props for four cards, recent regression runs and phase plus generation only (0.9931ms)
✔ P5 S09 regression table has only id task status and a client task filter without invented timestamps (0.7877ms)
✔ P5 S09 fetches selected run details and retains backend metrics quality and collapsed leak report (0.2151ms)
✔ P5 S09 preprocess reads only the selected dataset and preserves real time fields and empty states (0.2165ms)
✔ P5 S10 has a data-screen action and S11 embeds the settings form without fake controls (0.2269ms)
✔ P5 inserts four screen cases while preserving source anchors S03 debug text and theme boundary (0.4167ms)
✔ P2 navigation preserves App runId until the results back-to-list action (0.8173ms)
✔ P2 S04 and S03 thumbnails share BandCanvas and viewing updates workspace (0.3248ms)
✔ P2 S08 loads real regression runs and refetches run plus sweep on mount (0.1931ms)
✔ P2 S07 keeps training and internal views while results and source anchors stay intact (0.466ms)
✔ A1 navigation retains five ordered groups and exactly ten unique screen entries (1.971ms)
✔ A1 titles cover all eleven Screen values including the viewer below data (0.2458ms)
✔ A1 only s04 redirects its navigation highlight to s03 (0.2716ms)
✔ skin guards: annotation-skin.css (1.7518ms)
✔ skin guards: preprocess-skin.css (0.3033ms)
✔ skin guards: modeling-skin.css (0.2798ms)
ℹ tests 241
ℹ suites 0
ℹ pass 241
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 771.8341
```

### before-Python-collected.txt

完整文件：[before-Python-collected.txt](E:/AI_Agent/milestone25/evidence/D/before-Python-collected.txt)

```text
1561 tests collected in 2.86s
```

### before-Python-backend.txt

完整文件：[before-Python-backend.txt](E:/AI_Agent/milestone25/evidence/D/before-Python-backend.txt)

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
45 passed, 10 warnings in 5.78s
```

### before-Python-src.txt

完整文件：[before-Python-src.txt](E:/AI_Agent/milestone25/evidence/D/before-Python-src.txt)

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
1514 passed, 2 skipped, 6 warnings in 599.52s (0:09:59)
```

### before-Rust.txt

完整文件：[before-Rust.txt](E:/AI_Agent/milestone25/evidence/D/before-Rust.txt)

```text
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.45s
     Running unittests src\lib.rs (target\debug\deps\spectrum_agent-fc5a2225eca9e0bc.exe)

running 54 tests
test annotation::tests::parameter_edges_and_unicode_note_match_http_contract ... ok
test annotation::tests::four_management_operations_have_literal_paths_methods_and_bodies ... ok
test annotation::tests::project_query_is_strict_then_lowercase_but_dataset_path_is_unchanged ... ok
test annotation::tests::omitted_parameters_stay_omitted_and_all_prompt_geometries_are_typed ... ok
test annotation::tests::bad_types_lengths_and_out_of_range_parameters_are_rejected ... ok
test annotation::tests::only_the_supplied_nonzero_handshake_port_is_used ... ok
test annotation::tests::identifiers_cannot_escape_and_version_numbers_are_not_uuids ... ok
test annotation::tests::all_nine_operations_have_exact_paths_methods_and_bodies ... ok
test datasets_dev::tests::catalog_contract ... ok
test datasets_dev::tests::all_operations_use_the_handshake_port_and_fixed_namespace ... ok
test annotation::tests::no_free_url_host_port_path_or_method_can_enter_any_operation ... ok
test annotation::tests::unknown_operations_and_fields_are_structured_and_never_reflect_input ... ok
test datasets_dev::tests::delete_contract ... ok
test datasets_dev::tests::delete_preview_contract ... ok
test datasets_dev::tests::import_confirmation_defaults_false ... ok
test datasets_dev::tests::preview_legacy_url_is_unchanged_and_optional_fields_allow_rgb_without_band ... ok
test datasets_dev::tests::no_generic_host_port_path_or_method_can_be_deserialized ... ok
test datasets_dev::tests::recycle_list_contract ... ok
test models::tests::fixed_operations_and_methods ... ok
test health::route_tests::closed_routes_always_use_numeric_loopback_and_literal_paths ... ok
test datasets_dev::tests::restore_contract ... ok
test datasets_dev::tests::spectra_mean_has_fixed_post_path_typed_region_and_uuid_guard ... ok
test models::tests::new_ops_reject_proxy_fields_invalid_stages_and_all_id_traversal ... ok
test models::tests::registry_inference_six_fixed_operations ... ok
test preprocess::tests::actual_generation_guard_used_by_command_rejects_stale_or_nonready ... ok
test preprocess::tests::all_twelve_destinations_methods_and_exact_bodies ... ok
test preprocess::tests::four_uuid_error_codes_cover_every_identifier_field ... ok
test preprocess::tests::manual_base64_matches_rfc4648_vectors ... ok
test preprocess::tests::builder_sets_three_hundred_seconds_without_waiting ... ok
test annotation::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test datasets_dev::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test preprocess::tests::json_success_is_unchanged_and_post_body_is_forwarded ... ok
test preprocess::tests::malformed_http_envelope_uses_generic_error ... ok
test annotation::tests::label_body_limit_counts_serialized_utf8_and_business_validation_stays_in_python ... ok
test preprocess::tests::unknown_fields_ops_types_artifact_values_and_free_destinations_are_rejected ... ok
test preprocess::tests::uuid_copy_and_port_boundary_preserve_closed_destination ... ok
test preprocess::tests::redirects_are_not_followed ... ok
test preprocess::tests::binary_payload_and_wrapper_filename_are_also_sensitive_checked ... ok
test annotation::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test datasets_dev::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test preprocess::tests::structured_http_error_preserves_three_fields ... ok
test preprocess::tests::raw_and_canonical_tokens_never_cross_bridge ... ok
test preprocess::tests::only_204_maps_empty_body_to_null_not_200 ... ok
test preprocess::tests::identity_checks_precede_http_status_and_body ... ok
test preprocess::tests::report_stays_json_and_nonartifact_binary_is_rejected ... ok
test datasets_dev::tests::response_identity_precedes_status_and_body ... ok
test annotation::tests::response_identity_precedes_status_and_body ... ok
test models::tests::six_new_ops_reach_loopback_with_native_auth_and_exact_bodies ... ok
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
test boot::tests::healthy_document_always_waits_across_generations ... ok
test boot_monitor_tests::engine_retry_keeps_healthy_document_until_real_navigation ... ok
test boot::tests::reload_boundary_4999_5000_and_5001_ms ... ok
test exports_tests::export_folder_is_scoped_to_a_canonical_cube_uuid ... ok
test exports_tests::export_folder_rejects_paths_and_malformed_ids ... ok
test boot_monitor_tests::reload_budget_is_independent_and_activations_do_not_reset_it ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\agent_settings_forward.rs (target\debug\deps\agent_settings_forward-33848812934a45f0.exe)

running 12 tests
test both_commands_reject_stale_generation_or_non_ready_phase ... ok
test agent_three_operations_and_two_body_shapes_have_literal_routes ... ok
test whitelist_rejects_paths_methods_and_mixed_message_shapes ... ok
test project_paths_fixed_contract_empty_values_and_unknown_fields ... ok
test settings_only_existing_get_put_operations_and_no_key_in_config ... ok
test workspace_events_keep_only_bound_scalar_references ... ok
test http_errors_keep_status_and_envelope_redirects_not_followed ... ok
test settings_key_and_escaped_credentials_never_cross_error_or_success_envelopes ... ok
test sse_empty_done_suspended_human_check_and_error_close ... ok
test identity_is_checked_before_status_length_and_body_for_both_commands ... ok
test project_paths_visible_in_success_but_rejected_in_error_envelopes_and_identity_checked_first ... ok
test declared_and_streaming_limits_are_enforced_for_both_commands ... ok

test result: ok. 12 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.55s

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

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.82s

     Running tests\causality.rs (target\debug\deps\causality-36e4b6d833a263b9.exe)

running 2 tests
test midnight_files_and_preexisting_partial_line_are_handled_without_fallback ... ok
test only_new_complete_lines_with_own_integer_pid_in_utc_window_can_be_cause ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.04s

     Running tests\contracts.rs (target\debug\deps\contracts-6e34dbf97624c6bb.exe)

running 6 tests
test late_generation_and_expected_exit_cannot_fail_current_attempt ... ok
test all_transition_pairs_and_stopping_terminal_rule ... ok
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

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 5.92s

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

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.17s

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

### before-clippy.txt

完整文件：[before-clippy.txt](E:/AI_Agent/milestone25/evidence/D/before-clippy.txt)

```text
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.38s
```

### before-build.txt

完整文件：[before-build.txt](E:/AI_Agent/milestone25/evidence/D/before-build.txt)

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

✓ built in 144ms
```

### after-node.txt

完整文件：[after-node.txt](E:/AI_Agent/milestone25/evidence/D/after-node.txt)

```text
✔ block clicks retain the legacy geometry and omit label_id for erase and uncertain (2.7979ms)
✔ IPC superpixels: exact Rust variant, one command, no arbitrary route (0.3891ms)
✔ IPC diffuse: exact Rust variant, one command, no arbitrary route (0.2721ms)
✔ IPC regions: exact Rust variant, one command, no arbitrary route (0.2451ms)
✔ IPC undo: exact Rust variant, one command, no arbitrary route (0.9499ms)
✔ IPC working: exact Rust variant, one command, no arbitrary route (0.2418ms)
✔ IPC validate: exact Rust variant, one command, no arbitrary route (0.2772ms)
✔ IPC save: exact Rust variant, one command, no arbitrary route (0.3ms)
✔ IPC versions: exact Rust variant, one command, no arbitrary route (0.2646ms)
✔ IPC version_overlay: exact Rust variant, one command, no arbitrary route (0.4016ms)
✔ IPC projects: exact Rust variant, one command, no arbitrary route (0.2688ms)
✔ IPC labels: exact Rust variant, one command, no arbitrary route (0.1428ms)
✔ IPC add_label: exact Rust variant, one command, no arbitrary route (0.1772ms)
✔ IPC catalog: exact Rust variant, one command, no arbitrary route (0.1622ms)
✔ optional defaults are left to Python; all prompt and geometry forms retain [line,sample] (0.3738ms)
✔ all three structured label bodies match Python and carry the working project id (0.2261ms)
✔ local estimates and display state cannot enter request projections (0.398ms)
✔ structured errors keep code, field messages and context; client never swallows rejection (0.8244ms)
✔ RGB id decoding retains ids above 255 and verifies every block count (3.3704ms)
✔ hitTest is local and rejects out-of-image and fractional coordinates (0.3421ms)
✔ 3px Euclidean boundary is inclusive; drags produce no block action (0.2517ms)
✔ badges distinguish blank, uncertain, two and three kinds of marking (0.3629ms)
✔ canvas uses unscaled id loading, the existing contextmenu guard and down-time modifiers (0.7681ms)
✔ 2GiB boundary and plus one require exactly the shared extra approval (1.085ms)
✔ draft client projects only fixed confirm fields into the tenth command (1.2177ms)
✔ mock forward fetches estimate then confirms the fetched revision (0.4768ms)
✔ fetch failure and invalid summaries block approval instead of assuming zero (0.9313ms)
✔ confirmation card renders fetched byte count, loading, refusal and second dialog (11.3289ms)
✔ only HUMAN_CHECK uses the confirm card and pending-call revision stays server-owned (1.1096ms)
✔ old numeric preview call keeps the exact single-band request (4.204ms)
✔ extended preview request projects only allowed keys and explicit full resolution (0.2808ms)
✔ S05 band changes use display state, full resolution, and retain PNG onload hotfix (1.313ms)
✔ display modes are exclusive, preserve RGB order and reject duplicates (0.6036ms)
✔ entry defaults to backend automatic selection and displays returned RGB wavelengths (0.6367ms)
✔ default LUT is identity for all 256 intensities (0.5712ms)
✔ LUT rejects nonfinite/out of range/gap under 16 and preserves last valid parameters (0.5221ms)
✔ LUT follows clamp and inverse gamma, one table for RGB, alpha unchanged and input untouched (0.6131ms)
✔ manual LUT values stay local and are independent of image request keys (0.9785ms)
✔ point coordinates retain [line,sample] and send one-pixel spectra_mean, never region (0.5557ms)
✔ point inspection returns before any edit tool and leaves null gaps visible (0.841ms)
✔ box mean uses existing half-open endpoints, direction independent, no spectral arithmetic (0.2574ms)
✔ box inspection routes to spectra before edits and has no readiness dependency (0.3707ms)
✔ storeGesture projects exactly point, box or doodle and strips nested extras (2.3547ms)
✔ gesture projection adds no absent variant fields or optional defaults (0.3312ms)
✔ gesture client uses only annotations_draft_forward and preserves server reference (0.392ms)
✔ gesture store failure reaches caller without a fabricated reference (0.6792ms)
✔ B1/B6 parent folder supports Windows, slash and mixed paths (1.4014ms)
✔ B1 matching is exact, case insensitive and trims only (0.5871ms)
✔ B1 background number 1 is excluded; first ordered foreground match wins (0.2659ms)
✔ B2 catalog returns the canonical code without constructing label fields (0.2294ms)
✔ B2 an absent folder matches after the refreshed label list includes the catalog label (0.2394ms)
✔ B3 matching leaves the input list and labels unchanged (0.3175ms)
✔ B4 folders are derived separately for each cube (0.1669ms)
✔ B5 single-file import with an arbitrary parent has no fallback label or catalog code (0.2196ms)
✔ C4: previous version total and current label-index counts render as separate summaries (30.7814ms)
✔ C4: zero classes and uncertainty are omitted while zero blank pixels remain visible (0.3831ms)
✔ C4: missing overwrite summary cannot suppress the confirmation dialog (0.439ms)
✔ C1/C2/C3/C7: auto-default uses a touched ref, resets per dataset, and follows the version count (0.3526ms)
✔ C1/C3/C6: overwrite retains the confirmation gate and cancelling only dismisses the dialog (0.2399ms)
✔ projection consumes save response, shows a selectable absolute path and fixed folder command (1.1941ms)
✔ projection failures keep save available and explicitly explain overwrite retry (0.4855ms)
✔ click binds C; Delete and Shift are not independent commands (1.9416ms)
✔ 0 is background-only; 1–9 are numeric; unbound or out-of-range labels remain mouse-only (0.8037ms)
✔ Enter / Z / D / E-B-P / arrows / Ctrl+S / space have the specified actions (0.3807ms)
✔ typing never changes labels or undo; disabled settings suppress shortcuts; global chat keys pass through (0.2223ms)
✔ local remapping is deterministic and rejects duplicates/reserved keys without altering server labels (0.4829ms)
✔ each edit reads working again; write-response pixels, queue and statistics are never reconstructed (6.2774ms)
✔ switching cubes and recovering after confirm use only GET working, never diffuse (0.8828ms)
✔ a failed edit propagates its envelope and cannot manufacture a successful redraw (0.8996ms)
✔ R17 label indexes use sort_order plus SQLite BINARY code order, independent of tree grouping (0.49ms)
✔ local remaining-time estimate derives only from confirmation speed and handles no progress (0.2155ms)
✔ catalog color proximity uses backend colors and the task-card <30 rule (0.2723ms)
✔ viewport transforms preserve [line,sample], bounds, zoom anchors and half-open boxes (0.6603ms)
✔ component wiring has no local label map or undo history and preserves the outer conversation bar (2.3181ms)
✔ plan card renders table, scalar metadata, estimates, aria labels and chosen invalidation (15.9711ms)
✔ all destructive choices require a reason and IPC projects only plan contract fields (39.3916ms)
✔ disabled controls cannot submit and history keeps the plan decision without action buttons (5.8138ms)
✔ all agent operations invoke only agent_forward with exact projection (2.0242ms)
✔ view state, URL, key and mixed-body extras cannot enter IPC (0.2602ms)
✔ structured preflight HTTP status and errors pass through unchanged (0.5863ms)
✔ workspace context projects opaque references and cannot leak display data or geometry (0.2433ms)
✔ server-listed ordinals and names are usable without reimporting files in the current UI (3.4021ms)
✔ legacy lists retain backend order while local names remain local (0.5126ms)
✔ changing cubes clears an old gesture and same-cube followups retain it (0.2869ms)
✔ only successful annotation or preprocessing steps cause authoritative result refresh (0.3595ms)
✔ workspace SSE rejects paths, unbound geometry, unknown stage and invalid revisions (0.9196ms)
✔ request failures and SSE failures share human-readable error messages (0.4386ms)
✔ curated backend explanations survive both error delivery paths (0.3318ms)
✔ AI preview focus uses the workflow reference rather than queue order or a diffusion identifier (0.3884ms)
✔ P1 A1 App owns one session shared by Composer and S01; renderers have no reducer (2.5961ms)
✔ P1 A2 A3 composer hiding and global shortcuts leave S01 input independent (0.8966ms)
✔ P1 A4 A5 smoke stays in S01 and the three columns use current session context (0.7752ms)
✔ P1 A6 A8 retired panel files and rules are absent with only six new layout classes (1.5607ms)
✔ SSE 正常流 retains order and JSON (2.5628ms)
✔ SSE 确认后挂起 retains order and JSON (0.3162ms)
✔ SSE 错误收尾 retains order and JSON (0.5623ms)
✔ SSE 空流 retains order and JSON (0.1691ms)
✔ SSE accepts CRLF, multiline data, comments and final frame at EOF (2.4541ms)
✔ SSE rejects unknown events, missing event, malformed and nonobject data (0.4245ms)
✔ SSE collector retains every rejected step beyond eight (0.451ms)
✔ approve disables both controls and records executing until response (0.2272ms)
✔ reject immediately closes confirmation card; server result remains ordered (0.2528ms)
✔ pending check accepts ordinary dialogue and sequential checks replace pending id (0.3279ms)
✔ clarify and errors release busy state and keep messages in order (0.27ms)
✔ summary renderer displays scalars and excludes unexpected objects (0.2443ms)
✔ plan SSE is accepted, accepts dialogue and cannot use the tool-decision path (0.2292ms)
✔ unrecognized approval dialogue keeps its card while terminal outcomes clear it (0.3283ms)
✔ plan actions preserve pending while executing and retain the decision with the original plan (0.3417ms)
✔ plan approval can suspend again at human check and all terminal events clear pending (0.2821ms)
✔ C delete preview opens the impact dialog; only its confirm button sends strict deletion (37.2965ms)
✔ C cancelling or unmounting a deletion confirmation never sends deletion (1.9627ms)
✔ C existing active import never asks confirmation and ignores all_datasets in the UI (0.8666ms)
✔ C only REIMPORT_CONFIRMATION_REQUIRED prompts, with a selected new-id choice and no request until click (2.1191ms)
✔ C reimport cancellation and concurrent active-record conflict never silently retry or reuse (1.8947ms)
✔ C restore requires the UI button, renders refusal reason, and incomplete items cannot restore (1.1881ms)
✔ C S11 recycle summary includes retained space, count, per-item dates and incomplete cleanup refusal (6.6924ms)
✔ chat-selected registered cubes load through the existing fixed get operation (2.6797ms)
✔ catalog and recycle operations use fixed typed requests with explicit confirmation (0.4448ms)
✔ reimport confirmation is sent only from an explicit caller choice (0.4601ms)
✔ C cold catalog follows every page and retains unavailable sources as visible summaries (2.025ms)
✔ C engine generation clears immediately and an older response cannot replace the new catalog (0.5818ms)
✔ C stale failures and disposed requests cannot overwrite a current success (5.1151ms)
✔ C current catalog failure is shown and explicit retry recovers (0.567ms)
✔ C three existing imports append only that batch; catalog refreshes global names without expanding visible scope (3.325ms)
✔ C broken pagination fails instead of looping or silently hiding catalog rows (1.9156ms)
✔ G3 shared displayName uses the server name and preserves the legacy fallback (1.2299ms)
✔ G2 all_datasets refreshes a previously unique name without duplicating records (1.3283ms)
✔ G assistant choices and readable references use exactly the API display name (1.1831ms)
✔ only the absent-active recycled-key error promises a new dataset id (6.9955ms)
✔ active records and concurrent active conflicts never open the fresh-id confirmation (0.5346ms)
✔ existing and newly imported messages agree with actual response counts (0.3415ms)
✔ retries and existing imports keep exactly one row per persisted ID (3.0224ms)
✔ batch errors retain source path and reason for the user (0.5236ms)
✔ sample value uses fixed native command and preserves annotation response (3.1602ms)
✔ CSV duplicate confirmation is an explicit second import (0.3589ms)
✔ PLS request retains explicit bound runs and only regression CV; seven result labels (0.3847ms)
✔ coefficients use one fixed read-only native operation and exact model id body (0.3052ms)
✔ extents exclude null and non-finite values without changing inputs (3.027ms)
✔ coordinate mapping covers endpoints, inverted Y, constants and extreme finite domains (0.4031ms)
✔ nice ticks are deterministic, rounded and integer-only for counts or LVs (0.3906ms)
✔ null and non-finite curve points split paths and never interpolate gaps (0.2691ms)
✔ histogram uses sqrt sample count capped at 20, shared rounded edges and grouped counts (1.0874ms)
✔ histogram bins are left-closed with rightmost edge included; rounded inner edges agree with membership (0.245ms)
✔ one histogram sample becomes a single nonzero-width bin; invalid values produce no bins (0.2588ms)
✔ four evaluation models include curve, scatter, residual and grouped histogram (3.1798ms)
✔ LV markers use saved recommendations verbatim rather than recomputing an elbow (1.2385ms)
✔ empty curve and all non-finite curves show explicit no-data status without axes (0.9425ms)
✔ curve missing values retain separated finite paths and single-point strokes (0.5552ms)
✔ one prediction is a square, maps constant axes to midlines and has one populated histogram bar (0.429ms)
✔ constant references with varying predictions remain on X midline with an explicit note (0.4217ms)
✔ null metrics never enter chart coordinates or quality calculations (0.598ms)
✔ get_run failure produces four explicit unavailable plots, never blank axes (0.4244ms)
✔ missing LV artifact preserves the three prediction plots and their quality labels (0.3441ms)
✔ undefined predictions from classification runs are explicit, empty arrays remain no-data (0.3389ms)
✔ missing fields and unknown sets are excluded per chart, with an explicit reason when all are unusable (0.2371ms)
✔ half-quantitative label uses backend flag or label and never derives RPD (2.1354ms)
✔ loading has visible messages and a result can render while its curve is still loading (0.3108ms)
✔ error descriptions handle structured native errors and opaque values without secondary throws (0.2197ms)
✔ coefficient chart preserves signed values, zero reference, backend quality and tick targets (1.439ms)
✔ coefficient refusal: unknown axis (0.2431ms)
✔ coefficient refusal: dimension mismatch (0.2099ms)
✔ coefficient refusal: same dimensions unsafe operator (0.1135ms)
✔ coefficient loading, missing artifact and 404 have visible messages without secondary errors (0.225ms)
✔ coefficient empty and invalid arrays are distinct and never draw malformed nested coefficients (0.2718ms)
✔ coefficient zero line remains inside frame for 1,1,1 (0.3183ms)
✔ coefficient zero line remains inside frame for -3,-3,-3 (0.1769ms)
✔ coefficient zero line remains inside frame for 0,0,0 (0.1608ms)
✔ coefficient zero line remains inside frame for 1,2,3 (0.1727ms)
✔ coefficient zero line remains inside frame for -1,-2,-3 (0.1189ms)
✔ single coefficient is one square; nonascending wavelengths retain artifact order and disclose it (0.3495ms)
✔ six new fixed requests preserve exact bodies and strip input extras (1.4102ms)
✔ map source permits only PNG base64 and positive integer dimensions (0.2766ms)
✔ fixed palette rejects invalid RGB and preserves ordered endpoints (0.1636ms)
✔ clipping disclosure includes foreground totals and both directions (0.1176ms)
✔ stages and required scientific warning are explicit (0.1099ms)
✔ components use the client, disclose calibration, progress and independent map errors (0.6361ms)
✔ registered coefficient button is lazy per model and shows pending then success or 404 state (135.384ms)
✔ preprocess IPC list_recipes: exact projection and sole command (2.3711ms)
✔ preprocess IPC create_recipe: exact projection and sole command (0.4863ms)
✔ preprocess IPC get_recipe: exact projection and sole command (1.2787ms)
✔ preprocess IPC add_version: exact projection and sole command (0.2208ms)
✔ preprocess IPC select_recipe: exact projection and sole command (0.1953ms)
✔ preprocess IPC deselect_recipe: exact projection and sole command (0.142ms)
✔ preprocess IPC list_project_recipes: exact projection and sole command (0.188ms)
✔ preprocess IPC create_run: exact projection and sole command (0.2141ms)
✔ preprocess IPC list_runs: exact projection and sole command (0.1934ms)
✔ preprocess IPC get_run: exact projection and sole command (0.2359ms)
✔ preprocess IPC compare: exact projection and sole command (0.206ms)
✔ preprocess IPC get_artifact: exact projection and sole command (0.1914ms)
✔ request bodies omit runtime extras, run guard/block_size, and editor state (0.1796ms)
✔ report is parsed JSON; only sample_spectra uses binary wrapper; 204 stays null (0.193ms)
✔ recovery inspects only new succeeded summaries and matches recipe in details (2.0705ms)
✔ transport and timeout recover, business errors do not; structured details remain visible (2.4934ms)
✔ submit TRANSPORT automatically restores new matching success; unknown outcome stays pending verification (1.0759ms)
✔ legend resolves index→id→code with backend colors, missing id prefix, unlabeled title (0.3013ms)
✔ S06 component wiring: no transport outside API, no numeric engine / fake preview; global chat unchanged (1.9026ms)
✔ unsupported operations are all marked stage two / not applicable without example metrics (0.3017ms)
✔ operator directory matches explicit R15 names and excludes run B01 / unresolved reference methods (5.2343ms)
✔ axisAfter is pure, crop closed, resample replaces, decomposition removes axis (1.0218ms)
✔ crop→resample→crop supplies EACH current source, never stale saved source (0.6188ms)
✔ schema-direction validation: odd SG, STRICT polynomial bound, derivative order/mode (0.579ms)
✔ all exposed methods accept valid schema choices; unknown keys and absent components reject (2.9971ms)
✔ no wavelengths disables axis operators; lo<hi, nonempty crop, target finite/increasing enforce (0.8519ms)
✔ move/delete/repeat preserve order and compile legal explicit steps (0.3012ms)
✔ target creation is axis-only; chart gaps retain separate strokes and values (0.3709ms)
✔ settings screen starts with five empty text fields, an enabled egress switch, a password input and an unknown key status (20.4299ms)
✔ rendered field changes and submit save the six-key config then key, and clear the password (8.6867ms)
✔ GET has_key renders both states without pre-filling a key, and blank key preserves existing credentials (4.6548ms)
✔ GET failure disables saving and fields while the rendered cancel button remains usable (5.1641ms)
✔ nonempty URL and numeric validation blocks invalid saves without inventing provider limits (8.1066ms)
✔ backend 400 code and detail are rendered and a failed config save never submits the key (2.6942ms)
✔ failed key write reports partial save, clears its input and redacts credentials in errors (4.0037ms)
✔ saving prevents duplicate submits and disposing ignores an in-flight GET (1.3557ms)
✔ App settings entry opens S11 with its embedded form, preserving UI-to-configuration reachability (0.8463ms)
✔ egress checkbox reflects the false value returned by GET (1.8091ms)
✔ unchecking egress saves a boolean false and keeps the returned switch state (1.1915ms)
✔ C SMB and URL prefills become UNC strings, preserving independent empty and absent fields (3.1399ms)
✔ C rendered source and output inputs edit independently and save only the project defaults (21.763ms)
✔ C browse targets only its field, cancel preserves values, and S11 summary displays saved values without editing (1.2978ms)
✔ C path form failure disables saving; disposal rejects stale GET and double save is suppressed (1.3684ms)
✔ C project path IPC uses fixed ops, strips view extras, normalizes both paths and propagates refusal (0.8668ms)
✔ settings GET and two PUT operations use only settings_forward with exact bodies (2.1141ms)
✔ settings projections exclude credentials and view or route extras from config and responses (0.239ms)
✔ settings forward preserves the backend 400 envelope unchanged (0.457ms)
✔ egress false remains boolean through config PUT and GET projections (0.2077ms)
✔ P5 S02 uses props for four cards, recent regression runs and phase plus generation only (1.3391ms)
✔ P5 S09 regression table has only id task status and a client task filter without invented timestamps (0.9235ms)
✔ P5 S09 fetches selected run details and retains backend metrics quality and collapsed leak report (0.2866ms)
✔ P5 S09 preprocess reads only the selected dataset and preserves real time fields and empty states (0.3348ms)
✔ P5 S10 has a data-screen action and S11 embeds the settings form without fake controls (0.2493ms)
✔ P5 inserts four screen cases while preserving source anchors S03 debug text and theme boundary (0.4323ms)
✔ P2 navigation preserves App runId until the results back-to-list action (1.4328ms)
✔ P2 S04 and S03 thumbnails share BandCanvas and viewing updates workspace (0.5522ms)
✔ P2 S08 loads real regression runs and refetches run plus sweep on mount (0.4448ms)
✔ P2 S07 keeps training and internal views while results and source anchors stay intact (0.8691ms)
✔ A1 navigation retains five ordered groups and exactly ten unique screen entries (2.0214ms)
✔ A1 titles cover all eleven Screen values including the viewer below data (0.2608ms)
✔ A1 only s04 redirects its navigation highlight to s03 (0.2119ms)
✔ skin guards: annotation-skin.css (2.6888ms)
✔ skin guards: preprocess-skin.css (0.4644ms)
✔ skin guards: modeling-skin.css (0.5102ms)
ℹ tests 241
ℹ suites 0
ℹ pass 241
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 884.8005
```

### after-Python-collected.txt

完整文件：[after-Python-collected.txt](E:/AI_Agent/milestone25/evidence/D/after-Python-collected.txt)

```text
1568 tests collected in 2.26s
```

### after-Python-backend.txt

完整文件：[after-Python-backend.txt](E:/AI_Agent/milestone25/evidence/D/after-Python-backend.txt)

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
45 passed, 10 warnings in 6.16s
```

### after-Python-src.txt

完整文件：[after-Python-src.txt](E:/AI_Agent/milestone25/evidence/D/after-Python-src.txt)

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
........................................................................ [ 70%]
........................................................................ [ 75%]
........................................................................ [ 80%]
........................................................................ [ 85%]
........................................................................ [ 89%]
........................................................................ [ 94%]
........................................................................ [ 99%]
...........                                                              [100%]
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
1521 passed, 2 skipped, 6 warnings in 614.51s (0:10:14)
```

### after-Rust.txt

完整文件：[after-Rust.txt](E:/AI_Agent/milestone25/evidence/D/after-Rust.txt)

```text
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.73s
     Running unittests src\lib.rs (target\debug\deps\spectrum_agent-fc5a2225eca9e0bc.exe)

running 54 tests
test annotation::tests::identifiers_cannot_escape_and_version_numbers_are_not_uuids ... ok
test annotation::tests::four_management_operations_have_literal_paths_methods_and_bodies ... ok
test annotation::tests::only_the_supplied_nonzero_handshake_port_is_used ... ok
test annotation::tests::parameter_edges_and_unicode_note_match_http_contract ... ok
test annotation::tests::project_query_is_strict_then_lowercase_but_dataset_path_is_unchanged ... ok
test annotation::tests::bad_types_lengths_and_out_of_range_parameters_are_rejected ... ok
test annotation::tests::omitted_parameters_stay_omitted_and_all_prompt_geometries_are_typed ... ok
test annotation::tests::all_nine_operations_have_exact_paths_methods_and_bodies ... ok
test datasets_dev::tests::catalog_contract ... ok
test datasets_dev::tests::all_operations_use_the_handshake_port_and_fixed_namespace ... ok
test datasets_dev::tests::delete_contract ... ok
test annotation::tests::no_free_url_host_port_path_or_method_can_enter_any_operation ... ok
test annotation::tests::unknown_operations_and_fields_are_structured_and_never_reflect_input ... ok
test datasets_dev::tests::delete_preview_contract ... ok
test datasets_dev::tests::import_confirmation_defaults_false ... ok
test datasets_dev::tests::no_generic_host_port_path_or_method_can_be_deserialized ... ok
test datasets_dev::tests::preview_legacy_url_is_unchanged_and_optional_fields_allow_rgb_without_band ... ok
test datasets_dev::tests::recycle_list_contract ... ok
test datasets_dev::tests::restore_contract ... ok
test health::route_tests::closed_routes_always_use_numeric_loopback_and_literal_paths ... ok
test models::tests::new_ops_reject_proxy_fields_invalid_stages_and_all_id_traversal ... ok
test models::tests::registry_inference_six_fixed_operations ... ok
test preprocess::tests::actual_generation_guard_used_by_command_rejects_stale_or_nonready ... ok
test datasets_dev::tests::spectra_mean_has_fixed_post_path_typed_region_and_uuid_guard ... ok
test models::tests::fixed_operations_and_methods ... ok
test preprocess::tests::four_uuid_error_codes_cover_every_identifier_field ... ok
test preprocess::tests::all_twelve_destinations_methods_and_exact_bodies ... ok
test preprocess::tests::builder_sets_three_hundred_seconds_without_waiting ... ok
test preprocess::tests::manual_base64_matches_rfc4648_vectors ... ok
test annotation::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test datasets_dev::tests::structured_sidecar_errors_are_preserved_after_identity_validation ... ok
test preprocess::tests::json_success_is_unchanged_and_post_body_is_forwarded ... ok
test preprocess::tests::malformed_http_envelope_uses_generic_error ... ok
test preprocess::tests::unknown_fields_ops_types_artifact_values_and_free_destinations_are_rejected ... ok
test preprocess::tests::uuid_copy_and_port_boundary_preserve_closed_destination ... ok
test preprocess::tests::binary_payload_and_wrapper_filename_are_also_sensitive_checked ... ok
test annotation::tests::label_body_limit_counts_serialized_utf8_and_business_validation_stays_in_python ... ok
test preprocess::tests::redirects_are_not_followed ... ok
test preprocess::tests::structured_http_error_preserves_three_fields ... ok
test preprocess::tests::only_204_maps_empty_body_to_null_not_200 ... ok
test datasets_dev::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test annotation::tests::redirects_are_not_followed_and_sensitive_bodies_never_leave_rust ... ok
test preprocess::tests::raw_and_canonical_tokens_never_cross_bridge ... ok
test preprocess::tests::report_stays_json_and_nonartifact_binary_is_rejected ... ok
test annotation::tests::response_identity_precedes_status_and_body ... ok
test datasets_dev::tests::response_identity_precedes_status_and_body ... ok
test models::tests::six_new_ops_reach_loopback_with_native_auth_and_exact_bodies ... ok
test preprocess::tests::identity_checks_precede_http_status_and_body ... ok
test preprocess::tests::binary_artifact_roundtrips_and_keeps_filename ... ok
test annotation::tests::declared_and_streaming_response_limits_are_enforced ... ok
test datasets_dev::tests::declared_and_streaming_response_limits_are_enforced ... ok
test preprocess::tests::declared_and_streaming_limits_reject_above_eight_mib ... ok
test models::tests::rejects_general_proxy_extra_fields_traversal_and_oversize ... ok
test annotation::tests::an_exactly_eight_mib_json_response_is_allowed ... ok

test result: ok. 54 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.22s

     Running unittests src\main.rs (target\debug\deps\spectrum_agent-9760c85afe553455.exe)

running 8 tests
test boot::tests::final_timeout_is_fifteen_seconds_from_window_shown ... ok
test boot::tests::healthy_document_always_waits_across_generations ... ok
test exports_tests::export_folder_is_scoped_to_a_canonical_cube_uuid ... ok
test boot::tests::before_timeout_wait_and_first_attempt_precedes_give_up ... ok
test exports_tests::export_folder_rejects_paths_and_malformed_ids ... ok
test boot_monitor_tests::reload_budget_is_independent_and_activations_do_not_reset_it ... ok
test boot_monitor_tests::engine_retry_keeps_healthy_document_until_real_navigation ... ok
test boot::tests::reload_boundary_4999_5000_and_5001_ms ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\agent_settings_forward.rs (target\debug\deps\agent_settings_forward-33848812934a45f0.exe)

running 12 tests
test both_commands_reject_stale_generation_or_non_ready_phase ... ok
test project_paths_fixed_contract_empty_values_and_unknown_fields ... ok
test agent_three_operations_and_two_body_shapes_have_literal_routes ... ok
test workspace_events_keep_only_bound_scalar_references ... ok
test whitelist_rejects_paths_methods_and_mixed_message_shapes ... ok
test settings_only_existing_get_put_operations_and_no_key_in_config ... ok
test http_errors_keep_status_and_envelope_redirects_not_followed ... ok
test sse_empty_done_suspended_human_check_and_error_close ... ok
test settings_key_and_escaped_credentials_never_cross_error_or_success_envelopes ... ok
test identity_is_checked_before_status_length_and_body_for_both_commands ... ok
test project_paths_visible_in_success_but_rejected_in_error_envelopes_and_identity_checked_first ... ok
test declared_and_streaming_limits_are_enforced_for_both_commands ... ok

test result: ok. 12 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.57s

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

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.84s

     Running tests\causality.rs (target\debug\deps\causality-36e4b6d833a263b9.exe)

running 2 tests
test midnight_files_and_preexisting_partial_line_are_handled_without_fallback ... ok
test only_new_complete_lines_with_own_integer_pid_in_utc_window_can_be_cause ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.04s

     Running tests\contracts.rs (target\debug\deps\contracts-6e34dbf97624c6bb.exe)

running 6 tests
test late_generation_and_expected_exit_cannot_fail_current_attempt ... ok
test all_transition_pairs_and_stopping_terminal_rule ... ok
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

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 6.09s

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

### after-clippy.txt

完整文件：[after-clippy.txt](E:/AI_Agent/milestone25/evidence/D/after-clippy.txt)

```text
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.39s
```

### after-build.txt

完整文件：[after-build.txt](E:/AI_Agent/milestone25/evidence/D/after-build.txt)

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

✓ built in 137ms
```

### guard-probe.txt

完整文件：[guard-probe.txt](E:/AI_Agent/milestone25/evidence/D/guard-probe.txt)

```text
STORAGE_SELF_CHECK_FAILED
{
  "fixture": "E:\\AI_Agent\\.runtime\\task25\\storage-probe-5bf3644276734e698df37abbda5b7dbd",
  "imported_id": "49fb4d95-53a4-4383-bfb9-2156c70ffeb1",
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
      "mtime_ns": 1793811408306065500
    },
    {
      "path": "original.img",
      "sha256": "a46b67c8fb1c4c35fdfc8387c647f8c442a84e1520334a92a127f740b4c1dd5c",
      "mtime_ns": 1793811408306065500
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
    "ALLOW": 25,
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
      "mtime_ns": 1793811408306065500
    },
    {
      "path": "original.img",
      "sha256": "a46b67c8fb1c4c35fdfc8387c647f8c442a84e1520334a92a127f740b4c1dd5c",
      "mtime_ns": 1793811408306065500
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

### backend-focused.txt

完整文件：[backend-focused.txt](E:/AI_Agent/milestone25/evidence/D/backend-focused.txt)

```text
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1, pluggy-1.7.0 -- E:\AI_Agent\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: E:\AI_Agent
plugins: anyio-4.15.1
collecting ... collected 87 items

src-python/tests/storage/test_guard.py::test_three_roots_allow_but_source_write_delete_and_parent_delete_deny PASSED [  1%]
src-python/tests/storage/test_guard.py::test_normalization_and_symlink_cannot_escape PASSED [  2%]
src-python/tests/storage/test_guard.py::test_audit_insert_is_independent_and_nonrecursive PASSED [  3%]
src-python/tests/storage/test_guard.py::test_audits_are_append_only_and_not_default_filled[UPDATE-write_audit] PASSED [  4%]
src-python/tests/storage/test_guard.py::test_audits_are_append_only_and_not_default_filled[UPDATE-deletion_audit] PASSED [  5%]
src-python/tests/storage/test_guard.py::test_audits_are_append_only_and_not_default_filled[DELETE-write_audit] PASSED [  6%]
src-python/tests/storage/test_guard.py::test_audits_are_append_only_and_not_default_filled[DELETE-deletion_audit] PASSED [  8%]
src-python/tests/storage/test_guard.py::test_bounded_buffer_warns_and_flushes_without_reentering_guard PASSED [  9%]
src-python/tests/storage/test_guard.py::test_selfcheck_failure_keeps_business_writes_closed PASSED [ 10%]
src-python/tests/storage/test_guard.py::test_bootstrap_creates_trash_then_selfchecks_then_allows PASSED [ 11%]
src-python/tests/storage/test_guard.py::test_known_source_overlap_blocks_bootstrap_without_source_mutation PASSED [ 12%]
src-python/tests/storage/test_guard.py::test_audit_failure_denies_the_file_mutation PASSED [ 13%]
src-python/tests/storage/test_guard.py::test_insert_or_replace_cannot_rewrite_an_existing_audit PASSED [ 14%]
src-python/tests/storage/test_guard.py::test_audit_channel_reuses_one_connection_and_closes PASSED [ 16%]
src-python/tests/storage/test_guard.py::test_independent_audit_channel_cannot_write_outside_its_fixed_root PASSED [ 17%]
src-python/tests/storage/test_guard.py::test_source_inventory_is_reloaded_on_fresh_guard PASSED [ 18%]
src-python/tests/storage/test_guard.py::test_configured_output_root_is_checked_before_becoming_writable PASSED [ 19%]
src-python/tests/storage/test_recycle.py::test_full_delete_restore PASSED [ 20%]
src-python/tests/storage/test_recycle.py::test_reimport_and_conflict PASSED [ 21%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[False-False-False] PASSED [ 22%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[False-False-True] PASSED [ 24%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[False-True-False] PASSED [ 25%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[False-True-True] PASSED [ 26%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[True-False-False] PASSED [ 27%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[True-False-True] PASSED [ 28%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[True-True-False] PASSED [ 29%]
src-python/tests/storage/test_recycle.py::test_reimport_quadrants[True-True-True] PASSED [ 31%]
src-python/tests/storage/test_recycle.py::test_reimport_confirmed_race PASSED [ 32%]
src-python/tests/storage/test_recycle.py::test_reimport_unique_is_structured PASSED [ 33%]
src-python/tests/storage/test_recycle.py::test_reimport_batch_is_atomic PASSED [ 34%]
src-python/tests/storage/test_recycle.py::test_reimport_key_includes_raw PASSED [ 35%]
src-python/tests/storage/test_recycle.py::test_expiry_and_audit PASSED   [ 36%]
src-python/tests/storage/test_recycle.py::test_preview_binding[false] PASSED [ 37%]
src-python/tests/storage/test_recycle.py::test_preview_binding[tampered] PASSED [ 39%]
src-python/tests/storage/test_recycle.py::test_preview_binding[expired] PASSED [ 40%]
src-python/tests/storage/test_recycle.py::test_preview_binding[changed] PASSED [ 41%]
src-python/tests/storage/test_recycle.py::test_move_failure_rolls_back PASSED [ 42%]
src-python/tests/storage/test_recycle.py::test_commit_failure_rolls_back PASSED [ 43%]
src-python/tests/storage/test_recycle.py::test_restore_move_failure PASSED [ 44%]
src-python/tests/storage/test_recycle.py::test_purge_waits_for_long_run PASSED [ 45%]
src-python/tests/storage/test_recycle.py::test_multi_cube_fails_closed PASSED [ 47%]
src-python/tests/storage/test_recycle.py::test_incomplete_fail_closed[missing] PASSED [ 48%]
src-python/tests/storage/test_recycle.py::test_incomplete_fail_closed[manifest] PASSED [ 49%]
src-python/tests/storage/test_recycle.py::test_incomplete_fail_closed[file] PASSED [ 50%]
src-python/tests/storage/test_recycle.py::test_orphan_mapping_rollback PASSED [ 51%]
src-python/tests/storage/test_recycle.py::test_killed_move_is_quarantined PASSED [ 52%]
src-python/tests/storage/test_recycle.py::test_busy_and_startup_gate PASSED [ 54%]
src-python/tests/storage/test_recycle.py::test_stream_lease_until_body_end PASSED [ 55%]
src-python/tests/storage/test_recycle.py::test_http_contract_and_catalog PASSED [ 56%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[/absolute] PASSED [ 57%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[../escape] PASSED [ 58%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[exports\\cube] PASSED [ 59%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[C:/escape] PASSED [ 60%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[exports/../projects] PASSED [ 62%]
src-python/tests/storage/test_recycle.py::test_mapping_paths_refused[./exports] PASSED [ 63%]
src-python/tests/data/test_api.py::test_import_idempotency_raw_persistence_and_overrides PASSED [ 64%]
src-python/tests/data/test_api.py::test_directory_atomic_all_errors_and_no_source_write PASSED [ 65%]
src-python/tests/data/test_api.py::test_directory_names_unrelated_text_and_metadata_only PASSED [ 66%]
src-python/tests/data/test_api.py::test_existing_entries_also_get_unambiguous_directory_names PASSED [ 67%]
src-python/tests/data/test_api.py::test_concurrent_retries_create_only_one_id PASSED [ 68%]
src-python/tests/data/test_api.py::test_preview_png_pixel_orientation_and_bounds PASSED [ 70%]
src-python/tests/data/test_api.py::test_invalid_files_http400[missing] PASSED [ 71%]
src-python/tests/data/test_api.py::test_invalid_files_http400[corrupt] PASSED [ 72%]
src-python/tests/data/test_api.py::test_invalid_files_http400[undersize] PASSED [ 73%]
src-python/tests/data/test_api.py::test_invalid_files_http400[oversize] PASSED [ 74%]
src-python/tests/data/test_api.py::test_invalid_files_http400[empty] PASSED [ 75%]
src-python/tests/data/test_api.py::test_three_imports_do_not_block_health PASSED [ 77%]
src-python/tests/data/test_api.py::test_auth_identity_and_validation PASSED [ 78%]
src-python/tests/data/test_api.py::test_api_schema_snapshot PASSED       [ 79%]
src-python/tests/data/test_api.py::test_import_refreshes_prior_display_names_without_changing_batch_or_payload PASSED [ 80%]
src-python/tests/agent/test_project_paths.py::test_paths_defaults_round_trip_empty_values_identity_and_explicit_columns PASSED [ 81%]
src-python/tests/agent/test_project_paths.py::test_paths_unknown_fields_null_and_non_strings_fail_without_mutation_or_echo[body0] PASSED [ 82%]
src-python/tests/agent/test_project_paths.py::test_paths_unknown_fields_null_and_non_strings_fail_without_mutation_or_echo[body1] PASSED [ 83%]
src-python/tests/agent/test_project_paths.py::test_paths_unknown_fields_null_and_non_strings_fail_without_mutation_or_echo[body2] PASSED [ 85%]
src-python/tests/agent/test_project_paths.py::test_paths_unknown_fields_null_and_non_strings_fail_without_mutation_or_echo[body3] PASSED [ 86%]
src-python/tests/agent/test_project_paths.py::test_paths_unknown_fields_null_and_non_strings_fail_without_mutation_or_echo[body4] PASSED [ 87%]
src-python/tests/agent/test_project_paths.py::test_paths_unknown_fields_null_and_non_strings_fail_without_mutation_or_echo[body5] PASSED [ 88%]
src-python/tests/agent/test_project_paths.py::test_paths_unknown_fields_null_and_non_strings_fail_without_mutation_or_echo[body6] PASSED [ 89%]
src-python/tests/agent/test_project_paths.py::test_paths_invalid_or_unknown_project_is_rejected[get-invalid-id-400] PASSED [ 90%]
src-python/tests/agent/test_project_paths.py::test_paths_invalid_or_unknown_project_is_rejected[get-944de2f6-a7f7-4fa4-9f3a-009289020a09-404] PASSED [ 91%]
src-python/tests/agent/test_project_paths.py::test_paths_invalid_or_unknown_project_is_rejected[put-invalid-id-400] PASSED [ 93%]
src-python/tests/agent/test_project_paths.py::test_paths_invalid_or_unknown_project_is_rejected[put-944de2f6-a7f7-4fa4-9f3a-009289020a09-404] PASSED [ 94%]
src-python/tests/agent/test_project_paths.py::test_smb_normalizes_strings_without_connectivity_checks_or_credentials_echo PASSED [ 95%]
src-python/tests/agent/test_project_paths.py::test_saving_paths_does_not_change_payload_sources_files_or_guard_roots PASSED [ 96%]
src-python/tests/agent/test_project_paths.py::test_paths_survive_real_engine_process_restart PASSED [ 97%]
src-python/tests/agent/test_project_paths.py::test_paths_absent_from_logs_tools_and_real_llm_wire_body PASSED [ 98%]
src-python/tests/agent/test_project_paths.py::test_paths_require_authentication_before_saving PASSED [100%]

============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 87 passed, 1 warning in 28.60s ========================
```

### frontend-focused.txt

完整文件：[frontend-focused.txt](E:/AI_Agent/milestone25/evidence/D/frontend-focused.txt)

```text
✔ C delete preview opens the impact dialog; only its confirm button sends strict deletion (27.9563ms)
✔ C cancelling or unmounting a deletion confirmation never sends deletion (2.2152ms)
✔ C existing active import never asks confirmation and ignores all_datasets in the UI (0.5439ms)
✔ C only REIMPORT_CONFIRMATION_REQUIRED prompts, with a selected new-id choice and no request until click (1.8613ms)
✔ C reimport cancellation and concurrent active-record conflict never silently retry or reuse (3.0769ms)
✔ C restore requires the UI button, renders refusal reason, and incomplete items cannot restore (0.6916ms)
✔ C S11 recycle summary includes retained space, count, per-item dates and incomplete cleanup refusal (5.4484ms)
✔ C cold catalog follows every page and retains unavailable sources as visible summaries (1.3137ms)
✔ C engine generation clears immediately and an older response cannot replace the new catalog (0.4057ms)
✔ C stale failures and disposed requests cannot overwrite a current success (0.2151ms)
✔ C current catalog failure is shown and explicit retry recovers (0.3489ms)
✔ C three existing imports append only that batch; catalog refreshes global names without expanding visible scope (0.5974ms)
✔ C broken pagination fails instead of looping or silently hiding catalog rows (0.9942ms)
✔ G3 shared displayName uses the server name and preserves the legacy fallback (0.6212ms)
✔ G2 all_datasets refreshes a previously unique name without duplicating records (1.0939ms)
✔ G assistant choices and readable references use exactly the API display name (0.8863ms)
✔ C SMB and URL prefills become UNC strings, preserving independent empty and absent fields (1.6557ms)
✔ C rendered source and output inputs edit independently and save only the project defaults (11.684ms)
✔ C browse targets only its field, cancel preserves values, and S11 summary displays saved values without editing (0.797ms)
✔ C path form failure disables saving; disposal rejects stale GET and double save is suppressed (0.696ms)
✔ C project path IPC uses fixed ops, strips view extras, normalizes both paths and propagates refusal (0.4589ms)
ℹ tests 21
ℹ suites 0
ℹ pass 21
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 211.512
```

### acceptance.txt

完整文件：[acceptance.txt](E:/AI_Agent/milestone25/evidence/D/acceptance.txt)

```text
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1, pluggy-1.7.0 -- E:\AI_Agent\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: E:\AI_Agent
plugins: anyio-4.15.1
collecting ... collected 7 items

src-python/tests/storage/test_task25_acceptance.py::test_http_lifecycle_preserves_sources_audits_assets_and_has_no_business_orphans D_ACCEPTANCE_LIFECYCLE={"mode": "authenticated TestClient + real SQLite/FK + guarded moves + server-clock expiry", "cube_id": "7d6e610e-17b0-401e-b497-3057713f6ec9", "source_phases": {"before": [{"path": ".", "type": "directory", "bytes": null, "mtime_ns": 1793811383492554500, "sha256": null}, {"path": "sample.hdr", "type": "file", "bytes": 174, "mtime_ns": 1793811383492554500, "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772"}, {"path": "sample.img", "type": "file", "bytes": 48, "mtime_ns": 1793811383492554500, "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3"}], "after_delete": [{"path": ".", "type": "directory", "bytes": null, "mtime_ns": 1793811383492554500, "sha256": null}, {"path": "sample.hdr", "type": "file", "bytes": 174, "mtime_ns": 1793811383492554500, "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772"}, {"path": "sample.img", "type": "file", "bytes": 48, "mtime_ns": 1793811383492554500, "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3"}], "after_restore": [{"path": ".", "type": "directory", "bytes": null, "mtime_ns": 1793811383492554500, "sha256": null}, {"path": "sample.hdr", "type": "file", "bytes": 174, "mtime_ns": 1793811383492554500, "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772"}, {"path": "sample.img", "type": "file", "bytes": 48, "mtime_ns": 1793811383492554500, "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3"}], "after_purge": [{"path": ".", "type": "directory", "bytes": null, "mtime_ns": 1793811383492554500, "sha256": null}, {"path": "sample.hdr", "type": "file", "bytes": 174, "mtime_ns": 1793811383492554500, "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772"}, {"path": "sample.img", "type": "file", "bytes": 48, "mtime_ns": 1793811383492554500, "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3"}]}, "source_unchanged": true, "scans": {"before": {"rows": {"agent_session": 1, "annotation": 1, "annotation_draft": 1, "annotation_version": 1, "dataset_registry": 1, "inference_artifact": 1, "inference_run": 1, "label": 4, "label_schema": 1, "llm_settings": 6, "metric": 1, "model_artifact": 1, "model_registry": 1, "preprocess_artifact": 1, "preprocess_recipe": 1, "preprocess_recipe_version": 1, "preprocess_run": 1, "project": 1, "project_path_settings": 1, "project_recipe": 0, "sample_spectrum": 1, "sample_target": 1, "skill_upgrade_guard": 0, "skill_version": 3, "training_fold": 1, "training_mat": 1, "training_run": 1}, "checked_reference_values": 24, "findings": [], "excluded_archives": ["agent_plan_action", "agent_round", "agent_step", "llm_call", "recycle_bin", "recycle_health", "recycle_item"], "foreign_key_check": []}, "after_delete": {"rows": {"agent_session": 1, "annotation": 0, "annotation_draft": 0, "annotation_version": 0, "dataset_registry": 0, "inference_artifact": 0, "inference_run": 0, "label": 4, "label_schema": 1, "llm_settings": 6, "metric": 0, "model_artifact": 0, "model_registry": 0, "preprocess_artifact": 0, "preprocess_recipe": 1, "preprocess_recipe_version": 1, "preprocess_run": 0, "project": 1, "project_path_settings": 1, "project_recipe": 0, "sample_spectrum": 0, "sample_target": 0, "skill_upgrade_guard": 0, "skill_version": 3, "training_fold": 0, "training_mat": 0, "training_run": 0}, "checked_reference_values": 0, "findings": [], "excluded_archives": ["agent_plan_action", "agent_round", "agent_step", "llm_call", "recycle_bin", "recycle_health", "recycle_item"], "foreign_key_check": []}, "after_restore": {"rows": {"agent_session": 1, "annotation": 1, "annotation_draft": 1, "annotation_version": 1, "dataset_registry": 1, "inference_artifact": 1, "inference_run": 1, "label": 4, "label_schema": 1, "llm_settings": 6, "metric": 1, "model_artifact": 1, "model_registry": 1, "preprocess_artifact": 1, "preprocess_recipe": 1, "preprocess_recipe_version": 1, "preprocess_run": 1, "project": 1, "project_path_settings": 1, "project_recipe": 0, "sample_spectrum": 1, "sample_target": 1, "skill_upgrade_guard": 0, "skill_version": 3, "training_fold": 1, "training_mat": 1, "training_run": 1}, "checked_reference_values": 24, "findings": [], "excluded_archives": ["agent_plan_action", "agent_round", "agent_step", "llm_call", "recycle_bin", "recycle_health", "recycle_item"], "foreign_key_check": []}, "after_purge": {"rows": {"agent_session": 1, "annotation": 0, "annotation_draft": 0, "annotation_version": 0, "dataset_registry": 0, "inference_artifact": 0, "inference_run": 0, "label": 4, "label_schema": 1, "llm_settings": 6, "metric": 0, "model_artifact": 0, "model_registry": 0, "preprocess_artifact": 0, "preprocess_recipe": 1, "preprocess_recipe_version": 1, "preprocess_run": 0, "project": 1, "project_path_settings": 1, "project_recipe": 0, "sample_spectrum": 0, "sample_target": 0, "skill_upgrade_guard": 0, "skill_version": 3, "training_fold": 0, "training_mat": 0, "training_run": 0}, "checked_reference_values": 0, "findings": [], "excluded_archives": ["agent_plan_action", "agent_round", "agent_step", "llm_call", "recycle_bin", "recycle_health", "recycle_item"], "foreign_key_check": []}}, "audit_actions": {"DELETE": 2, "PURGE": 1, "RESTORE": 1}, "source_denials": [["D_SOURCE_WRITE", "DENY", "WRITE_TO_SOURCE_DENIED"], ["DELETE", "DENY", "WRITE_TO_SOURCE_DENIED"]], "restore_same_id": true, "protected_project_paths": true, "immutable_audit_history_preserved": true}
PASSED
src-python/tests/storage/test_task25_acceptance.py::test_orphan_scan_detects_undeclared_references_outside_known_recycle_tables[cube_id] D_ORPHAN_COUNTEREXAMPLE={"column": "cube_id", "sqlite_fk_check": [], "detected": [["d_reference_probe", "cube_id", "missing-object"]]}
PASSED
src-python/tests/storage/test_task25_acceptance.py::test_orphan_scan_detects_undeclared_references_outside_known_recycle_tables[version_id] D_ORPHAN_COUNTEREXAMPLE={"column": "version_id", "sqlite_fk_check": [], "detected": [["d_reference_probe", "version_id", "missing-object"]]}
PASSED
src-python/tests/storage/test_task25_acceptance.py::test_orphan_scan_detects_undeclared_references_outside_known_recycle_tables[run_id] D_ORPHAN_COUNTEREXAMPLE={"column": "run_id", "sqlite_fk_check": [], "detected": [["d_reference_probe", "run_id", "missing-object"]]}
PASSED
src-python/tests/storage/test_task25_acceptance.py::test_orphan_scan_detects_undeclared_references_outside_known_recycle_tables[cube_ids] D_ORPHAN_COUNTEREXAMPLE={"column": "cube_ids", "sqlite_fk_check": [], "detected": [["d_reference_probe", "cube_ids", "missing-object"]]}
PASSED
src-python/tests/storage/test_task25_acceptance.py::test_fresh_engine_startup_recovers_both_orphan_windows_and_gates_writes[unmapped_kill] D_ACCEPTANCE_RECOVERY={"mode": "unmapped_kill", "actual_killed_process_returncode": 1, "fresh_interpreter": true, "source_unchanged": true, "all_product_files_preserved": true, "business_rows_unchanged": true, "events": ["directories_created", "self_check", "business_ready", "recycle_reconcile_started", "recycle_business_ready", "directories_created", "self_check", "business_ready"], "ready_gate_injection": {"import": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}, "annotation": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}, "training": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}, "delete": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}}, "post_quarantine_blocks": {"get": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}, "import": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}, "preview": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}, "delete": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}}, "blocked_cubes": ["3f2f7a4f-865b-4dc0-8603-d78e307dd999"], "blocked_key_count": 1, "health": [["3f2f7a4f-865b-4dc0-8603-d78e307dd999", "ORPHAN_QUARANTINE"]], "audit_actions": {"ORPHAN_QUARANTINE": 1}}
PASSED
src-python/tests/storage/test_task25_acceptance.py::test_fresh_engine_startup_recovers_both_orphan_windows_and_gates_writes[mapped_rollback] D_ACCEPTANCE_RECOVERY={"mode": "mapped_rollback", "actual_killed_process_returncode": null, "fresh_interpreter": true, "source_unchanged": true, "all_product_files_preserved": true, "business_rows_unchanged": true, "events": ["directories_created", "self_check", "business_ready", "recycle_reconcile_started", "recycle_business_ready", "directories_created", "self_check", "business_ready"], "ready_gate_injection": {"import": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}, "annotation": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}, "training": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}, "delete": {"status": 503, "error": "RECYCLE_RECONCILIATION_REQUIRED"}}, "post_quarantine_blocks": {}, "blocked_cubes": [], "blocked_key_count": 0, "health": [], "audit_actions": {"DELETE": 1, "ORPHAN_ROLLBACK": 1}}
PASSED

============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 7 passed, 1 warning in 11.49s ========================
```

### reimport-isolation.txt

完整文件：[reimport-isolation.txt](E:/AI_Agent/milestone25/evidence/D/reimport-isolation.txt)

```text
E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
{
  "authority": "dfa67a7",
  "mode": "fresh synthetic ENVI + full dependent ledger / real SQLite + guarded filesystem",
  "old_id": "2c5cc7db-7d00-4500-8c32-18664c49d43e",
  "new_id": "04a8058e-914f-4a72-aadc-20473d875ca0",
  "confirmation_required": {
    "status": 409,
    "error": "REIMPORT_CONFIRMATION_REQUIRED"
  },
  "confirmed_summary": {
    "total": 1,
    "imported": 1,
    "existing": 0
  },
  "confirmed_existing": false,
  "active_ledger_counts": {
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
    "dataset_registry": 1
  },
  "old_rows_retained_in_recycle": [
    [
      "@file",
      5
    ],
    [
      "annotation",
      1
    ],
    [
      "annotation_draft",
      1
    ],
    [
      "annotation_version",
      1
    ],
    [
      "dataset_registry",
      1
    ],
    [
      "inference_artifact",
      1
    ],
    [
      "inference_run",
      1
    ],
    [
      "metric",
      1
    ],
    [
      "model_artifact",
      1
    ],
    [
      "model_registry",
      1
    ],
    [
      "preprocess_artifact",
      1
    ],
    [
      "preprocess_run",
      1
    ],
    [
      "sample_spectrum",
      1
    ],
    [
      "sample_target",
      1
    ],
    [
      "training_fold",
      1
    ],
    [
      "training_mat",
      1
    ],
    [
      "training_run",
      1
    ]
  ],
  "active_idempotency": [
    {
      "confirm_new": false,
      "id": "04a8058e-914f-4a72-aadc-20473d875ca0",
      "existing": true,
      "summary": {
        "total": 1,
        "imported": 0,
        "existing": 1
      }
    },
    {
      "confirm_new": true,
      "id": "04a8058e-914f-4a72-aadc-20473d875ca0",
      "existing": true,
      "summary": {
        "total": 1,
        "imported": 0,
        "existing": 1
      }
    }
  ],
  "restore_conflict": {
    "status": 409,
    "error": "RESTORE_CONFLICT"
  },
  "restore_denied_audit": [
    [
      "RESTORE_DENIED",
      "2c5cc7db-7d00-4500-8c32-18664c49d43e"
    ]
  ],
  "new_id_has_no_old_annotations_versions_runs": true,
  "source_unchanged": true
}
```

### production-delete-grep.txt

完整文件：[production-delete-grep.txt](E:/AI_Agent/milestone25/evidence/D/production-delete-grep.txt)

```text
src-python/spectrumagent/agent/mat.py:54:                storage.unlink(path, missing_ok=True)
src-python/spectrumagent/agent/mat.py:180:                storage.unlink(target)
src-python/spectrumagent/agent/mat.py:192:            storage.rmtree(temporary)
src-python/spectrumagent/annotation/projection_io.py:35:        storage.unlink(temporary, missing_ok=True)
src-python/spectrumagent/annotation/projection_io.py:122:                    storage.unlink(path)
src-python/spectrumagent/annotation/projection_io.py:128:                    storage.unlink(path, missing_ok=True)
src-python/spectrumagent/annotation/projection_io.py:135:                storage.unlink(path, missing_ok=True)
src-python/spectrumagent/annotation/session.py:405:                    storage.rmtree(directory)
src-python/spectrumagent/annotation/session.py:411:                    storage.rmtree(temporary)
src-python/spectrumagent/annotation/session.py:413:                storage.rmtree(backup)
src-python/spectrumagent/modeling/inference.py:285:                    storage.unlink(folder / name, missing_ok=True)
src-python/spectrumagent/modeling/run.py:226:                    storage.unlink(folder / (kind+".json"), missing_ok=True)
src-python/spectrumagent/preprocess/run.py:45:        storage.rmtree(resolved)
src-python/spectrumagent/preprocess/run.py:287:                        storage.unlink(path, missing_ok=True)
src-python/spectrumagent/storage/guard.py:170:                    probe.unlink(missing_ok=True)
src-python/spectrumagent/storage/guard.py:341:def unlink(path, *, missing_ok=False):
src-python/spectrumagent/storage/guard.py:342:    return resolve_delete(path).unlink(missing_ok=missing_ok)
src-python/spectrumagent/storage/guard.py:345:def rmtree(path):
src-python/spectrumagent/storage/guard.py:346:    return shutil.rmtree(resolve_delete(path))
src-python/spectrumagent/storage/guard.py:363:        rmtree(path)
src-python/spectrumagent/storage/recycle.py:332:            storage.rmtree(folder)
src-python/spectrumagent/storage/recycle.py:564:                        storage.rmtree(self.paths.trash / deletion)
backend/handshake.py:100:        storage.unlink(path)
backend/handshake.py:128:        storage.unlink(temporary, missing_ok=True)
```

### verify-scope.txt

完整文件：[verify-scope.txt](E:/AI_Agent/milestone25/evidence/D/verify-scope.txt)

```text
Anchors_equal=True
warning: unable to access 'C:\Users\Administrator/.config/git/ignore': Permission denied
Production_and_task_card_diff=0
warning: unable to access 'C:\Users\Administrator/.config/git/ignore': Permission denied
Existing_tracked_tests_diff=0
Production_write_files=15
New_D_test_file=E:\AI_Agent\src-python\tests\storage\test_task25_acceptance.py
Tracked_diff_check=PASS
```

## D 全生命周期取数 JSON（由原文解析，仅格式化）

```json
{
  "mode": "authenticated TestClient + real SQLite/FK + guarded moves + server-clock expiry",
  "cube_id": "7d6e610e-17b0-401e-b497-3057713f6ec9",
  "source_phases": {
    "before": [
      {
        "path": ".",
        "type": "directory",
        "bytes": null,
        "mtime_ns": 1793811383492554500,
        "sha256": null
      },
      {
        "path": "sample.hdr",
        "type": "file",
        "bytes": 174,
        "mtime_ns": 1793811383492554500,
        "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772"
      },
      {
        "path": "sample.img",
        "type": "file",
        "bytes": 48,
        "mtime_ns": 1793811383492554500,
        "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3"
      }
    ],
    "after_delete": [
      {
        "path": ".",
        "type": "directory",
        "bytes": null,
        "mtime_ns": 1793811383492554500,
        "sha256": null
      },
      {
        "path": "sample.hdr",
        "type": "file",
        "bytes": 174,
        "mtime_ns": 1793811383492554500,
        "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772"
      },
      {
        "path": "sample.img",
        "type": "file",
        "bytes": 48,
        "mtime_ns": 1793811383492554500,
        "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3"
      }
    ],
    "after_restore": [
      {
        "path": ".",
        "type": "directory",
        "bytes": null,
        "mtime_ns": 1793811383492554500,
        "sha256": null
      },
      {
        "path": "sample.hdr",
        "type": "file",
        "bytes": 174,
        "mtime_ns": 1793811383492554500,
        "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772"
      },
      {
        "path": "sample.img",
        "type": "file",
        "bytes": 48,
        "mtime_ns": 1793811383492554500,
        "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3"
      }
    ],
    "after_purge": [
      {
        "path": ".",
        "type": "directory",
        "bytes": null,
        "mtime_ns": 1793811383492554500,
        "sha256": null
      },
      {
        "path": "sample.hdr",
        "type": "file",
        "bytes": 174,
        "mtime_ns": 1793811383492554500,
        "sha256": "29b046af21bf7c88dcf7f623eb37c3a26aee2f3e4e658f35cf21f582c60d1772"
      },
      {
        "path": "sample.img",
        "type": "file",
        "bytes": 48,
        "mtime_ns": 1793811383492554500,
        "sha256": "ee853b6166da521127447ce0a8fbaf735bda6f17ee4647650b66885c632d37c3"
      }
    ]
  },
  "source_unchanged": true,
  "scans": {
    "before": {
      "rows": {
        "agent_session": 1,
        "annotation": 1,
        "annotation_draft": 1,
        "annotation_version": 1,
        "dataset_registry": 1,
        "inference_artifact": 1,
        "inference_run": 1,
        "label": 4,
        "label_schema": 1,
        "llm_settings": 6,
        "metric": 1,
        "model_artifact": 1,
        "model_registry": 1,
        "preprocess_artifact": 1,
        "preprocess_recipe": 1,
        "preprocess_recipe_version": 1,
        "preprocess_run": 1,
        "project": 1,
        "project_path_settings": 1,
        "project_recipe": 0,
        "sample_spectrum": 1,
        "sample_target": 1,
        "skill_upgrade_guard": 0,
        "skill_version": 3,
        "training_fold": 1,
        "training_mat": 1,
        "training_run": 1
      },
      "checked_reference_values": 24,
      "findings": [],
      "excluded_archives": [
        "agent_plan_action",
        "agent_round",
        "agent_step",
        "llm_call",
        "recycle_bin",
        "recycle_health",
        "recycle_item"
      ],
      "foreign_key_check": []
    },
    "after_delete": {
      "rows": {
        "agent_session": 1,
        "annotation": 0,
        "annotation_draft": 0,
        "annotation_version": 0,
        "dataset_registry": 0,
        "inference_artifact": 0,
        "inference_run": 0,
        "label": 4,
        "label_schema": 1,
        "llm_settings": 6,
        "metric": 0,
        "model_artifact": 0,
        "model_registry": 0,
        "preprocess_artifact": 0,
        "preprocess_recipe": 1,
        "preprocess_recipe_version": 1,
        "preprocess_run": 0,
        "project": 1,
        "project_path_settings": 1,
        "project_recipe": 0,
        "sample_spectrum": 0,
        "sample_target": 0,
        "skill_upgrade_guard": 0,
        "skill_version": 3,
        "training_fold": 0,
        "training_mat": 0,
        "training_run": 0
      },
      "checked_reference_values": 0,
      "findings": [],
      "excluded_archives": [
        "agent_plan_action",
        "agent_round",
        "agent_step",
        "llm_call",
        "recycle_bin",
        "recycle_health",
        "recycle_item"
      ],
      "foreign_key_check": []
    },
    "after_restore": {
      "rows": {
        "agent_session": 1,
        "annotation": 1,
        "annotation_draft": 1,
        "annotation_version": 1,
        "dataset_registry": 1,
        "inference_artifact": 1,
        "inference_run": 1,
        "label": 4,
        "label_schema": 1,
        "llm_settings": 6,
        "metric": 1,
        "model_artifact": 1,
        "model_registry": 1,
        "preprocess_artifact": 1,
        "preprocess_recipe": 1,
        "preprocess_recipe_version": 1,
        "preprocess_run": 1,
        "project": 1,
        "project_path_settings": 1,
        "project_recipe": 0,
        "sample_spectrum": 1,
        "sample_target": 1,
        "skill_upgrade_guard": 0,
        "skill_version": 3,
        "training_fold": 1,
        "training_mat": 1,
        "training_run": 1
      },
      "checked_reference_values": 24,
      "findings": [],
      "excluded_archives": [
        "agent_plan_action",
        "agent_round",
        "agent_step",
        "llm_call",
        "recycle_bin",
        "recycle_health",
        "recycle_item"
      ],
      "foreign_key_check": []
    },
    "after_purge": {
      "rows": {
        "agent_session": 1,
        "annotation": 0,
        "annotation_draft": 0,
        "annotation_version": 0,
        "dataset_registry": 0,
        "inference_artifact": 0,
        "inference_run": 0,
        "label": 4,
        "label_schema": 1,
        "llm_settings": 6,
        "metric": 0,
        "model_artifact": 0,
        "model_registry": 0,
        "preprocess_artifact": 0,
        "preprocess_recipe": 1,
        "preprocess_recipe_version": 1,
        "preprocess_run": 0,
        "project": 1,
        "project_path_settings": 1,
        "project_recipe": 0,
        "sample_spectrum": 0,
        "sample_target": 0,
        "skill_upgrade_guard": 0,
        "skill_version": 3,
        "training_fold": 0,
        "training_mat": 0,
        "training_run": 0
      },
      "checked_reference_values": 0,
      "findings": [],
      "excluded_archives": [
        "agent_plan_action",
        "agent_round",
        "agent_step",
        "llm_call",
        "recycle_bin",
        "recycle_health",
        "recycle_item"
      ],
      "foreign_key_check": []
    }
  },
  "audit_actions": {
    "DELETE": 2,
    "PURGE": 1,
    "RESTORE": 1
  },
  "source_denials": [
    [
      "D_SOURCE_WRITE",
      "DENY",
      "WRITE_TO_SOURCE_DENIED"
    ],
    [
      "DELETE",
      "DENY",
      "WRITE_TO_SOURCE_DENIED"
    ]
  ],
  "restore_same_id": true,
  "protected_project_paths": true,
  "immutable_audit_history_preserved": true
}
```

## D 全部锚点 grep -n 原文

命令全文 before-anchor-commands.ps1；after-anchors.txt 全文与此一致。完整对照表 anchor-review.md，无漂移。

### before-anchors.txt

完整文件：[before-anchors.txt](E:/AI_Agent/milestone25/evidence/D/before-anchors.txt)

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
src/App.tsx:113:    openingTicket.current++; setOpening(false); catalogController.reset(status.generation_id);
src/App.tsx:114:  }, [status.generation_id, catalogController]);
src/App.tsx:115:  useEffect(() => {
src/App.tsx:116:    if (status.phase !== 'Ready') return;
src/App.tsx:117:    void catalogController.load(status.generation_id);
src/App.tsx:118:    return () => catalogController.cancel();
src/App.tsx:119:  }, [status.phase, status.generation_id, catalogController]);
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
src-tauri/src/settings.rs:69:    pub fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
src-tauri/src/settings.rs:70:        self.validate()?;
src-tauri/src/settings.rs:71:        let (path, method, body) = match self {
src-tauri/src/settings.rs:72:            Self::GetLlm {} => ("/api/v1/settings/llm".into(), Method::GET, None),
src-tauri/src/settings.rs:73:            Self::PutLlm { body } => (
src-tauri/src/settings.rs:74:                "/api/v1/settings/llm".into(),
src-tauri/src/settings.rs:75:                Method::PUT,
src-tauri/src/settings.rs:76:                Some(body.clone()),
src-tauri/src/settings.rs:77:            ),
src-tauri/src/settings.rs:78:            Self::PutKey { key } => (
src-tauri/src/settings.rs:79:                "/api/v1/settings/llm/key".into(),
src-tauri/src/settings.rs:80:                Method::PUT,
src-tauri/src/settings.rs:81:                Some(json!({"key":key})),
src-tauri/src/settings.rs:82:            ),
src-tauri/src/settings.rs:83:            Self::GetProjectPaths { project_id } => (
src-tauri/src/settings.rs:84:                format!(
src-tauri/src/settings.rs:85:                    "/api/v1/settings/projects/{}/paths",
src-tauri/src/settings.rs:86:                    project_id.to_ascii_lowercase()
src-tauri/src/settings.rs:87:                ),
src-tauri/src/settings.rs:88:                Method::GET,
src-tauri/src/settings.rs:89:                None,
src-tauri/src/settings.rs:90:            ),
src-tauri/src/settings.rs:91:            Self::PutProjectPaths { project_id, body } => (
src-tauri/src/settings.rs:92:                format!(
src-tauri/src/settings.rs:93:                    "/api/v1/settings/projects/{}/paths",
src-tauri/src/settings.rs:94:                    project_id.to_ascii_lowercase()
src-tauri/src/settings.rs:95:                ),
src-tauri/src/settings.rs:96:                Method::PUT,
src-tauri/src/settings.rs:97:                Some(serde_json::to_value(body).map_err(|_| invalid_request())?),
src-tauri/src/settings.rs:98:            ),
src-tauri/src/settings.rs:99:        };
src-tauri/src/settings.rs:100:        Ok((fixed_url(port, &path)?, method, body))
src-tauri/src/settings.rs:106:    if let SettingsRequest::PutProjectPaths { body: fields, .. } = request {
src-tauri/src/settings.rs:107:        let paths: Vec<&str> = [fields.source_path.as_str(), fields.output_root.as_str()]
src-tauri/src/settings.rs:108:            .into_iter()
src-tauri/src/settings.rs:109:            .filter(|value| !value.is_empty())
src-tauri/src/settings.rs:110:            .collect();
src-tauri/src/settings.rs:111:        return forward_http_scoped(identity, url, method, body, false, (&[], &paths));
src-tauri/src/settings.rs:112:    }
src-tauri/src/settings.rs:113:    let secrets = match request {
src-tauri/src/settings.rs:114:        SettingsRequest::PutKey { key } => vec![key.as_str()],
src-tauri/src/settings.rs:115:        _ => vec![],
src-python/spectrumagent/modeling/migrations.py:68:    deferred = db.execute("PRAGMA defer_foreign_keys").fetchone()[0]
src-python/spectrumagent/modeling/migrations.py:69:    db.execute("SAVEPOINT modeling_132")
src-python/spectrumagent/modeling/migrations.py:70:    try:
src-python/spectrumagent/modeling/migrations.py:71:        if upgrade:
src-python/spectrumagent/modeling/migrations.py:72:            # Create-copy-drop-rename is essential for the parent: renaming the
src-python/spectrumagent/modeling/migrations.py:73:            # old parent would rewrite training_fold's FK. That table is never
src-python/spectrumagent/modeling/migrations.py:74:            # altered, renamed or copied. foreign_keys stays ON throughout.
src-python/spectrumagent/modeling/migrations.py:75:            names = ("training_run", "metric", "model_artifact")
src-python/spectrumagent/modeling/migrations.py:76:            for name in names:
src-python/spectrumagent/modeling/migrations.py:77:                statement = next(s for s in DDL.split(";") if f"CREATE TABLE IF NOT EXISTS {name} (" in s)
src-python/spectrumagent/modeling/migrations.py:78:                db.execute(statement.replace(f"{name} (", f"{name}_132 (", 1))
src-python/spectrumagent/modeling/migrations.py:79:                old_columns = [row[1] for row in db.execute(f"PRAGMA table_info({name})")]
src-python/spectrumagent/modeling/migrations.py:80:                fields = ",".join(old_columns)
src-python/spectrumagent/modeling/migrations.py:81:                db.execute(f"INSERT INTO {name}_132 ({fields}) SELECT {fields} FROM {name}")
src-python/spectrumagent/modeling/migrations.py:82:            db.execute("PRAGMA defer_foreign_keys=ON")
src-python/spectrumagent/modeling/migrations.py:83:            for name in ("metric", "model_artifact", "training_run"):
src-python/spectrumagent/modeling/migrations.py:84:                db.execute(f"DROP TABLE {name}")
src-python/spectrumagent/modeling/migrations.py:85:            for name in names:
src-python/spectrumagent/modeling/migrations.py:86:                db.execute(f"ALTER TABLE {name}_132 RENAME TO {name}")
src-python/spectrumagent/modeling/migrations.py:87:        for statement in DDL.split(";"):
src-python/spectrumagent/modeling/migrations.py:88:            if statement.strip():
src-python/spectrumagent/modeling/migrations.py:89:                db.execute(statement)
src-python/spectrumagent/modeling/migrations.py:90:        if db.execute("PRAGMA foreign_key_check").fetchall():
src-python/spectrumagent/modeling/migrations.py:91:            raise RuntimeError("Modeling migration foreign-key audit failed")
src-python/spectrumagent/modeling/migrations.py:92:        # SQLite retains a deferred DROP counter even after the parent exists
src-python/spectrumagent/modeling/migrations.py:93:        # again. Clear it only AFTER auditing every actual FK, then restore the
src-python/spectrumagent/modeling/migrations.py:94:        # caller's deferral setting. Never disable foreign_keys or skip audit.
src-python/spectrumagent/modeling/migrations.py:95:        db.execute("PRAGMA defer_foreign_keys=OFF")
src-python/spectrumagent/modeling/migrations.py:96:        if deferred:
src-python/spectrumagent/modeling/migrations.py:97:            db.execute("PRAGMA defer_foreign_keys=ON")
src-python/spectrumagent/modeling/migrations.py:98:        db.execute("RELEASE modeling_132")
src-python/spectrumagent/modeling/migrations.py:99:    except BaseException:
src-python/spectrumagent/modeling/migrations.py:100:        db.execute("ROLLBACK TO modeling_132")
src-python/spectrumagent/modeling/migrations.py:101:        db.execute("RELEASE modeling_132")
src-python/spectrumagent/modeling/migrations.py:102:        db.execute(f"PRAGMA defer_foreign_keys={int(deferred)}")
src/components/settings/settings-forward.ts:21:  getProjectPaths: (projectId: string): SettingsRequest => ({ op: 'get_project_paths', project_id: projectId }),
src/components/settings/settings-forward.ts:22:  putProjectPaths: (projectId: string, body: PathValues): SettingsRequest => ({ op: 'put_project_paths', project_id: projectId,
src/components/datasets/types.ts:26:export type SpectrumRegion = { l0: number; l1: number; s0: number; s1: number; raw?: boolean };
src-python/spectrumagent/api/project_paths.py:43:        db.execute("""CREATE TABLE IF NOT EXISTS project_path_settings (
src-python/spectrumagent/api/project_paths.py:57:    @router.get("/projects/{project_id}/paths", response_model=ProjectPathResponse)
src-python/spectrumagent/api/project_paths.py:66:    @router.put("/projects/{project_id}/paths", response_model=ProjectPathResponse)
```

## 本段逐文件清单

- [src-python/tests/storage/test_task25_acceptance.py](E:/AI_Agent/src-python/tests/storage/test_task25_acceptance.py)
- [milestone25/REPORT-D.md](E:/AI_Agent/milestone25/REPORT-D.md)
- [milestone25/evidence/D/acceptance-first-attempt.txt](E:/AI_Agent/milestone25/evidence/D/acceptance-first-attempt.txt)
- [milestone25/evidence/D/acceptance-second-attempt.txt](E:/AI_Agent/milestone25/evidence/D/acceptance-second-attempt.txt)
- [milestone25/evidence/D/acceptance.txt](E:/AI_Agent/milestone25/evidence/D/acceptance.txt)
- [milestone25/evidence/D/after-anchors.txt](E:/AI_Agent/milestone25/evidence/D/after-anchors.txt)
- [milestone25/evidence/D/after-build.txt](E:/AI_Agent/milestone25/evidence/D/after-build.txt)
- [milestone25/evidence/D/after-clippy.txt](E:/AI_Agent/milestone25/evidence/D/after-clippy.txt)
- [milestone25/evidence/D/after-node.txt](E:/AI_Agent/milestone25/evidence/D/after-node.txt)
- [milestone25/evidence/D/after-Python-backend.txt](E:/AI_Agent/milestone25/evidence/D/after-Python-backend.txt)
- [milestone25/evidence/D/after-Python-collected.txt](E:/AI_Agent/milestone25/evidence/D/after-Python-collected.txt)
- [milestone25/evidence/D/after-Python-src.txt](E:/AI_Agent/milestone25/evidence/D/after-Python-src.txt)
- [milestone25/evidence/D/after-Rust.txt](E:/AI_Agent/milestone25/evidence/D/after-Rust.txt)
- [milestone25/evidence/D/after-write-files.txt](E:/AI_Agent/milestone25/evidence/D/after-write-files.txt)
- [milestone25/evidence/D/anchor-review.md](E:/AI_Agent/milestone25/evidence/D/anchor-review.md)
- [milestone25/evidence/D/backend-focused.txt](E:/AI_Agent/milestone25/evidence/D/backend-focused.txt)
- [milestone25/evidence/D/before-anchor-commands.ps1](E:/AI_Agent/milestone25/evidence/D/before-anchor-commands.ps1)
- [milestone25/evidence/D/before-anchors.txt](E:/AI_Agent/milestone25/evidence/D/before-anchors.txt)
- [milestone25/evidence/D/before-build.txt](E:/AI_Agent/milestone25/evidence/D/before-build.txt)
- [milestone25/evidence/D/before-clippy.txt](E:/AI_Agent/milestone25/evidence/D/before-clippy.txt)
- [milestone25/evidence/D/before-cube-columns.txt](E:/AI_Agent/milestone25/evidence/D/before-cube-columns.txt)
- [milestone25/evidence/D/before-head.txt](E:/AI_Agent/milestone25/evidence/D/before-head.txt)
- [milestone25/evidence/D/before-node.txt](E:/AI_Agent/milestone25/evidence/D/before-node.txt)
- [milestone25/evidence/D/before-Python-backend.txt](E:/AI_Agent/milestone25/evidence/D/before-Python-backend.txt)
- [milestone25/evidence/D/before-Python-collected.txt](E:/AI_Agent/milestone25/evidence/D/before-Python-collected.txt)
- [milestone25/evidence/D/before-Python-src.txt](E:/AI_Agent/milestone25/evidence/D/before-Python-src.txt)
- [milestone25/evidence/D/before-Rust.txt](E:/AI_Agent/milestone25/evidence/D/before-Rust.txt)
- [milestone25/evidence/D/before-status-start.txt](E:/AI_Agent/milestone25/evidence/D/before-status-start.txt)
- [milestone25/evidence/D/before-status-stderr.txt](E:/AI_Agent/milestone25/evidence/D/before-status-stderr.txt)
- [milestone25/evidence/D/before-versions.txt](E:/AI_Agent/milestone25/evidence/D/before-versions.txt)
- [milestone25/evidence/D/before-write-files.txt](E:/AI_Agent/milestone25/evidence/D/before-write-files.txt)
- [milestone25/evidence/D/browser-harness.html](E:/AI_Agent/milestone25/evidence/D/browser-harness.html)
- [milestone25/evidence/D/browser-harness.tsx](E:/AI_Agent/milestone25/evidence/D/browser-harness.tsx)
- [milestone25/evidence/D/COMMANDS.md](E:/AI_Agent/milestone25/evidence/D/COMMANDS.md)
- [milestone25/evidence/D/delete-write-grep.txt](E:/AI_Agent/milestone25/evidence/D/delete-write-grep.txt)
- [milestone25/evidence/D/frontend-focused.txt](E:/AI_Agent/milestone25/evidence/D/frontend-focused.txt)
- [milestone25/evidence/D/guard-call-sites.txt](E:/AI_Agent/milestone25/evidence/D/guard-call-sites.txt)
- [milestone25/evidence/D/guard-probe.txt](E:/AI_Agent/milestone25/evidence/D/guard-probe.txt)
- [milestone25/evidence/D/lifecycle-result.json](E:/AI_Agent/milestone25/evidence/D/lifecycle-result.json)
- [milestone25/evidence/D/orphan-counterexamples.json](E:/AI_Agent/milestone25/evidence/D/orphan-counterexamples.json)
- [milestone25/evidence/D/production-delete-grep.txt](E:/AI_Agent/milestone25/evidence/D/production-delete-grep.txt)
- [milestone25/evidence/D/production-write-grep.txt](E:/AI_Agent/milestone25/evidence/D/production-write-grep.txt)
- [milestone25/evidence/D/raw-log-whitespace-check.txt](E:/AI_Agent/milestone25/evidence/D/raw-log-whitespace-check.txt)
- [milestone25/evidence/D/recovery-results.json](E:/AI_Agent/milestone25/evidence/D/recovery-results.json)
- [milestone25/evidence/D/reimport-isolation-probe.py](E:/AI_Agent/milestone25/evidence/D/reimport-isolation-probe.py)
- [milestone25/evidence/D/reimport-isolation.txt](E:/AI_Agent/milestone25/evidence/D/reimport-isolation.txt)
- [milestone25/evidence/D/ui-delete-preview.png](E:/AI_Agent/milestone25/evidence/D/ui-delete-preview.png)
- [milestone25/evidence/D/ui-generation-race.png](E:/AI_Agent/milestone25/evidence/D/ui-generation-race.png)
- [milestone25/evidence/D/ui-ipc-ledger.json](E:/AI_Agent/milestone25/evidence/D/ui-ipc-ledger.json)
- [milestone25/evidence/D/ui-server.txt](E:/AI_Agent/milestone25/evidence/D/ui-server.txt)
- [milestone25/evidence/D/ui-settings-summary.png](E:/AI_Agent/milestone25/evidence/D/ui-settings-summary.png)
- [milestone25/evidence/D/ui-settings.png](E:/AI_Agent/milestone25/evidence/D/ui-settings.png)
- [milestone25/evidence/D/ui-steps.json](E:/AI_Agent/milestone25/evidence/D/ui-steps.json)
- [milestone25/evidence/D/verify-scope.ps1](E:/AI_Agent/milestone25/evidence/D/verify-scope.ps1)
- [milestone25/evidence/D/verify-scope.txt](E:/AI_Agent/milestone25/evidence/D/verify-scope.txt)
- [milestone25/evidence/D/write-grep.txt](E:/AI_Agent/milestone25/evidence/D/write-grep.txt)
- [milestone25/evidence/D/write-pattern.txt](E:/AI_Agent/milestone25/evidence/D/write-pattern.txt)
