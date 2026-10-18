## 完成到哪一步

检查点 3 的依赖安装、响应头契约增补及重冻、固定 smoke 客户端、Tauri 开发宿主、
四态 UI / 中文失败页 / 常驻对话条已实现并完成本轮开发态自检，停下等负责人复核。
本报告不是第 3 步最终验收关闭声明。20 项验收中所有未做的 release / 矩阵 / DOM 项
逐条标未验证；第 2 步 VM 继续待实机验证，旧 exit code=70 原因继续未验证。

提交链彼此分开：引擎 8e35a5d → 3acd979 → bc0b4b6 → e7c3c9d → 4437710；
工具链与两份 lock 同笔 753da8a；宿主/客户端/UI 实现 c8d35f0。
requirements-lock.txt SHA256 仍为 58e24b59da34461a17fd942b4047071e42b5120b3d474ba976a7e28535d40bcc。

新冻结批次唯一引用：artifacts/step2/revision-20261018-smoke-headers/product-manifest.json。
artifact_source_commit=3acd979f3b5a94ad32283eb1608c95f0b8721696；
manifest_generator_commit=e7c3c9d90f83d23639a4ee54832c8b4bc75bf706。
新引擎 39 pytest / 30 轮生命周期矩阵 / 七项交叉校验 / 544 文件暂存比对均通过，
八项完整原始输出见 artifacts/step2/REVISION-20261018-smoke-headers.md。
旧 manifest、旧 REPORT、旧 smoke 证据未修改；旧产物 544 文件逐项复核 0 差异。

工具链复制/精确版本/安装失败原文/完整 npm ls 与 cargo tree 见 INSTALLATION-REPORT.md。
single-instance 实际解析 2.5.4 后锁为 =2.5.4；没有解析其他版本，没有 TLS 绕过或 Python 新依赖。

## 命令与原始输出

本轮代码构建与正式复跑命令（实际输出分段完整附后）。冷缓存覆盖配置的逐字节副本为 cold-dev-config.json，复跑可直接引用该副本：

```powershell
$env:CARGO_HOME='E:AI_Agent\.cargo-home'
$env:CARGO_TARGET_DIR='E:AI_Agent\src-tauri\target'
$env:TEMP='E:AI_Agent\artifacts\step3\checkpoint-3\temp'
$env:TMP=$env:TEMP
& C:UsersAdministrator\.cargo\bin\cargo.exe fmt --manifest-path src-tauri\Cargo.toml --check
& C:UsersAdministrator\.cargo\bin\cargo.exe clippy --manifest-path src-tauri\Cargo.toml --all-targets --all-features --locked --offline -- -D warnings
& C:UsersAdministrator\.cargo\bin\cargo.exe test --manifest-path src-tauri\Cargo.toml --all-features --locked --offline -- --nocapture --test-threads=1
& E:AI_Agent\.toolchains\node24.19.0-npm10.8.2\node.exe --test artifacts\step3\checkpoint-3\frontend-state.test.mjs
& .\frontend.ps1 run build
& .\stage-backend.ps1
$env:SPECTRUM_ENGINE_EXE='E:AI_Agent\artifacts\step2\revision-20261018-smoke-headers\dist\app\app.exe'
$env:CARGO_NET_OFFLINE='true'
$env:WEBVIEW2_USER_DATA_FOLDER='E:AI_Agent\artifacts\step3\checkpoint-3\temp\webview-dev'
& .\frontend.ps1 run tauri -- dev --no-watch
# 最后冷缓存复验：temp/cold-dev.json 仅覆盖 beforeDevCommand 为 npm run dev -- --force
& .\frontend.ps1 run tauri -- dev --no-watch --config E:AI_Agent\artifacts\step3\checkpoint-3\temp\cold-dev.json
```

fmt --check exit=0、输出为空（host-fmt-delivery-output.txt；实际执行元数据 fmt-delivery-execution.json），clippy exit=0 无 warning；
当前实现提交 c8d35f0 的 Rust 全量 22 passed，另 1 个 compile-fail 文档测试 passed。
文档测试打印 E0308 是预期拒绝第三路径/任意 URL 字符串的证据，测试本身通过。
前端 strict tsc + Vite build 通过，另有 2 个迟到快照/代次竞态测试通过。

### 实现边界

EngineRoute 内部枚举只产生字面量 /health、/smoke；URL 起点为固定 127.0.0.1，
只设置已核验 u16 端口，不接受 host/path 字符串。health 保持 body 四项校验，
smoke 在读取 HTTP status 或 body 前验证两个头；无头/非法/错值均 IdentityMismatch，
包括 401/500，不将身份不明的响应当成普通冒烟失败。混合大小写头名实测通过。
有效身份的 409 是普通 Http 失败；302 不跟随到第三路径；成功 JSON 只解为五个数值指标。

run_smoke 前端无参数；State/AppHandle 为框架注入，JS 不能传 URL/端口/路径/Auth。
token 所在 Handshake 无 Debug/Serialize，保存于 Rust 私有 Arc 会话。
Tauri invoke 在 spawn_blocking 等待 Actor 回复，实际 HTTP 另在专用工作线程，
回传带 generation_id，过期结果被丢弃；前端也拒绝迟到快照让 Failed/Stopping 倒退 Ready。
health 500ms / smoke 20s 上限，无代理、无重定向，reqwest features 仅 blocking/json。

single-instance 第一个注册，取得锁后才只读旧握手并挂起创建引擎 → Job → 恢复。
关闭由工作线程 stop/join，确认清理后才允许应用退出。四个固定命令与事件订阅最小授权，
不给 JS 通用 opener；打开目录由 Rust 固定到 SpectrumAgent 数据根。
日志写入使用进程内共享互斥，避免宿主与监督器各自 writer 交错 JSON 行。

### 真实窗口操作记录

使用 computer-use 技能操作真实 WebView 窗口；没有用浏览器 mock 替代 invoke。
Ready → Ctrl+K → 输入“查看光谱数据” → Ctrl+Enter，显示“当前地基演示仅支持冒烟测试”；
选中后输入“运行冒烟测试” → Ctrl+Enter，显示真实五项指标；空输入点击发送也成功。
实际日志中的 smoke_finished 与原始 UI 可访问性输出相互对应，引用上述新引擎批次。

第二例 debug 外壳 PID 10816、exit=0，原引擎 PID 17540 / port 54183 / boot 7864e309
握手字节不变；CIM 仅 1 个引擎。窗口激活回调和 show/focus 日志保留。
taskkill /F 引擎后出现 Failed，退出码 1、原生 Windows 路径、禁用输入/发送；
“打开数据目录”打开 SpectrumAgent 文件夹。点击重试，上一代清理完成后进入新代。
第二次最终构建重试还确认提示/指标清空，没有冒称上一代结果属于新引擎。
最终 UI PID 22664 / port 56086 / boot 885a547a / generation 2，真实指标 elapsed_ms=218.991。

Starting 的真实 window.is_visible() 为 false，Ready 后为 true（首次启动和重试均有日志）；
Stopping 的实际状态迁移与清理日志已捕获，瞬态禁用 UI 未单独截图，不冒称视觉验证通过。
四轮开发运行、共六个引擎代次的退出与端口均只读复核消失；不冒充 10 轮 release 矩阵。
Job 终止引擎允许握手残留，外壳没有删文件；残留内容已打码记录，下次仅由引擎恢复。

### 20 项验收状态（全项口径，未验证不写通过）

