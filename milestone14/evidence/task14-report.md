# TASK-14 启动白屏探针与兜底执行回报

日期：2026-11-03（Asia/Shanghai）。W1–W4 已实现，D1–D7 验收完成；保留改前既有 Clippy 失败。未提交 Git commit。

## 1. 逐文件改动

| 文件 | 实际改动 |
|---|---|
| src-tauri/src/main.rs | 注册无前端参数、成功返回 unit/null 的 boot_probe；记录 boot_received 时间及 generation。增加 BootMonitor 和按 generation 隔离的监控记录，show_window 显示并记录日志后异步起监控，窗口操作切回主线程。5s 仅 eval 一次 location.reload()，15s GiveUp 后原生 set_title 并写诊断文件，线程结束。原有 show/hide、引擎启动、单实例与关闭时序不变。 |
| src-tauri/src/boot.rs（新增） | 仅 std 的 BootAction、boot_decision 与 4 项纯函数单测。 |
| src/main.tsx | 新增 invoke import；模块顶层第 7 行执行 void invoke('boot_probe').catch(() => {})，早于第 10 行 createRoot 调用。未放入 React effect。 |
| src-tauri/build.rs | 按授权，仅在 open_exports_directory 后新增 boot_probe 一项（+1/-0）。 |
| src-tauri/capabilities/main.json | 按授权，在 allow-open-exports-directory 后新增 allow-boot-probe；description 十二→十三，并追加指定说明。+2/-1，净增一行；description 替换行属于明确授权。 |
| TASK-14-启动白屏探针与兜底.md | 按本轮授权补入 §2.3 的“引擎重试 ≠ 页面重载”三条口径，并同步 D1/D5 补充断言；更正 §2.3 所述开工实物函数范围。§3 ACL 配套由备卡方补卡的约定未替代为自行扩展。 |

logging.rs 无改动，复用原 ShellLog.event()。Python 237 个已跟踪文件哈希全部与开工一致；8 个在途前端文件哈希全部一致。Cargo.toml / Cargo.lock 未改，没有新依赖，没有改代理或持久 WebView2 配置。

构建自动生成的四份 gen/schemas 文件已恢复开工内容，新增的自动生成 boot_probe.toml 已清理，不纳入实现改动；它们在构建时由已授权的 build.rs / capability 重新生成。正式运行二进制的 ACL 实际调用已验证。

纯函数定义：

```rust
pub enum BootAction {
    Wait,
    Reload,
    GiveUp,
}

pub fn boot_decision(boot_seen: bool, reloaded: bool, elapsed: Duration) -> BootAction
```

文档与 generation 的边界：

- `main.rs:44` 的 BootMonitor.boot_at 属于当前 WebView 文档；不会在 begin_generation 时清空。
- `main.rs:470` 的原生 on_page_load 回调仅在 main WebView 的 PageLoadEvent::Started 调用 document_started() 清空 boot_at。location.reload、F5 和导航均由此原生加载事件触发；不依赖旧文档 JS。
- generations 为 BTreeMap<u64, BootGeneration>，每项独立记录 started / started_at / reload_attempted / finished。重复 show_window/激活不重置已有计数。
- 监控回调核验当前 supervisor generation 和关闭状态；旧 generation 的回调不操作新 generation 的窗口。boot 已到达则 Wait 并结束，无 reload/title/file 操作。

## 2. D1–D7 逐项结果

