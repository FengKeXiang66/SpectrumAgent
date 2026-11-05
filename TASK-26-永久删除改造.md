# TASK-26 永久删除改造（推翻 TASK-25 的回收站口径）

## 0. 一句话

把「删除进 30 天回收站」改成「人点确认后直接永久删除」：16 张业务表的关联行整行清除、工作区产物目录走统一守卫物理删除、原始 ENVI 源文件从头到尾不动；回收站链路、恢复、到期清理、三态对账、S11 占用统计全部下线。A–D 四段改造与验收已收口，**未提交**，原因见 §7。

## 1. 起因

TASK-25（`4cca8ad`，330 行权威卡）已按「删除一律进回收站、30 天可恢复」收口。用户在 2026-11-05 改口径：删除不要进回收站，直接永久删除，包括数据库中的路径记录与已经标注过的对应 json 文件。本文档为新的权威口径；TASK-25 卡保留为历史记录，其 §0.3 五条拍板、§3 回收站链路、§5 D 组验收断言**不再适用**。

## 2. 五条新拍板口径（替换 TASK-25 §0.3）

| # | 口径 |
|---|---|
| 1 | 删除 = 永久删除，无回收站、无 30 天窗口、无恢复入口，磁盘空间即时释放 |
| 2 | 原始 ENVI 源文件（.hdr / .img / 数据文件）不删、不复制、源目录零改动；守卫源目录只读红线保持 DENY |
| 3 | 数据库关联行（16 张业务表）与工作区产物（annotation.json / manifest.json / 模型 / 推理图等）一并清除；未登记到影响清单的残留目录不动 |
| 4 | 删除前必须由人点确认影响清单（preview_token 绑定 5 分钟），对话 / Agent 工具不能直接删 |
| 5 | 删除后同路径重新导入按首次导入处理，新建 id、不弹确认；并发撞车仍是结构化 409 `REIMPORT_ACTIVE_EXISTS` |

## 3. 用户确认的四项边界

| 问题 | 定案 |
|---|---|
| 源文件是否一起删 | 不删，守卫源目录红线不动 |
| 历史回收站数据 | 整套下线，启动时 DROP 三张 `recycle_*` 表并清空 `trash/` 内容 |
| 确认强度 | 沿用影响清单 + 人点确认，只改文案为「永久删除不可恢复」 |
| 重新导入 | 退化为三象限，不再有 `REIMPORT_CONFIRMATION_REQUIRED` |

## 4. 实现

### 4.1 删除主链路

`src-python/spectrumagent/storage/recycle.py` 的 `delete()` 重写为两阶段：

1. **事务阶段**（`BEGIN IMMEDIATE`）：复核 `_plan()` 与当前 `_selected()` 一致 → 把每个产物目录写入 `deletion_pending` → 按 16 表顺序删行 → `scrub()` 清掉 `agent_session.context_json` 里的失效引用 → 提交。
2. **文件阶段**：逐个 `_erase()` = `storage.rmtree(_owned(...))`，全部走 `guard.py:345` 的单一出口，ALLOW/DENY 全量留痕；成功一个就删一条 pending 行。

顺序刻意是「先提交行、再删文件」：崩在文件阶段只会留下无引用的孤儿目录，不会出现「行还在但文件没了」。`_plan()` / `_inventory()` / `preview_token` 的影响清单与哈希绑定原样保留。

### 4.2 崩溃一致性与启动清理

`deletion_pending` 只存 `deletion_id / seq / dataset_id / path / created_at`，**不存任何业务行 JSON、没有保留期**。启动时 `finish_pending()`：

- `_purge_legacy()`：一次性 DROP `recycle_bin` / `recycle_item` / `recycle_health`，清空 `trash/` 内容（保留空壳目录以兼容 `guard.self_check()` 的 trash 存在检查），记 `LEGACY_RECYCLE_PURGED` 审计；符号链接跳过并记 `quarantined_links`，不误删、不卡启动；
- 逐条续删 pending 目录（目录已不存在时幂等跳过），记 `DELETE_CLEANUP_DONE`；仍失败的留行并记 `DELETE_CLEANUP_PENDING`，下次启动再试。

审计事件：`DELETE`（含 `permanent: true` / `pending_directories`）、`DELETE_ABORTED`、`DELETE_PENDING`、`DELETE_CLEANUP_DONE` / `DELETE_CLEANUP_PENDING`、`LEGACY_RECYCLE_PURGED`。旧事件 `RESTORE` / `PURGE` / `ORPHAN_*` 全部消失。错误码改为 `DELETION_CLEANUP_REQUIRED`（503）/ `INVALID_DELETE_PATH` / `DELETE_INVENTORY_INCOMPLETE`。

### 4.3 契约

- `GET /api/v1/recycle`、`POST /api/v1/recycle/{id}/restore` 两个端点移除；OpenAPI 快照重新生成，删除相关 path 从 4 个变为 2 个（`delete/preview`、`delete`），tag 改 `deletion`。
- `POST /api/v1/datasets/{id}/delete` 返回 `{deletion_id, deleted_at, permanent, pending_directories, 影响清单摘要}`，不再有 `expires_at`。
- Rust `datasets_dev.rs` 移除 `RecycleList` / `Restore` 两个 op；新增 `retired_recycle_ops_are_rejected`，断言旧 op 不能反序列化复活。
- `api/registry.py` 四象限退化为三象限，移除 `recycle_bin` 查询分支。