| 项 | 本检查点实际结果 |
|---|---|
| 1 静态/构建 | 开发 fmt/clippy/tsc/Vite/测试通过；release tauri build --no-bundle 未验证 |
| 2 三组 supervisor 测试 | 通过；纯逻辑/Win32 注入/stub 分组，另补固定路由与 smoke 头场景 |
| 3 不存在 exe | CP2 与本轮 stub 的 SpawnFailed/code=2/立即失败通过；Tauri 对应失败页未单独验证 |
| 4 缺 DLL 两级 | 新引擎批次原生缺 DLL 及 CP2 副本证据通过；最终 release FaultFixture/Canonical 未验证 |
| 5 Resume 清理 | 注入验证 TerminateJobObject，句柄顺序与恰关一次通过 |
| 6 代次竞态 | Rust 纯逻辑/stub 与新增前端迟到快照竞态 2 项通过 |
| 7 Starting 30s 心跳/不冻结 | 库层真实 30s timeout 通过；Tauri 长等待心跳自动证据未验证 |
| 8 窗口可见性 | dev Starting/重试 visible=false、Ready=true，Failed 页实测；release 未验证 |
| 9 单实例三态 | dev Ready 第二例激活且不增引擎通过；Failed/Starting 激活未验证 |
| 10 常驻条/invoke | Ready 实际 invoke/快捷键/未知输入/发送及 Failed 禁用通过；Stopping 瞬态视觉未验证 |
| 11 三段计时 | 新引擎首启 705.066ms；窗口 show 有日志但不当作可交互；完整 dev/release 三段未验证 |
| 12 10轮关窗 | 4 轮开发运行的6个引擎代次均已退；10轮最终产物矩阵未验证 |
| 13 release 强杀10轮 | 未验证 |
| 14 Starting 强杀10轮 | 未验证 |
| 15 陈旧握手 | 新批次生命周期矩阵及 dev 跨次启动/重试恢复通过；最终 release 未验证 |
| 16 token | 6个实际值扫描原始5644行日志、UI文本、编译JS均0；DOM/localStorage完整审计未验证 |
| 17 四态/迁移/app_exit | 当前单元/注入/stub通过，实际迁移合法，app_exit为独立事件；最终产物完整覆盖未验证 |
| 18 资源路径 | 相对配置、忽略resources、Canonical544文件通过；release resolver/忽略env/--no-bundle实际布局未验证 |
| 19 三锁/git | 两份新锁同笔753da8a，Python锁不变；收尾归档提交后再核验git干净 |
| 20 两exe manifest | 提供自定义manifest和实际构建；两exe RT_MANIFEST提取/绑定SHA/LongPathsEnabled未验证；长路径功能留VM |

VM 状态沿用负责人确认：新 pristine f7ea81cf-6c3a-4823-9a7b-5fe77f4c2300；
不再引用旧检查点或 Hyper-V Disabled。restore 恢复验证、三段冷启动、断网安装仍待第4步 setup.exe。
Windows SQLite 排他锁双保险/完整 FR-D13 上下文子集按 prompt-final 延期，不引业务功能。

### 原始输出全文

### clippy（最终代码）

```text
    Checking spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.01s

```

### Rust HEAD 全量（含预期 compile-fail 原文）

```text
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `test` profile [unoptimized + debuginfo] target(s) in 5.97s
     Running unittests src\lib.rs (src-tauri\target\debug\deps\spectrum_agent-c477ec76ae2918b9.exe)

running 1 test
test health::route_tests::closed_routes_always_use_numeric_loopback_and_literal_paths ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src\main.rs (src-tauri\target\debug\deps\spectrum_agent-2f4eea3e6411e3bc.exe)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src\bin\supervisor_probe.rs (src-tauri\target\debug\deps\supervisor_probe-e5972fdf66b07d82.exe)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src\bin\supervisor_stub.rs (src-tauri\target\debug\deps\supervisor_stub-92b167030e8b4127.exe)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\causality.rs (src-tauri\target\debug\deps\causality-5ce90b31cbeef505.exe)

running 2 tests
test midnight_files_and_preexisting_partial_line_are_handled_without_fallback ... CAUSALITY pure function: launch/exit day files tracked, existing partial line excluded, no engine_boot/boot_id PID fallback
ok
test only_new_complete_lines_with_own_integer_pid_in_utc_window_can_be_cause ... CAUSALITY pure function: old/missing/wrong/noninteger PID, wrong logger/event/code, out-of-window, partial JSON excluded; own new complete line accepted
ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.07s

     Running tests\contracts.rs (src-tauri\target\debug\deps\contracts-418554dd67b2e116.exe)

running 6 tests
test all_transition_pairs_and_stopping_terminal_rule ... ok
test exact_fields_and_top_level_are_enforced ... ok
test late_generation_and_expected_exit_cannot_fail_current_attempt ... ok
test metadata_types_bounds_and_exact_strings_are_enforced ... ok
test times_reject_nonexistent_dates_leap_seconds_and_non_millisecond_formats ... ok
test valid_handshake_values_and_integer_utc_comparison ... ok

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\engine_path.rs (src-tauri\target\debug\deps\engine_path-7ba756e0a2f48fa3.exe)

running 1 test
test constructor_precedes_resource_and_rejects_non_engine_or_relative_paths ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\supervisor_stubs.rs (src-tauri\target\debug\deps\supervisor_stubs-0a179e3b2adfdd5c.exe)

running 9 tests
test absent_executable_immediately_fails_and_does_not_clean_invalid_old_handshake ... FAILURE DISPLAY handshake_path=E:\AI_Agent\src-tauri\target\stub-runtime\6860-1792316850774-1\run\handshake.json
MISSING PATH (constructor injection): kind=SpawnFailed elapsed_ms=14 preexisting_handshake_invalid=retained bytes_unchanged=true
ok
test retry_waits_for_cleanup_and_late_a_exit_cannot_change_b ... STUB retry: A_generation=1 B_generation=2 late_A_exit=discarded B=Ready
ok
test smoke_headers_are_checked_before_status_and_never_leak_token ... SMOKE STUB smoke-no-headers: response_identity_checked_before_status=true token_leaks=0
SMOKE STUB smoke-auth-failure: response_identity_checked_before_status=true token_leaks=0
SMOKE STUB smoke-wrong-boot: response_identity_checked_before_status=true token_leaks=0
SMOKE STUB smoke-bad-boot: response_identity_checked_before_status=true token_leaks=0
SMOKE STUB smoke-no-pid: response_identity_checked_before_status=true token_leaks=0
SMOKE STUB smoke-wrong-pid: response_identity_checked_before_status=true token_leaks=0
SMOKE STUB smoke-bad-pid: response_identity_checked_before_status=true token_leaks=0
SMOKE STUB ready: response_identity_checked_before_status=true token_leaks=0
SMOKE STUB smoke-http-failure: response_identity_checked_before_status=true token_leaks=0
SMOKE STUB smoke-redirect: response_identity_checked_before_status=true token_leaks=0
ok
test stub_alive_without_handshake_times_out_after_actual_30_seconds ... STUB no-handshake: pid=Some(23284) kind=StartupTimeout elapsed_ms=30032 pending_activation=true
ok
test stub_exit_after_ready_produces_exactly_one_failure_transition ... STUB ready-exit: pid=Some(26504) Ready->Failed(EngineExitedAfterReady) count=1
ok
test stub_immediate_exit_reports_actual_exit_code ... STUB immediate-exit: pid=Some(24532) code=23 kind=ExitedBeforeReady elapsed_ms=52
ok
test stub_ready_then_stop_has_no_listening_port_and_separate_app_exit ... STUB ready/stop: pid=Some(22912) port=59296 phase=Stopping port_absent=true app_exit=1 token_leaks=0
ok
test stub_tolerates_disconnected_health_client ... STUB transport: client disconnected without a request; stub remains Ready
ok
test stub_wrong_health_boot_id_fails_only_after_child_identity_validation ... STUB mismatch: pid=Some(27396) child_pid_and_created_at=verified failure_layer=health_boot_id kind=HealthIdentityMismatch
ok

test result: ok. 9 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 34.03s

     Running tests\win32_failures.rs (src-tauri\target\debug\deps\win32_failures-0c118d460e970771.exe)

running 3 tests
test five_injected_failures_use_correct_termination_wait_and_exact_handle_counts ... INJECT CreateProcessW: ["CreateProcessW(exe=E:\\bundle\\app.exe,cwd=E:\\bundle,inherit=0,flags=0x08000004,mutable_utf16=[34, 69, 58, 92, 98, 117, 110, 100, 108, 101, 92, 97, 112, 112, 46, 101, 120, 101, 34, 0])"]
INJECT CreateJobObjectW: ["CreateProcessW(exe=E:\\bundle\\app.exe,cwd=E:\\bundle,inherit=0,flags=0x08000004,mutable_utf16=[34, 69, 58, 92, 98, 117, 110, 100, 108, 101, 92, 97, 112, 112, 46, 101, 120, 101, 34, 0])","CreateJobObjectW(security=NULL)","TerminateProcess(101)","WaitForSingleObject(101,None)","CloseHandle(102)","CloseHandle(101)"]
INJECT SetInformationJobObject: ["CreateProcessW(exe=E:\\bundle\\app.exe,cwd=E:\\bundle,inherit=0,flags=0x08000004,mutable_utf16=[34, 69, 58, 92, 98, 117, 110, 100, 108, 101, 92, 97, 112, 112, 46, 101, 120, 101, 34, 0])","CreateJobObjectW(security=NULL)","SetInformationJobObject(103,KILL_ON_JOB_CLOSE)","TerminateProcess(101)","WaitForSingleObject(101,None)","CloseHandle(102)","CloseHandle(101)","CloseHandle(103)"]
INJECT AssignProcessToJobObject: ["CreateProcessW(exe=E:\\bundle\\app.exe,cwd=E:\\bundle,inherit=0,flags=0x08000004,mutable_utf16=[34, 69, 58, 92, 98, 117, 110, 100, 108, 101, 92, 97, 112, 112, 46, 101, 120, 101, 34, 0])","CreateJobObjectW(security=NULL)","SetInformationJobObject(103,KILL_ON_JOB_CLOSE)","AssignProcessToJobObject(103,101)","TerminateProcess(101)","WaitForSingleObject(101,None)","CloseHandle(102)","CloseHandle(101)","CloseHandle(103)"]
INJECT ResumeThread: ["CreateProcessW(exe=E:\\bundle\\app.exe,cwd=E:\\bundle,inherit=0,flags=0x08000004,mutable_utf16=[34, 69, 58, 92, 98, 117, 110, 100, 108, 101, 92, 97, 112, 112, 46, 101, 120, 101, 34, 0])","CreateJobObjectW(security=NULL)","SetInformationJobObject(103,KILL_ON_JOB_CLOSE)","AssignProcessToJobObject(103,101)","ResumeThread(102)","TerminateJobObject(103)","WaitForSingleObject(101,None)","CloseHandle(102)","CloseHandle(101)","CloseHandle(103)"]
ok
test success_closes_thread_immediately_and_cleanup_is_idempotent ... SUCCESS/CLEANUP: ["CreateProcessW(exe=E:\\bundle\\app.exe,cwd=E:\\bundle,inherit=0,flags=0x08000004,mutable_utf16=[34, 69, 58, 92, 98, 117, 110, 100, 108, 101, 92, 97, 112, 112, 46, 101, 120, 101, 34, 0])","CreateJobObjectW(security=NULL)","SetInformationJobObject(103,KILL_ON_JOB_CLOSE)","AssignProcessToJobObject(103,101)","ResumeThread(102)","CloseHandle(102)","GetProcessTimes(101)","TerminateJobObject(103)","WaitForSingleObject(101,None)","CloseHandle(101)","CloseHandle(103)"]
ok
test unconfirmed_cleanup_is_preserved_and_blocks_retry ... CLEANUP FAILURE: WaitForSingleObject error retained; cleanup_complete=false; retry blocked at generation=1
ok

test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.07s

   Doc-tests spectrum_agent

running 1 test
error[E0308]: mismatched types
   --> src\health.rs:105:18
    |
105 |     client.smoke("http://127.0.0.1:1234/third-path");
    |            ----- ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ expected `&Handshake`, found `&str`
    |            |
    |            arguments to this method are incorrect
    |
    = note: expected reference `&Handshake`
               found reference `&'static str`
