# Rust 监督器核心（检查点 1）

本提交完成进程监督器库、可注入 Win32 层、纯握手解析和确定性 stub 测试。
尚无 Tauri 主程序、前端或安装包；库测试不作为 release 外壳验收证据。

## 线程与所有权

- `EngineSupervisor` 在专用线程串行处理代次、状态迁移、重试和清理。
- 每代有独立的阻塞退出等待线程，以及只读握手与 health 轮询线程。结果携带递增整数代次，旧代结果不能改写当前代。
- 30 秒 deadline 归当前 actor 持有的 attempt；清理销毁该 attempt 后，不存在可迟到的旧计时任务。
- `ManagedProcess` 先挂起创建，再建 Job、配置 KILL_ON_JOB_CLOSE、加入、恢复并立即关闭线程句柄；进程和 Job 句柄留至清理。
- 阻塞等待和 Join 只在这些工作线程发生；未来 Tauri 关闭适配器必须在工作线程调用 `shutdown_and_join()`。
- 单实例插件属于下一阶段宿主适配器，必须第一个注册、取得应用级锁后才创建此监督器；这里没有第二套产品互斥锁。
- 外壳只读握手。`Handshake` 无 Debug/Serialize 实现；token 留在 Rust 内部的已验证会话中，Snapshot/事件不含 token。
- reqwest 唯一入口固定为 `http://127.0.0.1:<已验证端口>/health`，无代理、无重定向、有限超时。根据负责人本检查点授权，不用于 `/smoke` 或外网。
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
真实冻结引擎、SPECTRUM_ENGINE_EXE、Tauri 窗口、单实例、资源映射和最终 release 验收待负责人确认本检查点后实现。