| 条目 | 结果与证据 |
|---|---|
| D1 | 通过：4.999s Wait、5.000s Reload、5.001s Reload；14.999s Wait、15s/60s GiveUp；已 boot 在 reloaded=false/true、多种 elapsed 和多个模拟 generation 中恒为 Wait。boot.rs 可独立 rustc --test 编译运行，4/4，通过过程不加载 WebView2。 |
| D2 | 通过：真实 native debug 实例出现 boot_received，说明命令经过 ACL 并实际返回；无 boot_reload / boot_timeout_final / 标题变化 / boot_failure.json。原生标题仍为“光谱数据 AI Agent”。改前显示 Ready 3194ms、首个可交互 DOM 3228ms；改后为 3340ms / 3407ms，单次对照同量级，无新增显示门槛。 |
| D3 | 通过：按卡临时注释 main.tsx 的 boot_probe 调用，同时临时注释因此变成 unused 的 invoke import，以通过 tsc；npm run build 后启动隔离 native 实例。5.021s boot_reload 成功一次；15.066s boot_timeout_final；set_title 和文件写入均成功，完整原始日志见下。 |
| D4 | 通过：在 D3 实例显示后观察 95.130s，boot_reload=1、boot_timeout_final=1，boot_received=0，未循环。独立证据为 .temp/task14-d4-runtime.json。 |
| D5 | 通过：状态单测验证旧 generation 已 reload/GiveUp 后，新 generation 仍有自己的首次预算；原生运行中终止本任务隔离目录握手对应的测试引擎，点击同一页面“重试”进入 generation 2。继续观察 38.362s，boot_received 全进程仍只有首次文档的 1 次；boot_reload=0、boot_title_changed=0、无失败文件，标题不变，页面 Ready。没有页面 reload。 |
| D6 | 通过：临时将 invoke 目标改为未注册且未授权的 task14_unregistered_boot_probe，使 Promise 实际拒绝；仅测试时在 catch 写入 data-task14-probe-rejected=true 作为观测标记。原生 DOM 捕获在 683ms 见到 catch 标记，3405ms 见到 Ready 且 interactive=true。正式源码已逐字恢复为空 catch 的 boot_probe 调用，所有临时模拟均已移除。 |
| D7 | 通过（既有失败除外）：cargo test 开工 89 / 最终 95 passed，新增 6 项全部通过；npm run build（含 tsc --noEmit）通过。严格全目标 Clippy 开工和最终均为 models.rs 18 处 + tests/models_forward.rs 20 处既有 unwrap 错误，38 个诊断位置的多重集完全一致，无新增；本次桌面二进制单独严格 Clippy 通过。 |

D3 是卡指定的“探针缺失”模拟，前端 React 仍会渲染；没有宣称复现那次偶发真实白屏。原生标题及诊断文件的触发只依赖 Rust 收不到 boot 的状态，不依赖 React 或对话框。

D3 完整日志序列（原样 UTC；该次窗口显示为北京时间 12:01:16.425）：

```jsonl
{"activated": true, "event": "window_shown", "generation_id": 1, "success": true, "timestamp": "2026-11-03T04:01:16.425Z", "visible": true}
{"elapsed_ms": 5021, "error": null, "event": "boot_reload", "generation_id": 1, "success": true, "timestamp": "2026-11-03T04:01:21.448Z"}
{"elapsed_ms": 15066, "event": "boot_timeout_final", "generation_id": 1, "timestamp": "2026-11-03T04:01:31.492Z"}
{"error": null, "event": "boot_title_changed", "generation_id": 1, "success": true, "timestamp": "2026-11-03T04:01:31.493Z", "title": "SpectrumAgent — 页面未加载，请查看日志"}
{"error": null, "event": "boot_failure_written", "generation_id": 1, "path": "E:\\AI_Agent\\.temp\\task14-runs\\no-probe\\SpectrumAgent\\logs\\boot_failure.json", "success": true, "timestamp": "2026-11-03T04:01:31.493Z"}
```

D4 终点观测：

```json
{
  "checked_at": "2026-11-03T04:02:51.555179+00:00",
  "window_shown_at": "2026-11-03T04:01:16.425Z",
  "observed_seconds": 95.130179,
  "boot_received_count": 0,
  "boot_reload_count": 1,
  "boot_timeout_final_count": 1,
  "failure_file_exists": true
}
```

## 3. boot_failure.json 实际内容

实际文件：`E:/AI_Agent/.temp/task14-runs/no-probe/SpectrumAgent/logs/boot_failure.json`，与本次壳层日志同目录。

```json
{
  "boot_at": null,
  "generation_id": 1,
  "reload_attempted": true,
  "started_at": "2026-11-03T04:01:16.425Z",
  "url": "http://127.0.0.1:1420/",
  "webview_version": "156.0.4314.58"
}
```