note: method defined here
   --> src\health.rs:107:12
    |
107 |     pub fn smoke(&self, handshake: &Handshake) -> Result<SmokeMetrics, SmokeFailure> {
    |            ^^^^^

error: aborting due to 1 previous error

For more information about this error, try `rustc --explain E0308`.
test src\health.rs - health::HealthClient::smoke (line 101) - compile fail ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.16s


```

### 前端代次测试

```text
✔ late snapshot cannot resurrect Ready after Failed or Stopping (0.765ms)
✔ same-generation cleanup updates and a new retry generation are accepted (0.1265ms)
ℹ tests 2
ℹ suites 0
ℹ pass 2
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 858.7566

```

### tsc + Vite（最终代码）

```text

> spectrum-agent@0.1.0 build
> tsc --noEmit && vite build

vite v8.3.4 building client environment for production...
transforming...
✓ 20 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.37 kB │ gzip:  0.28 kB
dist/assets/index-DlY-5qsv.css    0.55 kB │ gzip:  0.36 kB
dist/assets/index-BVBpdjoe.js   226.31 kB │ gzip: 71.60 kB

✓ built in 106ms

```

### reqwest 全功能目标树

```text
reqwest v0.13.5
├── reqwest feature "blocking"
│   └── spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
│       ├── spectrum-agent feature "custom-protocol" (command-line)
│       ├── spectrum-agent feature "default" (command-line)
│       └── spectrum-agent feature "test-probes" (command-line)
└── reqwest feature "json"
    └── spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri) (*)

```

### Canonical 暂存

```text
validated_absolute_target=E:\AI_Agent\src-tauri\resources\backend source=E:\AI_Agent\artifacts\step2\revision-20261018-smoke-headers\dist\app mode=Canonical
report=E:\AI_Agent\artifacts\step3\staging-reports\20261018T092532286Z-Canonical-24969269.json matched_files=544 fault_fixture=False source_unchanged=true

```

### 强制重新优化缓存的 Tauri dev

```text

> spectrum-agent@0.1.0 tauri
> tauri dev --no-watch --config E:\AI_Agent\artifacts\step3\checkpoint-3\temp\cold-dev.json

     Running BeforeDevCommand (`npm run dev -- --force`)

> spectrum-agent@0.1.0 dev
> vite --force

17:41:18 [vite] (client) Forced re-optimization of dependencies
2026-10-18T09:41:18.364Z vite:deps (client) removing old cache dir E:/AI_Agent/node_modules/.vite/deps
2026-10-18T09:41:18.383Z vite:deps scanning for dependencies...

  VITE v8.3.4  ready in 190 ms

  ➜  Local:   http://127.0.0.1:1420/
2026-10-18T09:41:18.388Z vite:deps Crawling dependencies using entries: 
  E:/AI_Agent/index.html
2026-10-18T09:41:18.398Z vite:deps Scan completed in 14.95ms: 
  @tauri-apps/api/core -> E:/AI_Agent/node_modules/@tauri-apps/api/core.js
  @tauri-apps/api/event -> E:/AI_Agent/node_modules/@tauri-apps/api/event.js
  react -> E:/AI_Agent/node_modules/react/index.js
  react-dom/client -> E:/AI_Agent/node_modules/react-dom/client.js
  react/jsx-dev-runtime -> E:/AI_Agent/node_modules/react/jsx-dev-runtime.js
