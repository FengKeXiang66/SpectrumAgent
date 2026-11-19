# Rust 监督器核心（检查点 2 已验，检查点 3 进行中）

已完成进程监督器库、可注入 Win32 层、纯握手解析、stub 测试，以及 Tauri 开发宿主、
四态页面、失败页与常驻对话条。真实前端 invoke 已连接响应头增补后的新冻结批次。
最终 release 验收与安装包仍待后续检查点；开发模式证据不作为 release 验收证据。

## 线程与所有权

- `EngineSupervisor` 在专用线程串行处理代次、状态迁移、重试和清理。
- 每代有独立的阻塞退出等待线程，以及只读握手与 health 轮询线程。结果携带递增整数代次，旧代结果不能改写当前代。
- 30 秒 deadline 归当前 actor 持有的 attempt；清理销毁该 attempt 后，不存在可迟到的旧计时任务。
- `ManagedProcess` 先挂起创建，再建 Job、配置 KILL_ON_JOB_CLOSE、加入、恢复并立即关闭线程句柄；进程和 Job 句柄留至清理。
- 阻塞等待和 Join 只在工作线程发生；Tauri 关闭适配器用 spawn_blocking 调用 `shutdown_and_join()`，完成后才允许应用退出。
- 官方 single-instance 插件在宿主第一个注册，取得应用级锁后才创建监督器；没有第二套产品互斥锁。
- 外壳只读握手。`Handshake` 无 Debug/Serialize 实现；token 留在 Rust 内部的已验证会话中，Snapshot/事件不含 token。
- 负责人于 2026-10-18 检查点 3 批准 reqwest 仅请求本代 `127.0.0.1` 上固定 `/health` 与 `/smoke`；`/smoke` 对每个状态先核验响应头 `X-SpectrumAgent-Boot-Id`、`X-SpectrumAgent-Pid`。两路径用内部枚举与数字端口构建 URL，无代理、无重定向；health 总超时 500 ms，smoke 总超时 20 s，均在工作线程请求。JS 的 run_smoke 无参，token 只留在 Rust，不用于外网。新冻结批次及 stub/真实前端调用已回归；授权与新旧批次证据见 `artifacts/step3/checkpoint-3/CONTRACT-AMENDMENT.md`。
- 失败结构同时保留主退出原因与旧握手非法诊断；日志归属必须有本次子 PID、正确事件/日志器、UTC 时间窗及启动期错误族，旧日志、缺 PID 或 PID 不符均不回退推定。

## 本机复跑（依赖已按批准清单下载）

```powershell
$env:CARGO_HOME = 'E:\AI_Agent\.cargo-home'
$env:CARGO_TARGET_DIR = 'E:\AI_Agent\src-tauri\target'
$env:TEMP = 'E:\AI_Agent\artifacts\step3\checkpoint-1\temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
cargo fmt --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --check
cargo clippy --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --all-targets --all-features --locked --offline -- -D warnings
cargo test --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --all-features --locked --offline -- --nocapture --test-threads=1
cargo tree --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --all-features --locked --offline
```

`test-probes` 才编译 `supervisor-stub` 与对应集成测试。stub 的数据、握手和日志只写入
E 盘的 `src-tauri/target/`，不碰本机正式引擎数据目录；它不是产品引擎。
真实冻结引擎和 SPECTRUM_ENGINE_EXE 已在检查点 2 验收。本次开发 UI 指向
`artifacts/step2/revision-20261018-smoke-headers/dist/app/app.exe`，只用该批次
product-manifest.json 作为后续暂存参照；旧批次全部保留。

开发入口为根目录 `frontend.ps1 run tauri -- dev --no-watch`，先执行受版本控制的
`stage-backend.ps1`（默认 Canonical，另有显式 FaultFixture），必要时在当前进程设置
SPECTRUM_ENGINE_EXE。工具链与所有缓存在 E 盘，不更改用户/系统 PATH。
capabilities 仅四个固定命令及事件订阅，不开放通用 opener。新检出需先准备已批准依赖
并重建新冻结批次，确认 manifest 后再暂存；不得从残缺或未知产物目录直接构建。

开发态已实测 Ready/Failed 页面、启动和重试时隐藏、重试恢复、Ready 单实例激活、
快捷键/未知输入/真实冒烟及正常关窗清理。最终 release 验收另见
`artifacts/step3/checkpoint-4/`，以逐项状态为准。

`SPECTRUM_ACCEPTANCE_PROBE=1` 仅在验收时显式启用 45 秒有界诊断：主循环心跳、
固定无参 engine_status 内部 invoke、原生 eval_with_callback 读回完整 DOM、表单值及
localStorage/sessionStorage。实际握手 token 仅在 Rust 内存用于扫描原始回调串，
命中即拒绝归档；通过的完整快照写在应用数据根的 acceptance/，不写资源或安装目录。
不增加 JS 命令、capability、依赖或网络路径；普通启动不启用定时探针。
测试 stub 无参入口只用于真实宿主夹具，由显式 SPECTRUM_STUB_MODE 选择；
产品资源始终使用正式冻结 app.exe，不包含该 stub。
第 2 步 VM 项保持“待实机验证”，旧 exit code=70 内部原因仍为“未验证”。

生产外壳必须显式 `--features custom-protocol`；features=[] 的历史release构建不能当作发布态UI证据。当前修正批次先重新编译外壳并实测--no-bundle，再以相同特性bundle；外壳新SHA重新绑定，引擎批次不动。NSIS模板与升级纪律见 `nsis/README.md`，默认程序目录为 `%LOCALAPPDATA%\Programs\SpectrumAgent`，数据根不变。验收探针额外记录真实文档URL/script来源；仅启用探针时清理后留350ms关闭观察窗口供捕获Stopping DOM，普通启动无延迟。新证据见 checkpoint-4/release-custom-protocol-20261018/。
