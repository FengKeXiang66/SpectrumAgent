# 第 3 步检查点 1：Rust 监督器与测试（2026-10-18）

## 完成到哪一步

完成 EngineSupervisor 核心、Win32 生产实现与可注入替身、严格握手解析、四态/代次保护、只读日志归属和确定性子进程 stub。本检查点仅验证 Rust 库与测试进程，尚未接真实冻结引擎，尚无 Tauri 宿主/React 页面；本报告不作为 release 外壳验收结论。

第 2 步项 1/3/4/5/7 引用原有结果，未重跑或改写旧输出。按负责人本轮授权进入第 3 步，第 2 步仍保留“待实机验证”及未正式关闭状态。执行依据和已有提交索引见 ../preflight/HANDOFF.md。

本检查点最终依据为 acceptance-native-fixed-output.txt 与 verification-receipt-fixed.json；最初的 transcript/18 项结论属于中间态，保留但不作为最终依据。Ready 后退出另复跑 10 轮全部通过，完整输出在 ready-exit-repeat-output.txt。

本检查点结果：fmt --check 通过；clippy 全目标/全功能且 -D warnings 通过；19 项测试通过（日志归属 2、契约/状态 6、原生子进程 stub 8、注入清理 3）。测试后按完整路径查询 supervisor-stub.exe，残留 0。

首次 src-tauri 提交包含 Cargo.lock。直接依赖为获批准的 5 项，lock 含 103 个第三方包及项目本身（metadata 共 104）；transitive 不是额外手动选型。Cargo.lock=25,117 字节，SHA256=24a4beb3d9a41b6b483da938dc00d28ebd04c7fa2208d0626e863104b07dc51d。

## 命令与原始输出

实际生效路径：CARGO_HOME=E:\AI_Agent\.cargo-home；CARGO_TARGET_DIR=E:\AI_Agent\src-tauri\target。cargo metadata 的 target_directory 与之相同。TEMP/TMP 也显式落 E:\AI_Agent\artifacts\step3\checkpoint-1\temp。只读探针确认默认 C:\Users\Administrator\.cargo\registry 不存在。

已按负责人批准执行的下载命令与首次输出保存在 fetch-output.txt；完整依赖树为 cargo-tree.txt。reqwest 实际功能仅 blocking/json，无默认 TLS；源码唯一请求入口固定为 127.0.0.1 的 /health，无代理、无重定向，没有 /smoke 或外网请求。

本次正式检查的完整命令：

```powershell
$env:CARGO_HOME = 'E:\AI_Agent\.cargo-home'
$env:CARGO_TARGET_DIR = 'E:\AI_Agent\src-tauri\target'
$env:TEMP = 'E:\AI_Agent\artifacts\step3\checkpoint-1\temp'
$env:TMP = $env:TEMP
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' fmt --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --check
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' clippy --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --all-targets --all-features --locked --offline -- -D warnings
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' test --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --all-features --locked --offline -- --nocapture --test-threads=1
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' tree --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --all-features --locked --offline
```

以下完整粘贴 acceptance-native-fixed-output.txt，已用显式 2>&1 | Tee-Object 捕获原生 stdout/stderr。旧 Start-Transcript 文件保留为执行元数据，不能作为完整 cargo 输出。