2026-10-18T09:41:18.399Z vite:deps creating package.json in E:/AI_Agent/node_modules/.vite/deps_temp_ed712ad5
     Running DevCommand (`cargo  run --no-default-features --color always --`)
2026-10-18T09:41:18.433Z vite:deps static imports crawl ended
2026-10-18T09:41:18.511Z vite:deps Dependencies bundled in 111.24ms
2026-10-18T09:41:18.511Z vite:deps using post-scan optimizer result, the scanner found every used dependency
2026-10-18T09:41:18.512Z vite:deps creating _metadata.json in E:/AI_Agent/node_modules/.vite/deps_temp_ed712ad5
2026-10-18T09:41:18.515Z vite:deps renaming E:/AI_Agent/node_modules/.vite/deps_temp_ed712ad5 to E:/AI_Agent/node_modules/.vite/deps
2026-10-18T09:41:18.517Z vite:deps dependencies optimized
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Building [=======================> ] 382/385: spectru…
    Building [=======================> ] 383/385: spectru…
    Building [=======================> ] 384/385: spectru…
                                                            
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 6.82s
     Running `target\debug\spectrum-agent.exe`
[1018/174335.602:ERROR:ui\gfx\win\window_impl.cc:172] Failed to unregister class Chrome_WidgetWin_0. Error = 1412

```

### 单实例

```text
{
  "second_shell_pid": 10816,
  "second_exit_code": 0,
  "owner_pid": 17540,
  "boot_id": "7864e309",
  "port": 54183,
  "handshake_bytes_unchanged": true,
  "stdout": "",
  "stderr": ""
}
```

### 单实例进程数

```text
{"ProcessId":17540,"ParentProcessId":14868,"ExecutablePath":"E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\app.exe"}