### 4.4 前端

数据集列表移除「已删除（回收站）」筛选、恢复按钮、占用/预计释放日期；删除按钮与弹窗改「永久删除」，弹窗明确「数据库记录与程序产物永久删除，不可恢复；原始 ENVI 源文件保持不变」。S11 移除回收站占用统计与刷新请求，改为静态「删除口径」说明，保留出域禁运清单与出域记录占位。`confirm_new` 契约参数保留（后端竞态判定仍用），前端不再发送 `true`。

## 5. 明确不做

与 TASK-25 相同：NAS 只读挂载 / 凭据 / 连通性 / 产物实际写入 NAS 输出根（FR-A12、FR-A13 另立卡）；新格式；检索；报告导出；其他业务域；打包安装态冒烟；真实 NAS 联机；外部 LLM 真实调用。本次额外不做：不新增删除审计查询接口，S11 不展示删除计数。

## 6. 验收基线（2026-11-05 终值）

| 项 | 结果 |
|---|---|
| node | 239 / 239（`node --test "src/**/*.test.ts"`） |
| `npm run build` | `tsc --noEmit && vite build` 通过 |
| Python collected | 1552（1550 passed + 2 skipped），与 `--collect-only` 一致 |
| Python 分区 | backend 45；agent 487；annotation 377 + 2 skip；data 106；mat 6；modeling 145；preprocess 281；storage 46；根 57，均独立进程 + 独立临时根 |
| 核心新测试 | `test_recycle.py` 23 passed；`test_task25_acceptance.py` 6 passed（含真实 kill 子进程 + 新解释器续删、HTTP 生命周期、孤儿引用扫描 4 参数） |
| Rust | `cargo test` 全绿；`cargo clippy --all-targets -- -D warnings` 0 error |
| OpenAPI 快照 | `src-python/tests/data/test_api.py::test_api_schema_snapshot` 通过 |
| 生产写点 | 15 文件不变（`storage/recycle.py` 仍在清单内，调用点改为 `rmtree` / `unlink`）；无新增或删除的生产 `.py` 文件 |
| 守卫地基 | 三根白名单、源目录 DENY、append-only 审计、自检顺序、环形缓冲均未改；启动事件改为 `deletion_cleanup_started` / `deletion_business_ready` |

验收环境备注：本轮一度因 C 盘 0 字节导致 `sqlite3 disk I/O error` 与 fixture setup 报错；经用户确认清理历史 pytest 临时根（`t25df` / `t23` / `t25*` 等，内容仅 `pytest-of-Administrator`）后恢复 5.9GB，全部重跑通过。清理对象不含项目源码、`milestone25/evidence/` 证据或用户文件。

## 7. 工作区并发改动与提交建议

开工时 `git status --short` 为空（HEAD `4cca8ad`）。改造过程中工作区出现了**另一条工作线**的写入，与本任务无关：

- `src/components/settings/SmokePanel.tsx`（新文件，未跟踪）
- `src/screens/S01.tsx`、`src/App.tsx`（冒烟测试从 S01 移入 SmokePanel、shellError 重构）、`src/components/assistant/assistant.css`、`src/components/assistant/session-shell.test.ts`、`src/components/annotation/AnnotationWorkbench.tsx`
- `src-python/spectrumagent/annotation/engines/superpixels.py`（`n_segments` 800→200）、`src-python/tests/agent/test_workflows.py`、`src-python/tests/annotation/test_superpixels.py`

其中 `App.tsx`（我的 `onRestored` 移除）与 `S11.tsx`（我的删除口径段落）是**混合文件**。若只提交本任务文件而不带这些改动，HEAD 会因 `S01` 签名 / `SmokePanel` 引用断裂而编译失败。因此**本次不自动提交**，全部改动保留在工作区，由用户决定：

1. 两条工作线合并为一个提交（最简单，代码可编译）；
2. 或由用户先收口那条工作线，再让我按纯 TASK-26 文件清单单独提交。

纯 TASK-26 文件清单：`src-python/spectrumagent/{storage/recycle.py, api/recycle.py, api/registry.py, app.py, api/openapi.json}`、`src-python/tests/storage/{test_recycle.py, test_task25_acceptance.py}`、`src-tauri/src/datasets_dev.rs`、`src/components/datasets/{actions.ts, actions.test.ts, api.ts, api.test.ts, types.ts, DatasetPanel.tsx, RecycleView.ts, importDecision.ts, importDecision.test.ts}`、`src/screens/light-screens.test.ts`、本卡。混合文件：`src/App.tsx`、`src/screens/S11.tsx`。

未 tag、未 push、未打包。

## 8. 已知命名债

为保持 15 文件写点基线与契约路径稳定，以下历史标识**有意保留**，语义已变为永久删除：`storage/recycle.py` 模块名、`RecycleStore` 类名、`registry.recycle` / `app.state.recycle` 属性、`api/recycle.py` 模块名、`RecycleJobsMiddleware` 类名、`src/components/datasets/RecycleView.ts` 文件名、`test_recycle.py` / `test_task25_acceptance.py` 文件名。对外可见的 UI 文案、错误码、OpenAPI tag 与事件名均已去掉回收站语义。

## 9. 修订记录

| 日期 | 内容 |
|---|---|
| 2026-11-05 | 四项边界确认；A–D 四段改造与全量验收收口；因工作区并发改动，暂不提交 |