```text
CARGO_HOME=E:\AI_Agent\.cargo-home CARGO_TARGET_DIR=E:\AI_Agent\src-tauri\target TEMP=E:\AI_Agent\artifacts\step3\checkpoint-1\temp
COMMAND: C:\Users\Administrator\.cargo\bin\cargo.exe fmt --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --check
EXIT_CODE: 0
COMMAND: C:\Users\Administrator\.cargo\bin\cargo.exe clippy --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --all-targets --all-features --locked --offline -- -D warnings
    Checking spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.28s
EXIT_CODE: 0
COMMAND: C:\Users\Administrator\.cargo\bin\cargo.exe test --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --all-features --locked --offline -- --nocapture --test-threads=1
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.96s
     Running unittests src\lib.rs (src-tauri\target\debug\deps\spectrum_agent-b6001364c889b023.exe)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src\bin\supervisor_stub.rs (src-tauri\target\debug\deps\supervisor_stub-adcb0492630f654f.exe)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\causality.rs (src-tauri\target\debug\deps\causality-f2e3024024108ae0.exe)

running 2 tests
test midnight_files_and_preexisting_partial_line_are_handled_without_fallback ... CAUSALITY pure function: launch/exit day files tracked, existing partial line excluded, no engine_boot/boot_id PID fallback
ok
test only_new_complete_lines_with_own_integer_pid_in_utc_window_can_be_cause ... CAUSALITY pure function: old/missing/wrong/noninteger PID, wrong logger/event/code, out-of-window, partial JSON excluded; own new complete line accepted
ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.02s

     Running tests\contracts.rs (src-tauri\target\debug\deps\contracts-e5d78a5d06b21f39.exe)

running 6 tests
test all_transition_pairs_and_stopping_terminal_rule ... ok
test exact_fields_and_top_level_are_enforced ... ok
test late_generation_and_expected_exit_cannot_fail_current_attempt ... ok
test metadata_types_bounds_and_exact_strings_are_enforced ... ok
test times_reject_nonexistent_dates_leap_seconds_and_non_millisecond_formats ... ok
test valid_handshake_values_and_integer_utc_comparison ... ok

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\supervisor_stubs.rs (src-tauri\target\debug\deps\supervisor_stubs-4547224912d4d370.exe)

running 8 tests
test absent_executable_immediately_fails_and_does_not_clean_invalid_old_handshake ... MISSING PATH (constructor injection): kind=SpawnFailed elapsed_ms=11 preexisting_handshake_invalid=retained bytes_unchanged=true
ok
test retry_waits_for_cleanup_and_late_a_exit_cannot_change_b ... STUB retry: A_generation=1 B_generation=2 late_A_exit=discarded B=Ready
ok
test stub_alive_without_handshake_times_out_after_actual_30_seconds ... STUB no-handshake: pid=Some(21524) kind=StartupTimeout elapsed_ms=30074 pending_activation=true
ok
test stub_exit_after_ready_produces_exactly_one_failure_transition ... STUB ready-exit: pid=Some(22288) Ready->Failed(EngineExitedAfterReady) count=1
ok
test stub_immediate_exit_reports_actual_exit_code ... STUB immediate-exit: pid=Some(22232) code=23 kind=ExitedBeforeReady elapsed_ms=52
ok
test stub_ready_then_stop_has_no_listening_port_and_separate_app_exit ... STUB ready/stop: pid=Some(16080) port=56215 phase=Stopping port_absent=true app_exit=1 token_leaks=0
ok
test stub_tolerates_disconnected_health_client ... STUB transport: client disconnected without a request; stub remains Ready
ok
test stub_wrong_health_boot_id_fails_only_after_child_identity_validation ... STUB mismatch: pid=Some(22444) child_pid_and_created_at=verified failure_layer=health_boot_id kind=HealthIdentityMismatch
ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 33.36s

     Running tests\win32_failures.rs (src-tauri\target\debug\deps\win32_failures-86c2aafe833154ce.exe)

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

test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.06s

   Doc-tests spectrum_agent

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

EXIT_CODE: 0
COMMAND: C:\Users\Administrator\.cargo\bin\cargo.exe tree --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --all-features --locked --offline --edges features -i reqwest
reqwest v0.13.5
├── reqwest feature "blocking"
│   └── spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
│       ├── spectrum-agent feature "default" (command-line)
│       └── spectrum-agent feature "test-probes" (command-line)
└── reqwest feature "json"
    └── spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri) (*)
EXIT_CODE: 0
COMMAND: C:\Users\Administrator\.cargo\bin\cargo.exe fetch --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --locked --offline
EXIT_CODE: 0

```

实际依赖树全文（cargo-tree.txt）：