## 4. 两处 ACL 配套完整 diff

build.rs 恰好新增一行；capability 权限列表恰好新增一行，另按授权替换 description 那一行（所以文件净增一行）。没有其他字段或权限变更。

```diff
diff --git a/src-tauri/build.rs b/src-tauri/build.rs
index a3404c1..a793ac0 100644
--- a/src-tauri/build.rs
+++ b/src-tauri/build.rs
@@ -10,6 +10,7 @@ fn main() {
             "run_smoke",
             "open_data_directory",
             "open_exports_directory",
+            "boot_probe",
             // Permission is declarative; the handler enforces fixed routes and identity.
             "datasets_forward",
             "annotations_forward",
diff --git a/src-tauri/capabilities/main.json b/src-tauri/capabilities/main.json
index 043b79c..d1ff277 100644
--- a/src-tauri/capabilities/main.json
+++ b/src-tauri/capabilities/main.json
@@ -1,6 +1,6 @@
 {
   "identifier": "main",
-  "description": "主窗口订阅状态并调用十二个固定业务命令；datasets-forward 固定/api/v1/datasets/*，annotations-forward 固定数据集标注及/api/v1/projects、/api/v1/labels、/api/v1/catalog/plastic；preprocess-forward 固定/api/v1/preprocess/*及/api/v1/datasets/*/preprocess/*，取消选用固定DELETE，其余固定GET/POST，总超时300s；agent-forward 仅会话创建、消息与步骤，SSE收集后一次返回；settings-forward 仅LLM设置GET/PUT及key PUT；annotations-draft-forward 仅/api/v1/annotations/* 的草稿三路由、确认及训练MAT，固定GET/POST；models-forward 仅/api/v1/models 下十五个固定操作（list_targets/put_target/import_targets/create_run/preflight_run/list_runs/get_run/lv_sweep/register_model/list_models/set_model_stage/create_inference/get_inference/get_inference_map/get_coefficients），固定GET/POST/PUT，300s超时，8MiB响应、身份与代次核验；仅本代127.0.0.1握手端口、固定方法、响应8MiB并核验身份与代次，标签请求64KiB。原生选择仅允许open，不开放通用网络能力。",
+  "description": "主窗口订阅状态并调用十三个固定业务命令；datasets-forward 固定/api/v1/datasets/*，annotations-forward 固定数据集标注及/api/v1/projects、/api/v1/labels、/api/v1/catalog/plastic；preprocess-forward 固定/api/v1/preprocess/*及/api/v1/datasets/*/preprocess/*，取消选用固定DELETE，其余固定GET/POST，总超时300s；agent-forward 仅会话创建、消息与步骤，SSE收集后一次返回；settings-forward 仅LLM设置GET/PUT及key PUT；annotations-draft-forward 仅/api/v1/annotations/* 的草稿三路由、确认及训练MAT，固定GET/POST；models-forward 仅/api/v1/models 下十五个固定操作（list_targets/put_target/import_targets/create_run/preflight_run/list_runs/get_run/lv_sweep/register_model/list_models/set_model_stage/create_inference/get_inference/get_inference_map/get_coefficients），固定GET/POST/PUT，300s超时，8MiB响应、身份与代次核验；仅本代127.0.0.1握手端口、固定方法、响应8MiB并核验身份与代次，标签请求64KiB。原生选择仅允许open，不开放通用网络能力。boot-probe 仅记录页面启动心跳，无参数、无返回数据",
   "windows": [
     "main"
   ],
@@ -12,6 +12,7 @@
     "allow-run-smoke",
     "allow-open-data-directory",
     "allow-open-exports-directory",
+    "allow-boot-probe",
     "allow-datasets-forward",
     "allow-annotations-forward",
     "allow-preprocess-forward",
```

## 5. 基线、执行模式与证据位置

