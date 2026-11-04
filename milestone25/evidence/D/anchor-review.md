# D 段锚点复核（无漂移）

权威卡 dfa67a7，D 未改生产源码或任务卡。下表摘录权威卡 §0.2；每一行开工 / 收口均吻合，原文见 before-anchors.txt / after-anchors.txt。范围锚点逐行展开，命令见 before-anchor-commands.ps1；不是按起始行推算。

### 0.2 行号锚点（全部 `grep -n` 直取；**2026-11-05 00:35 按 HEAD `cb97eeb` 全量校准，A/B/C 段收口后**）

| 事实 | 路径:行 | 判定行要点 |
|---|---|---|
| 列表初始为空（C 段改存摘要） | `src/App.tsx:56` | `useState<CatalogRecord[]>([])`；冷启动只存摘要，详情打开时单独 `get`（C 段前 `:54` 为 `DatasetRecord[]`） |
| 引擎换代次清空列表 | `src/App.tsx:111` | `setRecords([])`；重置与 Ready 自动加载在 `:113-119`，controller 按代次 + 请求序号双重失效（C 段前 `:85`） |
| 批次入口（**C 段已移除全库合并**） | `src/components/datasets/actions.ts:47` | `callbacks.imported(result.datasets)`；原 `DatasetPanel.tsx:48` 的 `mergeRecords(previous, result.all_datasets)` **已删除**，`catalog.ts` 的 `imported` / `refreshNames` 只更新当前可见集合 |
| 合并函数只加不删 | `src/components/datasets/types.ts:51` | `export function mergeRecords`；`Map` / `set` / `values` 在 `:52`/`:53`/`:54`（C 段前 `:50`/`51-53`） |
| 全库字段声明 | `src/components/datasets/types.ts:15`；`src-python/spectrumagent/api/schemas.py:36` | `all_datasets: ...`（**保留未删**，G2 仍依赖；两处未漂移） |
| 已有断言依赖该字段 | `src/components/datasets/display_names.test.ts:14` | `G2 all_datasets refreshes a previously unique name...`（原样未改） |
| 表内唯一约束 | `src-python/spectrumagent/api/registry.py:121` | `CREATE TABLE ... UNIQUE(header_key,raw)`（B 段前 `:120`，出卡时 `:118`） |
| 导入查重 | `src-python/spectrumagent/api/registry.py:177` | `SELECT id,payload ... WHERE header_key=? AND raw=?`（B 段前 `:156`） |
| 导入插入 | `src-python/spectrumagent/api/registry.py:199` | `INSERT INTO dataset_registry (...)`（B 段前 `:165`） |
| 全库记录生成 | `src-python/spectrumagent/api/registry.py:231` | `all_records = [...]`（B 段前 `:174`） |
| 读时重新打开源文件 | `src-python/spectrumagent/api/registry.py:258` / `:262` | `def readable` / `read_header(Path(stored.header_path), ...)`；失败抛 `SOURCE_CHANGED`（B 段前 `:200`/`:204`） |
| `payload` 整列重写 | `src-python/spectrumagent/api/registry.py:219` | `UPDATE dataset_registry SET payload=? WHERE id=?`（B 段前 `:161`） |
| 前端 IPC 请求联合类型 | `src/components/datasets/api.ts:7` | `export type Request = ...`（C 段新增 SMB→UNC 字符串归一 import，请求 op 未增；C 段前 `:6`） |
| 目录选择对话框 | `src/components/datasets/api.ts:45` | `open({ directory: true, multiple: true, filters: [...] })`（C 段前 `:44`） |
| 前端传输契约范围 | `src/components/datasets/types.ts:38-49` | `DatasetTransport`；B 段五个方法当前在 **`:42-46`**（C 段前 `41-45`，**旧卡误注 `39-43` 已更正**）；`SpectrumRegion` 仍在 `:26` |
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
| 项目级 projection 配置 | `src-python/spectrumagent/annotation/projection_io.py:21` / `:73` / `:74` | `:21` `return paths.root / "projects"/.../"projection.json"`；`:73` `root = paths.exports.resolve()`；`:74` `folder = root / cube_id`（A/B 段未改，仍吻合） |
| settings 请求枚举（C 后**五 op**） | `src-tauri/src/settings.rs:12/13/69-100` | `#[serde(...deny_unknown_fields)]` / `pub enum SettingsRequest`（`GetLlm`/`PutLlm`/`PutKey` + `GetProjectPaths`/`PutProjectPaths`）；`:69` `destination`、完整 match `:72-100`、项目路径分支 `:83`/`:91`；serde/enum `:12/13` 未漂移 |
| settings 敏感字段保护 | `src-tauri/src/settings.rs:106-111/114-115` | `:106-111` 两个路径**错误响应**不得回显（成功响应允许展示给 UI）；`:114-115` 原 key 全响应保护 |
| settings 前端契约 | `src/components/settings/settings-forward.ts:8/28` | `SettingsRequest` **五 op** 联合类型 / `settings_forward` 转发（`:21`/`:22` 两个新 op，严格投影、不接 URL/port） |
| settings 后端契约 | `src-python/spectrumagent/api/settings.py:14/16/22/26/31`；`src-python/spectrumagent/api/project_paths.py:43/57/66` | `make_router(paths)` / prefix / 三 LLM 端点；`:43` `CREATE TABLE project_path_settings`、`:57` GET、`:66` PUT |
| settings 注册与白名单 | `src-python/spectrumagent/app.py:54/93/110` | `:54` 实参已改 `make_settings_router(paths)`（**行号未漂移**）；`:93`/`:110` 前缀白名单**未改、未重复添加** |
| OpenAPI 受控产物 | `src-python/spectrumagent/api/openapi.json:644/738/794` | `:644` 项目路径 GET/PUT 共用 path item；`:738` `/llm`、`:794` `/llm/key` |



执行 verify-scope.ps1 的原文见 verify-scope.txt。