```text
spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
├── chrono v0.4.45
│   ├── num-traits v0.2.19
│   │   [build-dependencies]
│   │   └── autocfg v1.5.1
│   └── windows-link v0.2.1
├── reqwest v0.13.5
│   ├── base64 v0.23.1
│   ├── bytes v1.12.1
│   ├── futures-channel v0.3.34
│   │   ├── futures-core v0.3.34
│   │   └── futures-sink v0.3.34
│   ├── futures-core v0.3.34
│   ├── futures-util v0.3.34
│   │   ├── futures-core v0.3.34
│   │   ├── futures-io v0.3.34
│   │   ├── futures-sink v0.3.34
│   │   ├── futures-task v0.3.34
│   │   ├── memchr v2.8.3
│   │   ├── pin-project-lite v0.2.17
│   │   └── slab v0.4.12
│   ├── http v1.5.0
│   │   ├── bytes v1.12.1
│   │   └── itoa v1.0.18
│   ├── http-body v1.1.0
│   │   ├── bytes v1.12.1
│   │   └── http v1.5.0 (*)
│   ├── http-body-util v0.1.5
│   │   ├── bytes v1.12.1
│   │   ├── futures-core v0.3.34
│   │   ├── http v1.5.0 (*)
│   │   ├── http-body v1.1.0 (*)
│   │   └── pin-project-lite v0.2.17
│   ├── hyper v1.12.0
│   │   ├── atomic-waker v1.1.2
│   │   ├── bytes v1.12.1
│   │   ├── futures-core v0.3.34
│   │   ├── http v1.5.0 (*)
│   │   ├── http-body v1.1.0 (*)
│   │   ├── httparse v1.10.1
│   │   ├── itoa v1.0.18
│   │   ├── pin-project-lite v0.2.17
│   │   ├── smallvec v1.16.3
│   │   ├── tokio v1.53.3
│   │   │   ├── mio v1.2.4
│   │   │   │   └── windows-sys v0.61.2
│   │   │   │       └── windows-link v0.2.1
│   │   │   ├── pin-project-lite v0.2.17
│   │   │   ├── socket2 v0.6.5
│   │   │   │   └── windows-sys v0.61.2 (*)
│   │   │   └── windows-sys v0.61.2 (*)
│   │   └── want v0.3.2
│   │       └── try-lock v0.2.5
│   ├── hyper-util v0.1.21
│   │   ├── base64 v0.23.1
│   │   ├── bytes v1.12.1
│   │   ├── futures-channel v0.3.34 (*)
│   │   ├── futures-util v0.3.34 (*)
│   │   ├── http v1.5.0 (*)
│   │   ├── http-body v1.1.0 (*)
│   │   ├── httparse v1.10.1
│   │   ├── hyper v1.12.0 (*)
│   │   ├── ipnet v2.12.2
│   │   ├── libc v0.2.191
│   │   ├── percent-encoding v2.3.2
│   │   ├── pin-project-lite v0.2.17
│   │   ├── socket2 v0.6.5 (*)
│   │   ├── tokio v1.53.3 (*)
│   │   ├── tower-service v0.3.3
│   │   └── tracing v0.1.44
│   │       ├── pin-project-lite v0.2.17
│   │       └── tracing-core v0.1.36
│   │           └── once_cell v1.21.4
│   ├── log v0.4.34
│   ├── percent-encoding v2.3.2
│   ├── pin-project-lite v0.2.17
│   ├── serde v1.0.229
│   │   ├── serde_core v1.0.229
│   │   └── serde_derive v1.0.229 (proc-macro)
│   │       ├── proc-macro2 v1.0.107
│   │       │   └── unicode-ident v1.0.27
│   │       ├── quote v1.0.47
│   │       │   └── proc-macro2 v1.0.107 (*)
│   │       └── syn v3.0.9
│   │           ├── proc-macro2 v1.0.107 (*)
│   │           ├── quote v1.0.47 (*)
│   │           └── unicode-ident v1.0.27
│   ├── serde_json v1.0.154
│   │   ├── itoa v1.0.18
│   │   ├── memchr v2.8.3
│   │   ├── serde_core v1.0.229
│   │   └── zmij v1.0.23
│   ├── sync_wrapper v1.0.2
│   │   └── futures-core v0.3.34
│   ├── tokio v1.53.3 (*)
│   ├── tower v0.5.3
│   │   ├── futures-core v0.3.34
│   │   ├── futures-util v0.3.34 (*)
│   │   ├── pin-project-lite v0.2.17
│   │   ├── sync_wrapper v1.0.2 (*)
│   │   ├── tokio v1.53.3 (*)
│   │   ├── tower-layer v0.3.3
│   │   └── tower-service v0.3.3
│   ├── tower-http v0.6.11
│   │   ├── bitflags v2.13.2
│   │   ├── bytes v1.12.1
│   │   ├── futures-util v0.3.34 (*)
│   │   ├── http v1.5.0 (*)
│   │   ├── http-body v1.1.0 (*)
│   │   ├── pin-project-lite v0.2.17
│   │   ├── tower v0.5.3 (*)
│   │   ├── tower-layer v0.3.3
│   │   ├── tower-service v0.3.3
│   │   └── url v2.5.8
│   │       ├── form_urlencoded v1.2.2
│   │       │   └── percent-encoding v2.3.2
│   │       ├── idna v1.1.0
│   │       │   ├── idna_adapter v1.2.2
│   │       │   │   ├── icu_normalizer v2.3.0
│   │       │   │   │   ├── icu_collections v2.3.0
│   │       │   │   │   │   ├── displaydoc v0.2.7 (proc-macro)
│   │       │   │   │   │   │   ├── proc-macro2 v1.0.107 (*)
│   │       │   │   │   │   │   ├── quote v1.0.47 (*)
│   │       │   │   │   │   │   └── syn v3.0.9 (*)
│   │       │   │   │   │   ├── potential_utf v0.1.6
│   │       │   │   │   │   │   └── zerovec v0.11.8
│   │       │   │   │   │   │       ├── yoke v0.8.3
│   │       │   │   │   │   │       │   ├── stable_deref_trait v1.2.1
│   │       │   │   │   │   │       │   ├── yoke-derive v0.8.4 (proc-macro)
│   │       │   │   │   │   │       │   │   ├── proc-macro2 v1.0.107 (*)
│   │       │   │   │   │   │       │   │   ├── quote v1.0.47 (*)
│   │       │   │   │   │   │       │   │   ├── syn v3.0.9 (*)
│   │       │   │   │   │   │       │   │   └── synstructure v0.14.0
│   │       │   │   │   │   │       │   │       ├── proc-macro2 v1.0.107 (*)
│   │       │   │   │   │   │       │   │       ├── quote v1.0.47 (*)
│   │       │   │   │   │   │       │   │       └── syn v3.0.9 (*)
│   │       │   │   │   │   │       │   └── zerofrom v0.1.8
│   │       │   │   │   │   │       │       └── zerofrom-derive v0.1.8 (proc-macro)
│   │       │   │   │   │   │       │           ├── proc-macro2 v1.0.107 (*)
│   │       │   │   │   │   │       │           ├── quote v1.0.47 (*)
│   │       │   │   │   │   │       │           ├── syn v3.0.9 (*)
│   │       │   │   │   │   │       │           └── synstructure v0.14.0 (*)
│   │       │   │   │   │   │       ├── zerofrom v0.1.8 (*)
│   │       │   │   │   │   │       └── zerovec-derive v0.11.6 (proc-macro)
│   │       │   │   │   │   │           ├── proc-macro2 v1.0.107 (*)
│   │       │   │   │   │   │           ├── quote v1.0.47 (*)
│   │       │   │   │   │   │           └── syn v3.0.9 (*)
│   │       │   │   │   │   ├── utf8_iter v1.0.4
│   │       │   │   │   │   ├── yoke v0.8.3 (*)
│   │       │   │   │   │   ├── zerofrom v0.1.8 (*)
│   │       │   │   │   │   └── zerovec v0.11.8 (*)
│   │       │   │   │   ├── icu_normalizer_data v2.3.0
│   │       │   │   │   ├── icu_provider v2.3.1
│   │       │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │       │   │   │   │   ├── icu_locale_core v2.3.0
│   │       │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │       │   │   │   │   │   ├── litemap v0.8.3
│   │       │   │   │   │   │   ├── tinystr v0.8.4
│   │       │   │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │       │   │   │   │   │   │   └── zerovec v0.11.8 (*)
│   │       │   │   │   │   │   ├── writeable v0.6.4
│   │       │   │   │   │   │   └── zerovec v0.11.8 (*)
│   │       │   │   │   │   ├── writeable v0.6.4
│   │       │   │   │   │   ├── yoke v0.8.3 (*)
│   │       │   │   │   │   ├── zerofrom v0.1.8 (*)
│   │       │   │   │   │   ├── zerotrie v0.2.5
│   │       │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │       │   │   │   │   │   ├── yoke v0.8.3 (*)
│   │       │   │   │   │   │   └── zerofrom v0.1.8 (*)
│   │       │   │   │   │   └── zerovec v0.11.8 (*)
│   │       │   │   │   ├── smallvec v1.16.3
│   │       │   │   │   └── zerovec v0.11.8 (*)
│   │       │   │   └── icu_properties v2.3.0
│   │       │   │       ├── displaydoc v0.2.7 (proc-macro) (*)
│   │       │   │       ├── icu_collections v2.3.0 (*)
│   │       │   │       ├── icu_locale_core v2.3.0 (*)
│   │       │   │       ├── icu_properties_data v2.3.0
│   │       │   │       ├── icu_provider v2.3.1 (*)
│   │       │   │       ├── zerotrie v0.2.5 (*)
│   │       │   │       └── zerovec v0.11.8 (*)
│   │       │   ├── smallvec v1.16.3
│   │       │   └── utf8_iter v1.0.4
│   │       └── percent-encoding v2.3.2
│   ├── tower-service v0.3.3
│   └── url v2.5.8 (*)
├── serde v1.0.229 (*)
├── serde_json v1.0.154 (*)
└── windows-sys v0.61.2 (*)

```