- Windows PowerShell；cargo / rustc 1.99.1；设置进程级 CARGO_HOME=E:/AI_Agent/.cargo-home，使用 offline debug 检查，没有下载依赖。
- 开工与最终都执行 `cargo test --offline --manifest-path src-tauri/Cargo.toml`；计数包含二进制单测、集成测试和 doc test，89→95。
- 开工与最终都执行 `cargo clippy --offline --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings`。提示词只列了 models.rs 的 18 处；实测还存在 models_forward 集成测试 20 处，均为改前既有，前后位置完全一致。本次新增 Rust 代码没有 .unwrap()。
- 补充执行 `cargo clippy --offline --manifest-path src-tauri/Cargo.toml --bin spectrum-agent -- -D warnings`，exit 0，确认新桌面实现不受既有测试失败遮挡。
- 纯模块另用 `rustc --edition 2024 --test src-tauri/src/boot.rs` 独立运行 4 项测试。
- `npm run build` 在最终恢复后通过（tsc --noEmit + Vite），正式构建输出与正常探针验收时一致。
- Native 验收模式：debug desktop 二进制、默认 devUrl http://127.0.0.1:1420/，由临时静态服务提供真实 npm build 产物。使用既有 SPECTRUM_ACCEPTANCE_PROBE=1 原生有界 DOM 观察器记录 Ready/interactive，不修改该观察器或启动顺序。
- LOCALAPPDATA 与 WEBVIEW2_USER_DATA_FOLDER 仅在测试子进程中指向工作区隔离目录，避免触碰用户数据库和被占用的配置目录。首轮受限启动出现 WebView2 HRESULT 0x800700AA，随后受限隔离进程停留在初始化；原生验收改为沙箱外的隔离子进程成功。没有改变持久 WebView2 配置、运行时版本或代理设置。
- 测试实例均通过原生关闭流程结束，临时 HTTP 服务已停止；正式 main.tsx 与模拟前正式副本字节一致。

主要证据：

| 证据 | 路径（工作区内） |
|---|---|
| cargo 基线 / 最终 | .temp/task14-cargo-baseline.log / .temp/task14-cargo-restored-final.log |
| Clippy 基线 / 最终 | .temp/task14-clippy-baseline.log / .temp/task14-clippy-restored-final.log |
| 桌面单独 Clippy | .temp/task14-clippy-bin-final.log |
| 正式前端最终构建 | .temp/task14-build-restored-final.log |
| 无 WebView 纯函数测试 | .temp/task14-boot-pure-tests.log |
| 正常与新 generation native 日志 | .temp/task14-runs/normal-verified/SpectrumAgent/logs/shell-20261103.log |
| D3 完整事件序列 / D4 终点 | .temp/task14-d3-log-sequence.jsonl / .temp/task14-d4-runtime.json |
| D5 / D6 观测 | .temp/task14-d5-runtime.json / .temp/task14-d6-runtime.json |
| D3 原生失败标题截图 | .temp/task14-no-probe-title.png |
| D5 正常标题截图 | .temp/task14-normal-generation2.png |
| D6 原始 DOM（含 catch 标记） | .temp/task14-runs/rejected-probe-verified/SpectrumAgent/acceptance/dom-22616.jsonl |

## 6. 行号漂移清单

| 卡引用 | 开工实物 | 改后位置 |
|---|---|---|
| show_window main.rs:225–240 | 函数实际 :284–297（:299 已是 run 起点）；卡范围与实物不同 | :349–363 |
| window_shown :234–235 | :293–294 | :358–359 |
| dialog 插件 :265 | :324 | :491 |
| 前端 React 挂载调用 | 开工 src/main.tsx:7 | :10，探针在 :7 |

新增定位：BootMonitor :44、document_started :51、boot_probe :86、start_boot_monitor :365、on_page_load :470；boot.rs 的 BootAction :4、boot_decision :10。卡 §2.3 已按本轮授权写入“文档 boot 与 generation 预算分离”的口径，并更正了其中开工函数范围。

## 7. 未决问题

TASK-14 实现与规定验收无未决项。Clippy 保留前述 38 处既有失败。2026-11-01 偶发真实白屏的根因仍未定位；按本卡只交付探针、一次重载和可见兜底，没有将其误报为根因已修复。