```

### 未知请求

```text
{
  "document_text": "查看光谱数据",
  "focused_element": "15 文档 光谱数据 AI Agent Value: http://127.0.0.1:1420/ ID: RootWebArea",
  "tree": "Window: \"光谱数据 AI Agent\", App: spectrum-agent.exe.\n\t0 窗口 光谱数据 AI Agent Secondary Actions: Raise\n\t\t7 窗格\n\t\t\t8 窗格 光谱数据 AI Agent\n\t\t\t\t9 窗格 (disabled)\n\t\t\t\t10 区域 光谱数据 AI Agent - Web 内容\n\t\t\t\t\t11 区域\n\t\t\t\t\t\t12 区域\n\t\t\t\t\t\t13 区域\n\t\t\t\t\t\t\t14 区域\n\t\t\t\t\t\t\t\t15 文档 光谱数据 AI Agent Value: http://127.0.0.1:1420/ ID: RootWebArea\n\t\t\t\t\t\t\t\t\t16 组 ID: root\n\t\t\t\t\t\t\t\t\t\t17 主要\n\t\t\t\t\t\t\t\t\t\t\t18 标题 光谱数据 AI Agent · 地基演示\n\t\t\t\t\t\t\t\t\t\t\t19 状态\n\t\t\t\t\t\t\t\t\t\t\t\t20 文本 引擎已就绪\n\t\t\t\t\t\t\t\t\t\t\t21 文本 本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。\n\t\t\t\t\t\t\t\t\t\t\t22 文本 进程\n\t\t\t\t\t\t\t\t\t\t\t23 文本 17540\n\t\t\t\t\t\t\t\t\t\t\t24 文本 · 端口\n\t\t\t\t\t\t\t\t\t\t\t25 文本 54183\n\t\t\t\t\t\t\t\t\t\t\t26 文本 · 启动代次\n\t\t\t\t\t\t\t\t\t\t\t27 文本 1\n\t\t\t\t\t\t\t\t\t\t28 页脚 常驻对话条\n\t\t\t\t\t\t\t\t\t\t\t29 状态\n\t\t\t\t\t\t\t\t\t\t\t\t30 文本 当前地基演示仅支持冒烟测试\n\t\t\t\t\t\t\t\t\t\t\t31 文本 hello 对话条\n\t\t\t\t\t\t\t\t\t\t\t32 编辑 (settable, string) hello 对话条 Description: 运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送） Value: 查看光谱数据 ID: agent-input\n\t\t\t\t\t\t\t\t\t\t\t33 按钮 发送\n\t\t\t\t\t\t\t\t34 区域\n\t\t1 标题栏 (settable, string) Value: 光谱数据 AI Agent\n\t\t\t2 菜单栏 系统 ID: MenuBar\n\t\t\t\t3 菜单项目 系统\n\t\t\t4 按钮 最小化\n\t\t\t5 按钮 最大化\n\t\t\t6 按钮 关闭\n\nDocument text: ```\n查看光谱数据\n```"
}
```

### Ctrl+Enter 冒烟完成

```text
{
  "document_text": "￼",
  "focused_element": "15 文档 光谱数据 AI Agent Value: http://127.0.0.1:1420/ ID: RootWebArea",
  "tree": "Window: \"光谱数据 AI Agent\", App: spectrum-agent.exe.\n\t0 窗口 光谱数据 AI Agent Secondary Actions: Raise\n\t\t7 窗格\n\t\t\t8 窗格 光谱数据 AI Agent\n\t\t\t\t9 窗格 (disabled)\n\t\t\t\t10 区域 光谱数据 AI Agent - Web 内容\n\t\t\t\t\t11 区域\n\t\t\t\t\t\t12 区域\n\t\t\t\t\t\t13 区域\n\t\t\t\t\t\t\t14 区域\n\t\t\t\t\t\t\t\t15 文档 光谱数据 AI Agent Value: http://127.0.0.1:1420/ ID: RootWebArea\n\t\t\t\t\t\t\t\t\t16 组 ID: root\n\t\t\t\t\t\t\t\t\t\t17 主要\n\t\t\t\t\t\t\t\t\t\t\t18 标题 光谱数据 AI Agent · 地基演示\n\t\t\t\t\t\t\t\t\t\t\t19 状态\n\t\t\t\t\t\t\t\t\t\t\t\t20 文本 引擎已就绪\n\t\t\t\t\t\t\t\t\t\t\t21 文本 本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。\n\t\t\t\t\t\t\t\t\t\t\t22 文本 进程\n\t\t\t\t\t\t\t\t\t\t\t23 文本 17540\n\t\t\t\t\t\t\t\t\t\t\t24 文本 · 端口\n\t\t\t\t\t\t\t\t\t\t\t25 文本 54183\n\t\t\t\t\t\t\t\t\t\t\t26 文本 · 启动代次\n\t\t\t\t\t\t\t\t\t\t\t27 文本 1\n\t\t\t\t\t\t\t\t\t\t\t35 组 冒烟测试真实结果\n\t\t\t\t\t\t\t\t\t\t\t\t36 文本 { \"nan_ratio\": 0, \"reflectance_range\": [ -1.5275289241381491, 1.5275289241381491 ], \"bands\": 8, \"shape\": [ 8, 8, 8 ], \"elapsed_ms\": 236.619 }\n\t\t\t\t\t\t\t\t\t\t28 页脚 常驻对话条\n\t\t\t\t\t\t\t\t\t\t\t29 状态\n\t\t\t\t\t\t\t\t\t\t\t\t30 文本 冒烟测试完成。\n\t\t\t\t\t\t\t\t\t\t\t31 文本 hello 对话条\n\t\t\t\t\t\t\t\t\t\t\t32 编辑 (settable, string) hello 对话条 Description: 运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送） ID: agent-input\n\t\t\t\t\t\t\t\t\t\t\t33 按钮 发送\n\t\t\t\t\t\t\t\t34 区域\n\t\t1 标题栏 (settable, string) Value: 光谱数据 AI Agent\n\t\t\t2 菜单栏 系统 ID: MenuBar\n\t\t\t\t3 菜单项目 系统\n\t\t\t4 按钮 最小化\n\t\t\t5 按钮 最大化\n\t\t\t6 按钮 关闭\n\nDocument text: ```\n￼\n```"
}
```

### Failed 与路径/禁用

```text
{
  "document_text": "￼",
  "focused_element": "15 文档 光谱数据 AI Agent Value: http://127.0.0.1:1420/ ID: RootWebArea",
  "tree": "Window: \"光谱数据 AI Agent\", App: spectrum-agent.exe.\n\t0 窗口 光谱数据 AI Agent Secondary Actions: Raise\n\t\t7 窗格\n\t\t\t8 窗格 光谱数据 AI Agent\n\t\t\t\t9 窗格 (disabled)\n\t\t\t\t10 区域 光谱数据 AI Agent - Web 内容\n\t\t\t\t\t11 区域\n\t\t\t\t\t\t12 区域\n\t\t\t\t\t\t13 区域\n\t\t\t\t\t\t\t14 区域\n\t\t\t\t\t\t\t\t15 文档 光谱数据 AI Agent Value: http://127.0.0.1:1420/ ID: RootWebArea\n\t\t\t\t\t\t\t\t\t16 组 ID: root\n\t\t\t\t\t\t\t\t\t\t17 主要\n\t\t\t\t\t\t\t\t\t\t\t18 标题 光谱数据 AI Agent · 地基演示\n\t\t\t\t\t\t\t\t\t\t\t39 警报\n\t\t\t\t\t\t\t\t\t\t\t\t40 标题 引擎启动或运行失败\n\t\t\t\t\t\t\t\t\t\t\t\t41 文本 引擎意外退出。\n\t\t\t\t\t\t\t\t\t\t\t\t42 文本 退出码：1\n\t\t\t\t\t\t\t\t\t\t\t\t43 文本 握手路径：\n\t\t\t\t\t\t\t\t\t\t\t\t44 文本 C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run\\handshake.json\n\t\t\t\t\t\t\t\t\t\t\t\t45 文本 日志路径：\n\t\t\t\t\t\t\t\t\t\t\t\t46 文本 C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl\n\t\t\t\t\t\t\t\t\t\t\t\t47 文本 数据目录：\n\t\t\t\t\t\t\t\t\t\t\t\t48 文本 C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\n\t\t\t\t\t\t\t\t\t\t\t\t49 按钮 重试\n\t\t\t\t\t\t\t\t\t\t\t\t50 按钮 打开数据目录\n\t\t\t\t\t\t\t\t\t\t28 页脚 常驻对话条\n\t\t\t\t\t\t\t\t\t\t\t29 状态\n\t\t\t\t\t\t\t\t\t\t\t\t30 文本 引擎不可用，请查看失败原因与诊断入口。\n\t\t\t\t\t\t\t\t\t\t\t31 文本 hello 对话条\n\t\t\t\t\t\t\t\t\t\t\t32 编辑 (disabled) hello 对话条 Description: 运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送） ID: agent-input\n\t\t\t\t\t\t\t\t\t\t\t33 按钮 (disabled) 发送\n\t\t\t\t\t\t\t\t34 区域\n\t\t1 标题栏 (settable, string) Value: 光谱数据 AI Agent\n\t\t\t2 菜单栏 系统 ID: MenuBar\n\t\t\t\t3 菜单项目 系统\n\t\t\t4 按钮 最小化\n\t\t\t5 按钮 最大化\n\t\t\t6 按钮 关闭\n\nDocument text: ```\n￼\n```"
}
```

### 最终重试清空结果

```text
{
  "document_text": "光谱数据 AI Agent · 地基演示\n引擎已就绪\n本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。\n进程 22664 · 端口 56086 · 启动代次 2\n输入“运行冒烟测试”，或点击发送。\nhello 对话条\n￼\n发送",
  "focused_element": "8 窗格 光谱数据 AI Agent",
  "tree": "Window: \"光谱数据 AI Agent\", App: spectrum-agent.exe.\n\t0 窗口 光谱数据 AI Agent Secondary Actions: Raise\n\t\t7 窗格\n\t\t\t8 窗格 光谱数据 AI Agent\n\t\t\t\t9 窗格 (disabled)\n\t\t\t\t10 区域 光谱数据 AI Agent - Web 内容\n\t\t\t\t\t11 区域\n\t\t\t\t\t\t12 区域\n\t\t\t\t\t\t13 区域\n\t\t\t\t\t\t\t14 区域\n\t\t\t\t\t\t\t\t15 文档 光谱数据 AI Agent Value: http://127.0.0.1:1420/ ID: RootWebArea\n\t\t\t\t\t\t\t\t\t16 组 ID: root\n\t\t\t\t\t\t\t\t\t\t49 主要\n\t\t\t\t\t\t\t\t\t\t\t50 标题 光谱数据 AI Agent · 地基演示\n\t\t\t\t\t\t\t\t\t\t\t51 状态\n\t\t\t\t\t\t\t\t\t\t\t\t52 文本 引擎已就绪\n\t\t\t\t\t\t\t\t\t\t\t53 文本 本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。\n\t\t\t\t\t\t\t\t\t\t\t54 文本 进程\n\t\t\t\t\t\t\t\t\t\t\t55 文本 22664\n\t\t\t\t\t\t\t\t\t\t\t56 文本 · 端口\n\t\t\t\t\t\t\t\t\t\t\t57 文本 56086\n\t\t\t\t\t\t\t\t\t\t\t58 文本 · 启动代次\n\t\t\t\t\t\t\t\t\t\t\t59 文本 2\n\t\t\t\t\t\t\t\t\t\t60 页脚 常驻对话条\n\t\t\t\t\t\t\t\t\t\t\t61 状态\n\t\t\t\t\t\t\t\t\t\t\t\t62 文本 输入“运行冒烟测试”，或点击发送。\n\t\t\t\t\t\t\t\t\t\t\t63 文本 hello 对话条\n\t\t\t\t\t\t\t\t\t\t\t64 编辑 (settable, string) hello 对话条 Description: 运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送） ID: agent-input\n\t\t\t\t\t\t\t\t\t\t\t65 按钮 发送\n\t\t\t\t\t\t\t\t34 区域\n\t\t1 标题栏 (settable, string) Value: 光谱数据 AI Agent\n\t\t\t2 菜单栏 系统 ID: MenuBar\n\t\t\t\t66 菜单项目 系统\n\t\t\t4 按钮 最小化\n\t\t\t5 按钮 最大化\n\t\t\t6 按钮 关闭\n\nDocument text: ```\n光谱数据 AI Agent · 地基演示\n引擎已就绪\n本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。\n进程 22664 · 端口 56086 · 启动代次 2\n输入“运行冒烟测试”，或点击发送。\nhello 对话条\n￼\n发送\n```"
}
```

### 最终冒烟完成

```text
{
  "document_text": "光谱数据 AI Agent · 地基演示\n引擎已就绪\n本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。\n进程 22664 · 端口 56086 · 启动代次 2\n{\n  \"nan_ratio\": 0,\n  \"reflectance_range\": [\n    -1.5275289241381491,\n    1.5275289241381491\n  ],\n  \"bands\": 8,\n  \"shape\": [\n    8,\n    8,\n    8\n  ],\n  \"elapsed_ms\": 218.991\n}\n冒烟测试完成。\nhello 对话条\n￼\n发送",
  "focused_element": "8 窗格 光谱数据 AI Agent",
  "tree": "Window: \"光谱数据 AI Agent\", App: spectrum-agent.exe.\n\t0 窗口 光谱数据 AI Agent Secondary Actions: Raise\n\t\t7 窗格\n\t\t\t8 窗格 光谱数据 AI Agent\n\t\t\t\t9 窗格 (disabled)\n\t\t\t\t10 区域 光谱数据 AI Agent - Web 内容\n\t\t\t\t\t11 区域\n\t\t\t\t\t\t12 区域\n\t\t\t\t\t\t13 区域\n\t\t\t\t\t\t\t14 区域\n\t\t\t\t\t\t\t\t15 文档 光谱数据 AI Agent Value: http://127.0.0.1:1420/ ID: RootWebArea\n\t\t\t\t\t\t\t\t\t16 组 ID: root\n\t\t\t\t\t\t\t\t\t\t49 主要\n\t\t\t\t\t\t\t\t\t\t\t50 标题 光谱数据 AI Agent · 地基演示\n\t\t\t\t\t\t\t\t\t\t\t51 状态\n\t\t\t\t\t\t\t\t\t\t\t\t52 文本 引擎已就绪\n\t\t\t\t\t\t\t\t\t\t\t53 文本 本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。\n\t\t\t\t\t\t\t\t\t\t\t54 文本 进程\n\t\t\t\t\t\t\t\t\t\t\t55 文本 22664\n\t\t\t\t\t\t\t\t\t\t\t56 文本 · 端口\n\t\t\t\t\t\t\t\t\t\t\t57 文本 56086\n\t\t\t\t\t\t\t\t\t\t\t58 文本 · 启动代次\n\t\t\t\t\t\t\t\t\t\t\t59 文本 2\n\t\t\t\t\t\t\t\t\t\t\t67 组 冒烟测试真实结果\n\t\t\t\t\t\t\t\t\t\t\t\t68 文本 { \"nan_ratio\": 0, \"reflectance_range\": [ -1.5275289241381491, 1.5275289241381491 ], \"bands\": 8, \"shape\": [ 8, 8, 8 ], \"elapsed_ms\": 218.991 }\n\t\t\t\t\t\t\t\t\t\t60 页脚 常驻对话条\n\t\t\t\t\t\t\t\t\t\t\t61 状态\n\t\t\t\t\t\t\t\t\t\t\t\t62 文本 冒烟测试完成。\n\t\t\t\t\t\t\t\t\t\t\t63 文本 hello 对话条\n\t\t\t\t\t\t\t\t\t\t\t64 编辑 (settable, string) hello 对话条 Description: 运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送） ID: agent-input\n\t\t\t\t\t\t\t\t\t\t\t65 按钮 发送\n\t\t\t\t\t\t\t\t34 区域\n\t\t1 标题栏 (settable, string) Value: 光谱数据 AI Agent\n\t\t\t2 菜单栏 系统 ID: MenuBar\n\t\t\t\t66 菜单项目 系统\n\t\t\t4 按钮 最小化\n\t\t\t5 按钮 最大化\n\t\t\t6 按钮 关闭\n\nDocument text: ```\n光谱数据 AI Agent · 地基演示\n引擎已就绪\n本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。\n进程 22664 · 端口 56086 · 启动代次 2\n{\n  \"nan_ratio\": 0,\n  \"reflectance_range\": [\n    -1.5275289241381491,\n    1.5275289241381491\n  ],\n  \"bands\": 8,\n  \"shape\": [\n    8,\n    8,\n    8\n  ],\n  \"elapsed_ms\": 218.991\n}\n冒烟测试完成。\nhello 对话条\n￼\n发送\n```"
}
```

### PID/端口与残留握手

```text
{
  "checks": [
    {
      "pid": 23856,
      "port": 64094,
      "pid_absent": true,
      "port_absent": true
    },
    {
      "pid": 17444,
      "port": 62929,
      "pid_absent": true,
      "port_absent": true
    },
    {
      "pid": 17540,
      "port": 54183,
      "pid_absent": true,
      "port_absent": true
    },
    {
      "pid": 17880,
      "port": 63814,
      "pid_absent": true,
      "port_absent": true
    },
    {
      "pid": 17580,
      "port": 61000,
      "pid_absent": true,
      "port_absent": true
    },
    {
      "pid": 22664,
      "port": 56086,
      "pid_absent": true,
      "port_absent": true
    }
  ],
  "handshake_exists": true,
  "residual_handshake": {
    "boot_id": "885a547a",
    "pid": 22664,
    "process_created_at": "2026-10-18T09:42:33.162Z",
    "port": 56086,
    "token": "<redacted>",
    "protocol": 1,
    "version": "0.1.0",
    "started_at": "2026-10-18T09:42:33.804Z"
  },
  "interpretation": "Job termination does not claim graceful engine handshake cleanup; shell never deletes handshake; next engine owns stale recovery"
}
```

### 原始日志/实际token审计

```text
{
  "actual_tokens_count": 6,
  "original_source_log_files": [
    {
      "source": "C:/Users/Administrator/AppData/Local/SpectrumAgent/logs/engine-20261018.jsonl",
      "name": "engine-20261018.jsonl",
      "bytes": 869554,
      "json_lines": 4921,
      "sha256": "ffd73b10e68ec00ca6a1c716d86d1f3b62e017a5fee8b7b340f29591f675ad78",
      "actual_token_leaks": 0,
      "source_equals_archive": true
    },
    {
      "source": "C:/Users/Administrator/AppData/Local/SpectrumAgent/logs/shell-20261018.log",
      "name": "shell-20261018.log",
      "bytes": 101117,
      "json_lines": 723,
      "sha256": "c49104aa7b0ec6530bb8a81622eaf9bdbe3af1458c238d27a00d22dfe6290299",
      "actual_token_leaks": 0,
      "source_equals_archive": true
    }
  ],
  "original_source_token_leaks": 0,
  "ui_accessibility_files": [
    "ui-cold-optimizer-ready.txt",
    "ui-ctrl-k-focus.txt",
    "ui-engine-exit-failed-settled.txt",
    "ui-engine-exit-failed.txt",
    "ui-engine-exit-taskkill-output.txt",
    "ui-final-engine-exit-taskkill-output.txt",
    "ui-final-retry-ready.txt",
    "ui-final-smoke-complete.txt",
    "ui-open-data-directory.txt",
    "ui-ready-initial.txt",
    "ui-ready-watch-filtered.txt",
    "ui-retry-ready.txt",
    "ui-smoke-keyboard-complete.txt",
    "ui-smoke-keyboard.txt",
    "ui-smoke-send-button-complete.txt",
    "ui-smoke-send-button.txt",
    "ui-unknown-input.txt"
  ],
  "ui_accessibility_token_leaks": 0,
  "frontend_bundle_files": [
    "index-BVBpdjoe.js"
  ],
  "frontend_bundle_token_leaks": 0,
  "dom_and_localStorage": "未验证：未进行浏览器 DOM / localStorage 完整导出，不能用可见文本代替",
  "scope": "actual tokens scanned in original source logs BEFORE archival; no redaction used as pass evidence"
}
```

### 旧产物逐项核对

```text
{
  "old_expected_files": 544,
  "old_actual_files": 544,
  "differences": [],
  "windows_path_order_equals_manifest": false
}