可复核文件：verification-receipt-fixed.json 保存 lock、实际 target、直接依赖功能和被测源文件哈希；final-inventory-output.txt 保存残留进程 0、锁哈希与 Step-2 基线 diff 为空。stub 数据/完整握手只在被忽略的 E 盘 target 中，未提交。

原始数据的含义与边界：启动即退的 code=23 来自本次原生 CreateProcessW 子进程；假 health 用例先有 handshake_identity_verified，主因层为 health_boot_id；30 秒计时实际运行完整时长，没有缩短超时假测。重试用例证明 A 清理完后才启动 B，迟到的 A 退出事件被丢弃。Stopping 的退出不计为 EngineExitedAfterReady，app_exit 为独立事件。以上均是 stub/库层证据，不能代替真实引擎、Tauri 事件循环、release 强杀矩阵或 VM 冷启动。

验收项逐条状态（未到的检查点不冒报通过）：

| 编号 | 本检查点结果 |
|---|---|
| 1 | Rust fmt/clippy/test 通过；npm build、tsc、Tauri --no-bundle 未验证 |
| 2a | 5 种确定性原生子进程 stub 行为通过；另加重试、无效路径与断线用例 |
| 2b | 5 种 Win32 启动失败注入通过；成功与失败的实际句柄关闭恰好一次；清理错误阻止重试 |
| 2c | 真实冻结引擎/release 集成未验证 |
| 2d | 纯解析通过所列字段、类型、范围、格式、日历及 token 不泄漏用例 |
| 3 | 仅构造参数注入的无效路径即时 SpawnFailed 已验证；SPECTRUM_ENGINE_EXE 尚未定义，不冒充环境变量验收 |
| 4 | 专用 DLL 副本、release 故障夹具、最终 Canonical 暂存均未实施 |
| 5 | ResumeThread 失败的 TerminateJobObject → Wait → Close 顺序已验证 |
| 6 | A→B 代次竞态与 Stopping 预期退出的库层用例通过 |
| 7 | Tauri 主事件循环 heartbeat/invoke/激活响应未验证；库层测试不能替代 |
| 8 | 窗口尚未实现，未验证 |
| 9 | 单实例插件与激活尚未实现，未验证 |
| 10 | 前端 smoke/对话条/快捷键未实现，未验证 |
| 11 | dev/release 三段计时未验证；VM 冷启动继续延期 |
| 12 | 真实外壳正常关窗 10 轮未验证 |
| 13 | 直接 release 外壳强杀 10 轮未验证 |
| 14 | 真实启动窗口强杀 10 轮未验证 |
| 15 | 真实冻结引擎陈旧握手恢复未验证 |
| 16 | stub 用例中实际 token 原串扫描为 0；真实外壳各轮完整扫描待后续 |
| 17 | 纯状态机覆盖全部允许/禁止迁移，库层退出独立事件已验证；最终外壳完整迁移日志待后续 |
| 18 | resources 忽略规则已加入；资源映射、dev/release 实测未验证 |
| 19 | Python lock 原样保留、本次 Cargo.lock 入库；package-lock 未生成；整体 Git 仍有负责人原有 VM 改动 |
| 20 | 最终两个 EXE manifest 尚未提取；系统策略及 >260 字符实机测试未验证 |