```

### 实际外壳关键原始日志（完整未删节源文件已归档）

```text
{"event":"shell_started","pid":17440,"timestamp":"2026-10-18T09:30:39.252Z"}
{"event":"single_instance_lock_acquired","timestamp":"2026-10-18T09:30:39.809Z"}
{"event":"process_created_suspended","generation_id":1,"pid":23856,"timestamp":"2026-10-18T09:30:39.820Z"}
{"event":"job_assigned","generation_id":1,"pid":23856,"timestamp":"2026-10-18T09:30:39.820Z"}
{"event":"thread_resumed_and_closed","generation_id":1,"pid":23856,"timestamp":"2026-10-18T09:30:39.821Z"}
{"boot_id":"16d20a85","event":"handshake_identity_verified","generation_id":1,"pid":23856,"process_created_at_ms":1792315839814,"timestamp":"2026-10-18T09:30:40.646Z"}
{"event":"health_verified","generation_id":1,"pid":23856,"port":64094,"timestamp":"2026-10-18T09:30:40.651Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"health_identity_matched","timestamp":"2026-10-18T09:30:40.651Z","to":"Ready"}
{"activated":true,"event":"window_shown","generation_id":1,"success":true,"timestamp":"2026-10-18T09:30:40.651Z"}
{"event":"state_transition","from":"Ready","generation_id":1,"reason":"application_close","timestamp":"2026-10-18T09:33:18.494Z","to":"Stopping"}
{"complete":true,"errors":[],"event":"generation_cleanup","generation_id":1,"timestamp":"2026-10-18T09:33:18.505Z"}
{"event":"app_exit","generation_id":1,"timestamp":"2026-10-18T09:33:18.505Z"}
{"event":"host_cleanup_completed","success":true,"timestamp":"2026-10-18T09:33:18.506Z"}
{"event":"shell_started","pid":17916,"timestamp":"2026-10-18T09:33:38.061Z"}
{"event":"single_instance_lock_acquired","timestamp":"2026-10-18T09:33:38.617Z"}
{"event":"process_created_suspended","generation_id":1,"pid":17444,"timestamp":"2026-10-18T09:33:38.631Z"}
{"event":"job_assigned","generation_id":1,"pid":17444,"timestamp":"2026-10-18T09:33:38.632Z"}
{"event":"thread_resumed_and_closed","generation_id":1,"pid":17444,"timestamp":"2026-10-18T09:33:38.632Z"}
{"boot_id":"e41c4b56","event":"handshake_identity_verified","generation_id":1,"pid":17444,"process_created_at_ms":1792316018629,"timestamp":"2026-10-18T09:33:39.283Z"}
{"event":"health_verified","generation_id":1,"pid":17444,"port":62929,"timestamp":"2026-10-18T09:33:39.287Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"health_identity_matched","timestamp":"2026-10-18T09:33:39.287Z","to":"Ready"}
{"activated":true,"event":"window_shown","generation_id":1,"success":true,"timestamp":"2026-10-18T09:33:39.288Z"}
{"event":"state_transition","from":"Ready","generation_id":1,"reason":"application_close","timestamp":"2026-10-18T09:34:46.372Z","to":"Stopping"}
{"complete":true,"errors":[],"event":"generation_cleanup","generation_id":1,"timestamp":"2026-10-18T09:34:46.388Z"}
{"event":"app_exit","generation_id":1,"timestamp":"2026-10-18T09:34:46.388Z"}
{"event":"host_cleanup_completed","success":true,"timestamp":"2026-10-18T09:34:46.389Z"}
{"event":"shell_started","pid":14868,"timestamp":"2026-10-18T09:34:56.070Z"}
{"event":"single_instance_lock_acquired","timestamp":"2026-10-18T09:34:56.601Z"}
{"event":"process_created_suspended","generation_id":1,"pid":17540,"timestamp":"2026-10-18T09:34:56.615Z"}
{"event":"job_assigned","generation_id":1,"pid":17540,"timestamp":"2026-10-18T09:34:56.616Z"}
{"event":"thread_resumed_and_closed","generation_id":1,"pid":17540,"timestamp":"2026-10-18T09:34:56.616Z"}
{"boot_id":"7864e309","event":"handshake_identity_verified","generation_id":1,"pid":17540,"process_created_at_ms":1792316096612,"timestamp":"2026-10-18T09:34:57.233Z"}
{"event":"health_verified","generation_id":1,"pid":17540,"port":54183,"timestamp":"2026-10-18T09:34:57.237Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"health_identity_matched","timestamp":"2026-10-18T09:34:57.237Z","to":"Ready"}
{"activated":true,"event":"window_shown","generation_id":1,"success":true,"timestamp":"2026-10-18T09:34:57.238Z"}
{"event":"smoke_requested","generation_id":1,"timestamp":"2026-10-18T09:36:30.636Z"}
{"event":"smoke_finished","generation_id":1,"result":{"Ok":{"bands":8,"elapsed_ms":236.619,"nan_ratio":0.0,"reflectance_range":[-1.5275289241381491,1.5275289241381491],"shape":[8,8,8]}},"timestamp":"2026-10-18T09:36:30.880Z"}
{"event":"smoke_requested","generation_id":1,"timestamp":"2026-10-18T09:36:52.803Z"}
{"event":"smoke_finished","generation_id":1,"result":{"Ok":{"bands":8,"elapsed_ms":116.007,"nan_ratio":0.0,"reflectance_range":[-1.5275289241381491,1.5275289241381491],"shape":[8,8,8]}},"timestamp":"2026-10-18T09:36:52.923Z"}
{"event":"shell_started","pid":10816,"timestamp":"2026-10-18T09:37:39.083Z"}
{"event":"single_instance_activation","timestamp":"2026-10-18T09:37:39.091Z"}
{"event":"activation_requested","generation_id":1,"pending_activation":true,"phase":"Ready","timestamp":"2026-10-18T09:37:39.092Z"}
{"activated":true,"event":"window_shown","generation_id":1,"success":true,"timestamp":"2026-10-18T09:37:39.092Z"}
{"activated":true,"event":"window_shown","generation_id":1,"success":true,"timestamp":"2026-10-18T09:37:39.092Z"}
{"event":"state_transition","from":"Ready","generation_id":1,"reason":"engine_failure","timestamp":"2026-10-18T09:37:56.781Z","to":"Failed"}
{"activated":true,"event":"window_shown","generation_id":1,"success":true,"timestamp":"2026-10-18T09:37:56.782Z"}
{"complete":true,"errors":[],"event":"generation_cleanup","generation_id":1,"timestamp":"2026-10-18T09:37:56.782Z"}
{"event":"state_transition","from":"Failed","generation_id":2,"reason":"retry_after_cleanup","timestamp":"2026-10-18T09:38:33.017Z","to":"Starting"}
{"event":"process_created_suspended","generation_id":2,"pid":17880,"timestamp":"2026-10-18T09:38:33.029Z"}
{"event":"job_assigned","generation_id":2,"pid":17880,"timestamp":"2026-10-18T09:38:33.029Z"}
{"event":"thread_resumed_and_closed","generation_id":2,"pid":17880,"timestamp":"2026-10-18T09:38:33.029Z"}
{"boot_id":"2c3d5ee0","event":"handshake_identity_verified","generation_id":2,"pid":17880,"process_created_at_ms":1792316313028,"timestamp":"2026-10-18T09:38:33.681Z"}
{"event":"health_verified","generation_id":2,"pid":17880,"port":63814,"timestamp":"2026-10-18T09:38:33.683Z"}
{"event":"state_transition","from":"Starting","generation_id":2,"reason":"health_identity_matched","timestamp":"2026-10-18T09:38:33.683Z","to":"Ready"}
{"activated":true,"event":"window_shown","generation_id":2,"success":true,"timestamp":"2026-10-18T09:38:33.684Z"}
{"event":"state_transition","from":"Ready","generation_id":2,"reason":"application_close","timestamp":"2026-10-18T09:39:17.572Z","to":"Stopping"}
{"complete":true,"errors":[],"event":"generation_cleanup","generation_id":2,"timestamp":"2026-10-18T09:39:17.584Z"}
{"event":"app_exit","generation_id":2,"timestamp":"2026-10-18T09:39:17.585Z"}
{"event":"host_cleanup_completed","success":true,"timestamp":"2026-10-18T09:39:17.585Z"}
{"event":"shell_started","pid":16416,"timestamp":"2026-10-18T09:41:25.312Z"}
{"event":"single_instance_lock_acquired","timestamp":"2026-10-18T09:41:25.927Z"}
{"event":"process_created_suspended","generation_id":1,"pid":17580,"timestamp":"2026-10-18T09:41:25.944Z"}
{"event":"job_assigned","generation_id":1,"pid":17580,"timestamp":"2026-10-18T09:41:25.944Z"}
{"event":"thread_resumed_and_closed","generation_id":1,"pid":17580,"timestamp":"2026-10-18T09:41:25.944Z"}
{"event":"window_hidden","generation_id":1,"success":true,"timestamp":"2026-10-18T09:41:25.949Z","visible":false}
{"boot_id":"544308d5","event":"handshake_identity_verified","generation_id":1,"pid":17580,"process_created_at_ms":1792316485939,"timestamp":"2026-10-18T09:41:26.597Z"}
{"event":"health_verified","generation_id":1,"pid":17580,"port":61000,"timestamp":"2026-10-18T09:41:26.601Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"health_identity_matched","timestamp":"2026-10-18T09:41:26.601Z","to":"Ready"}
{"activated":true,"event":"window_shown","generation_id":1,"success":true,"timestamp":"2026-10-18T09:41:26.612Z","visible":true}
{"event":"state_transition","from":"Ready","generation_id":1,"reason":"engine_failure","timestamp":"2026-10-18T09:42:09.857Z","to":"Failed"}
{"complete":true,"errors":[],"event":"generation_cleanup","generation_id":1,"timestamp":"2026-10-18T09:42:09.859Z"}
{"activated":true,"event":"window_shown","generation_id":1,"success":true,"timestamp":"2026-10-18T09:42:09.860Z","visible":true}
{"event":"state_transition","from":"Failed","generation_id":2,"reason":"retry_after_cleanup","timestamp":"2026-10-18T09:42:33.151Z","to":"Starting"}
{"event":"process_created_suspended","generation_id":2,"pid":22664,"timestamp":"2026-10-18T09:42:33.163Z"}
{"event":"job_assigned","generation_id":2,"pid":22664,"timestamp":"2026-10-18T09:42:33.163Z"}
{"event":"thread_resumed_and_closed","generation_id":2,"pid":22664,"timestamp":"2026-10-18T09:42:33.164Z"}
{"event":"window_hidden","generation_id":2,"success":true,"timestamp":"2026-10-18T09:42:33.188Z","visible":false}
{"event":"window_hidden","generation_id":2,"success":true,"timestamp":"2026-10-18T09:42:33.193Z","visible":false}
{"boot_id":"885a547a","event":"handshake_identity_verified","generation_id":2,"pid":22664,"process_created_at_ms":1792316553162,"timestamp":"2026-10-18T09:42:33.818Z"}
{"event":"health_verified","generation_id":2,"pid":22664,"port":56086,"timestamp":"2026-10-18T09:42:33.821Z"}
{"event":"state_transition","from":"Starting","generation_id":2,"reason":"health_identity_matched","timestamp":"2026-10-18T09:42:33.821Z","to":"Ready"}
{"activated":true,"event":"window_shown","generation_id":2,"success":true,"timestamp":"2026-10-18T09:42:33.886Z","visible":true}
{"event":"smoke_requested","generation_id":2,"timestamp":"2026-10-18T09:42:50.232Z"}
{"event":"smoke_finished","generation_id":2,"result":{"Ok":{"bands":8,"elapsed_ms":218.991,"nan_ratio":0.0,"reflectance_range":[-1.5275289241381491,1.5275289241381491],"shape":[8,8,8]}},"timestamp":"2026-10-18T09:42:50.455Z"}
{"event":"state_transition","from":"Ready","generation_id":2,"reason":"application_close","timestamp":"2026-10-18T09:43:35.421Z","to":"Stopping"}
{"complete":true,"errors":[],"event":"generation_cleanup","generation_id":2,"timestamp":"2026-10-18T09:43:35.433Z"}
{"event":"app_exit","generation_id":2,"timestamp":"2026-10-18T09:43:35.433Z"}
{"event":"host_cleanup_completed","success":true,"timestamp":"2026-10-18T09:43:35.434Z"}
```

## 遇到的问题

1. CLI add 成功解析2.5.4后因缺当时的main.rs失败；已由实际宿主首个注册插件。
   全平台fetch中止后同锁Windows fetch通过，中间offline tree失败保留；详见INSTALLATION-REPORT。
2. 新smoke stub首轮返回Transport。原始connection-events显示Winsock10035；对accepted socket
   显式set_nonblocking(false)后，10个头/status场景和全量22测试通过。首轮完整失败输出
   host-tests-development-output.txt与stub-10035-original-connection-events.jsonl保留。
   仅解释这次有日志的10035；不据此倒推旧exit code=70原因。
3. Vite最初窗口空白，本机GET超时；缩窄entries并排除.venv/.cargo-home/.npm-cache/
   .toolchains/artifacts/src-tauri/build监听后恢复。强制冷缓存复测扫描14.95ms、bundle111.24ms，
   GET200且窗口/真实invoke通过。先前扫描9058.38ms、bundle43371.47ms原文保留；
   这是配置调整前后的实测，不把无单变量隔离的观察写成唯一内部根因证明。
4. 首轮stage脚本完成复制却因报告父目录不存在失败，补建报告目录后重跑544文件通过；
   失败输出canonical-staging-output.txt保留，成功报告独立文件未覆盖。
5. PowerShell吞掉脚本边界的--，首次help返回npm帮助；frontend.ps1补npm转发delimiter后
   实际tauri dev --help正确。入口热更新曾报重复createRoot，拆App.tsx与main.tsx后最终
   冷缓存运行未再见此警告。对应所有原始输出保留。
6. UI工具一次报告coordinate input geometry is unavailable；没有将该次发送当成功。
   重新选择/激活窗口后重试与最终冒烟成功；初次Failed抓取发生a11y/截图更新间隙，
   原文件保留，判定使用settled文件和原始日志。
7. WebView2正常关窗时原生stderr多次出现
   “[ERROR:ui\gfx\win\window_impl.cc:172] Failed to unregister class Chrome_WidgetWin_0. Error = 1412”。
   本轮原因未定位；退出码0与PID/端口消失已分别核验，不将其解释为引擎code=70。
8. 收尾旧产物只读核对首轮直接比较WindowsPath枚举list触发AssertionError；按相对路径键
   逐项比较后544文件0差异。未修改旧产物或旧manifest来迁就顺序。

第2步新引擎重冻开发期的中文路径/ZIP顺序两次拦截及修复单独记录在日期REVISION中，
原文保留。新旧manifest的字节与代码来源没有合并。DEBUG二进制在UI运行时未采集SHA，
随后cargo test可能重建该文件；不将当前debug文件冒作最终release绑定证明。

## 下一步打算

在此检查点停止，等负责人复核后再进入最终release验收：FaultFixture/Canonical两种暂存、
实际资源解析、两exe manifest提取与SHA、长等待/激活/三段计时、DOM/localStorage审计及
各10轮关闭/强杀矩阵。尚未执行NSIS打包或VM实机项，未新增未经批准的依赖。