## 遇到的问题

- 首轮 clippy 在工具回传中报 4 处可合并 if 和 1 处大 enum，已修改且未禁用 lint；新增清理错误测试的返回类型遗漏也已修复。最初 Start-Transcript 文件只留了命令/PowerShell 输出，漏了原生 cargo 输出。我先前称其“完整原始输出”不准确；这些文件保留为执行元数据，旧报告中的该表述已更正。最终以显式 2>&1 | Tee-Object 捕获的新文件为准。
- 首次完整采集的复跑出现 ready-exit stub 在 Ready 前 code=70：acceptance-native-output.txt 完整保留。该轮实际为 14 过、1 失败、3 项未运行；此前口头说“17 过、1 失败”不准确，现按 cargo 提前终止的实际记录更正。旧 fixture 没有内部错误落盘，首次 code=70 的具体内部原因仍为“未验证”，不把推测写成结论。
- 随后的确定性断线实验确认旧 stub 收到“连上后不发请求即断开”的连接会退出，修复前 0 过、1 失败的完整输出见 stub-disconnect-before-fix.txt。已修复 fixture 的连接级错误处理、增加错误/连接事件文件，并让 ready-exit 等父进程确认已观察到 Ready 才主动退出。没有修改监督器代码。修复后全量 19 过、0 失败，额外 10 轮 ready-exit 全过；这些结果不替代 release 强杀矩阵，也不倒推首次 code=70 的具体原因。
- VM 只读现状：Hyper-V=Enabled、vmms=Running，pristine ID 匹配；但 vCPU=10、动态内存 512MB–1TB、TPM=False，与负责人描述不同。完整原文见 ../preflight/environment-current-output.txt；未改 VM，未重做 Copy-VMFile，不把负责人提供的双侧 SHA 当作本次独立验证。
- 当前 PATH Node/npm 为 20.18.0/10.8.2，另有应用自带 Node 24.19.0。本检查点尚未选择或安装前端工具链，后续会先明确兼容版本与安装清单。
- 负责人已有四项未提交 VM 文件变更保留原样，不混入本次 src-tauri 提交。因此不能宣称整个工作区干净；本检查点不作第 3 步最终关闭验收。

## 下一步打算

停在检查点 1 等负责人确认；确认后接真实冻结 onedir 引擎及其失败场景，随后再按顺序进入 Tauri/React，新增依赖另列清单确认。