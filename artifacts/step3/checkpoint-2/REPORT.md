## 完成到哪一步

第 3 步检查点 2：Rust 监督器已接入封版冻结 onedir 引擎，完成真实启动、身份校验、失败分类、陈旧握手恢复及 Ready 后退出联调；停在本检查点等待负责人复核。

基线 HEAD 为负责人提交的 9312a96。未修改 backend、Step-2 spec、两份依赖锁或 Step-2 STATUS/REPORT；第 2 步继续保持“待实机验证”。没有安装 npm 包，没有新增 Rust/Python 依赖，没有实现 Tauri 窗口、单实例插件、React 或安装包。

新增 engine_path 模块：构造注入优先；debug 构建读取 SPECTRUM_ENGINE_EXE；release 编译分支不读该变量，资源解析由后续 Tauri host 提供。路径形状校验拒绝相对路径及非 app.exe；不存在的绝对 app.exe 由原生启动路径立即报 SpawnFailed。测试入口 supervisor-probe 受 test-probes feature 控制，不是产品外壳。其 --resource-exe 是测试参数，不能冒充 Tauri Resource resolver 的验收证据。

监督器额外记录非敏感旧身份和本次 GetProcessTimes 创建时间，未改变握手/health 字段、因果规则、句柄继承参数或 Job 顺序。reqwest 仍只访问字面量 127.0.0.1 的 /health；smoke 由验收控制器调用系统 curl，token 经 stdin 配置传递，不进入命令行。

## 命令与原始输出

最终依据目录：evidence-20261018-160306-056134/。其中 raw-output.txt 为完整控制器输出，各 curl.txt 为完整返回体，launch.json 保存命令及启动前 EOF，events.jsonl 保存无 token 状态，engine/shell 日志副本保留原始换行。握手副本只脱敏 token，其余字段完整。原始日志与 16 个 final 归档片段已逐字节比对一致，独立审计的闭合偏移与 SHA256 可复核。

独立入口（PowerShell，默认使用现有 lock 离线构建 debug/release probe 后运行）：

```powershell
& E:\AI_Agent\artifacts\step3\checkpoint-2\selfcheck_checkpoint2.ps1
```

本轮最终运行命令（两份 probe 已构建，故跳过重复编译）：

```powershell
& E:\AI_Agent\artifacts\step3\checkpoint-2\selfcheck_checkpoint2.ps1 -SkipBuild
```

脚本显式设置 CARGO_HOME=E:\AI_Agent\.cargo-home、CARGO_TARGET_DIR=E:\AI_Agent\src-tauri\target、TEMP/TMP=E:\AI_Agent\artifacts\step3\checkpoint-2\temp，Python 固定为 E:\AI_Agent\.venv\Scripts\python.exe。控制器 shell=False 启动 Rust probe，再由原生 CreateProcessW 挂起创建 app.exe；不以 Python 启动引擎。

最终轮结果与证据含义：

| 场景 | 实测 | 判读与边界 |
|---|---|---|
| dev 真引擎 | probe PID=19856；app PID=22124；父 PID=19856；tasklist 仅 1 个 app.exe；boot_id=ca80b7eb；port=57854 | 握手 PID、GetProcessTimes UTC 毫秒 1792310586367、health 身份均匹配 |
| 真 HTTP | health 200、无 token 401、smoke 200、blocks=8 200 | 全部完整 JSON 见下面原始输出及分项 curl.txt |
| 无效 dev 路径 | 34.314ms，SpawnFailed，CreateProcessW code=2，pid=null | 立即失败，没有等 30 秒，没有子进程 |
| 注入优先级 | 无效 dev env + 构造参数正式 app.exe → Ready | 测试注入优先于 dev env |
| release 编译分支 | debug_assertions=false，无效 dev env，resolved_resource → Ready | 只证明库层 release 不读变量；Tauri 布局和最终外壳 release 未验证 |
| 非法 JSON | PID=512，code=1，HandshakeInvalid/HANDSHAKE_INVALID_JSON | 本代新增完整 handshake_error 自带 PID/boot_id；原字节 SHA 未变；重试 generation=2、PID=12420，仍拒绝且不改原字节 |
| 缺字段 | PID=1448，code=1，HandshakeInvalid/HANDSHAKE_INVALID_FIELDS | 同样由本代新增引擎行归因，原字节未变 |
| 缺 DLL + 非法旧握手 | PID=4768，code=4294967295，ExitedBeforeReady，preexisting=InvalidJson，engine_error=null | Python 未运行，无新增 engine 日志；不被非法旧握手抢主因。故障副本只有 _internal/python312.dll 缺失，其他 543 文件精确一致 |
| 陈旧握手恢复 | old 22124/ca80b7eb/57854 → new 17472/b11fe604/57875；旧端口假 health 的调用增量=0 | 不清洗旧握手直接再启，只有引擎执行 stale_handshake_removed；新 PID/创建时间/boot 校验后 Ready |
| Ready 后意外退出 | app PID=16416，taskkill /F 后 code=1，EngineExitedAfterReady | 恰好一次 Ready→Failed，清理完成，probe 随后停止；不是 release 外壳强杀矩阵 |
| 正常停止验收入口 | 所有本轮 app PID 已退、端口已关；Job 硬终止后握手残留 | 原始残留先存档。之后验收工具删除仅为测试卫生，不作为引擎自动清理或通过依据 |
| 来源完整性 | 正式树前后 544 文件、255,564,460 字节，逐文件路径/字节/SHA256 与既有 product-manifest 一致 | 没有重新颁发清单，没有改正式冻结产物 |
| 日志 | 最终原始增量 engine=75 行、shell=145 行，全合法 JSON；5 个实际 token 原串命中 0，日志 token 键 0，辅助 32hex 命中 0 | 先扫未脱敏原始日志，再扫归档；receipt 只留 token SHA256 供核验，不保存明文 |
| 时延 | app 实际创建→Ready 616ms；probe 启动→观察 Ready 627.110ms；缺 DLL 实际创建→Failed 42ms，probe→Failed 85.708ms | 前一口径由 GetProcessTimes 与迁移日志 UTC 毫秒计算，后一口径是控制器单调时钟。均为宿主机组件计时，不能代替 VM 冷启动或 UI 三段计时 |

正常停止 probe 的实现使用现有监督器 TerminateJobObject 路径，不是模拟 Ctrl+C；握手残留如实留证。missing-dll-standalone-control.txt 的 bootloader 报错来自另一次独立对照启动，不声称它是监督器原次启动的 stderr。原次因果证据是 CreateProcessW PID、真实 exit code、无新增 engine 行和未变的旧握手。Rust 没有为取 stderr 改句柄继承方式。

Rust 回归：cargo fmt --check exit=0（无控制台输出）；clippy exit=0、无 warning；cargo test exit=0，共 20 passed/0 failed（2 causality + 6 contracts + 1 engine_path + 8 stubs + 3 Win32）。30 秒超时用例实际耗时 30021ms，未缩短超时；完整输出附后。

VM 只读现状：Win11 Running/Gen2、4 vCPU、动态内存 4294967296–10737418240、启动 8589934592、TPM=True、vmms Running；pristine=f7ea81cf-6c3a-4823-9a7b-5fe77f4c2300，2026-10-18 15:41:03。没有执行 VM 修改、restore、安装或 Copy-VMFile。VM 配置以本次只读结果为准。restore 恢复验证、三段冷启动和断网安装仍待第 4 步 setup.exe。

20 项验收状态逐条更新（本表不是第 3 步最终验收）：

| 编号 | 当前状态 |
|---|---|
| 1 | Rust fmt/clippy/20 测试通过；npm build、tsc、Tauri --no-bundle 未验证 |
| 2a | 五种确定性 stub 及既有额外用例复跑通过 |
| 2b | 五种 Win32 失败注入、句柄次数/顺序、清理错误阻止重试复跑通过 |
| 2c | 本文真实冻结引擎组件联调通过；最终 Tauri release 集成、release 故障暂存与关窗/强杀矩阵未验证 |
| 2d | 纯解析严格字段/类型/范围/日历等既有测试复跑通过 |
| 3 | dev 环境变量无效 app.exe 立即 SpawnFailed，34.314ms，code=2；最终 UI 错误展示未验证 |
| 4 | 测试副本精确缺 python312.dll、主因与原始报错已验证；正式 release FaultFixture/Canonical 暂存未实现 |
| 5 | ResumeThread 注入失败的 TerminateJobObject→Wait→Close 顺序复跑通过 |
| 6 | 库层 A→B 代次保护/Stopping 测试复跑通过；真实非法握手重试已验证；最终外壳迟到事件场景未验证 |
| 7 | Tauri 主循环 heartbeat/invoke/激活响应未验证 |
| 8 | 四态窗口/失败页未实现，未验证 |
| 9 | 单实例插件/激活未实现，未验证 |
| 10 | 前端 smoke/常驻对话条/快捷键未实现，未验证 |
| 11 | 只采集本文宿主机组件计时；dev/release UI 三段、VM 冷启动未验证 |
| 12 | 真实外壳正常关窗 10 轮未验证 |
| 13 | 直接 release 外壳强杀 10 轮未验证 |
| 14 | 启动窗口强杀 10 轮未验证 |
| 15 | 真实冻结引擎陈旧握手恢复与旧端口隔离通过；最终 release 外壳轮次未验证 |
| 16 | 本轮未脱敏原始 engine/shell 日志、归档证据实际 token 扫描 0；未来 Tauri/UI 各轮待验 |
| 17 | 库层迁移/独立 app_exit 验证通过；本轮完整迁移序列附后；最终外壳全部迁移待验 |
| 18 | dev 成功和库层 release 忽略 env 已验证；Tauri resolve(Resource)、配置相对映射与 --no-bundle 布局未验证 |
| 19 | Python/Cargo lock 未变；package-lock 尚未生成。按里程碑提交本检查点，最终 Git 状态另有原始输出 |
| 20 | 最终两个 EXE RT_MANIFEST、系统 LongPathsEnabled 及长路径实机验收未验证 |

## 遇到的问题

1. 首次自检在启动前报 canonical differs：只是 Python Windows Path 排序与既有 PowerShell 清单排序不同。只读复核 544 对 544、missing/extra/changed 全空，现按统一相对路径顺序比较；没改旧 manifest。失败原文在 evidence-20261018-155624-671746/FAILURE.txt，只读复核在 canonical-readonly-difference-output.txt。
2. 第一轮控制台中文编码不一致、早期文本归档又将日志 CRLF 二次转换；前两轮只扫描脱敏副本也不足以证明原始日志无 token。旧输出一律保留为中间记录，未回头修饰。最终入口显式 UTF-8、保存文本禁二次换行转换，先扫原始增量再脱敏；最终 16 个日志片段逐字节回比原文件成功。前三个完成轮次的旧 receipt 不作为最终原始字节/token 证明。
3. 独立字节审计的首个临时命令遗漏 read_text(encoding='utf-8')，按系统 GBK 读 UTF-8 receipt 报 UnicodeDecodeError；失败输出在 original-log-audit-output.txt。正式 audit_evidence.py 已显式 UTF-8，修复输出在 original-log-audit-fixed-output.txt。它是审计工具错误，不是引擎退出。
4. 缺 DLL 的 stderr 第一行明确指出 Failed to load Python DLL 及缺失路径；第二行实际字节就是 LoadLibrary: ?????????。原字节另以 base64 保存，不猜补系统中文，也不替换 bootloader 文本。后续失败页按枚举提供中文原因。
5. 首次 stub code=70 的具体内部原因仍“未验证”。本轮真实引擎未出现 70；验收入口一旦观察到 70，会先保存本代内部日志和状态，然后终止验收。未用本轮通过倒推旧错误原因。

目前本检查点无阻塞；Tauri/UI 与最终 release 验收尚未开展，不能写整个第 3 步通过。第 2 步 VM 验证继续开放。

## 下一步打算

按负责人检查点纪律停在这里等确认；确认后先给出 Node/前端/Tauri 工具链的精确版本方案和安装清单，获得安装授权后再进入四态 UI、失败页和常驻对话条。

以下附本轮命令对应的完整原始输出，未用省略号删节；更早输出作为历史保留，不替换最终依据。


**fmt 原始输出（无输出；退出码原始元数据见下一块）**

```powershell
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' fmt --manifest-path src-tauri/Cargo.toml --check
```

```text

```


**fmt 执行元数据**

```powershell
Get-Content fmt-final-execution.json
```

```json
{
  "command": "cargo fmt --manifest-path src-tauri/Cargo.toml --check",
  "exit_code": 0,
  "stdout_stderr_lines": 0
}

```


**clippy 原始输出**

```powershell
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' clippy --manifest-path src-tauri/Cargo.toml --locked --offline --all-targets --all-features -- -D warnings
```

```text
    Checking spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.73s

```


**全量测试原始输出**

```powershell
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' test --manifest-path src-tauri/Cargo.toml --locked --offline --all-features -- --nocapture --test-threads=1
```

```text
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `test` profile [unoptimized + debuginfo] target(s) in 1.35s
     Running unittests src\lib.rs (src-tauri\target\debug\deps\spectrum_agent-b6001364c889b023.exe)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src\bin\supervisor_probe.rs (src-tauri\target\debug\deps\supervisor_probe-99a06473056d9845.exe)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src\bin\supervisor_stub.rs (src-tauri\target\debug\deps\supervisor_stub-adcb0492630f654f.exe)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\causality.rs (src-tauri\target\debug\deps\causality-92351f73b8debeee.exe)

running 2 tests
test midnight_files_and_preexisting_partial_line_are_handled_without_fallback ... CAUSALITY pure function: launch/exit day files tracked, existing partial line excluded, no engine_boot/boot_id PID fallback
ok
test only_new_complete_lines_with_own_integer_pid_in_utc_window_can_be_cause ... CAUSALITY pure function: old/missing/wrong/noninteger PID, wrong logger/event/code, out-of-window, partial JSON excluded; own new complete line accepted
ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.04s

     Running tests\contracts.rs (src-tauri\target\debug\deps\contracts-1bfdca8146014ed7.exe)

running 6 tests
test all_transition_pairs_and_stopping_terminal_rule ... ok
test exact_fields_and_top_level_are_enforced ... ok
test late_generation_and_expected_exit_cannot_fail_current_attempt ... ok
test metadata_types_bounds_and_exact_strings_are_enforced ... ok
test times_reject_nonexistent_dates_leap_seconds_and_non_millisecond_formats ... ok
test valid_handshake_values_and_integer_utc_comparison ... ok

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\engine_path.rs (src-tauri\target\debug\deps\engine_path-b00a1ca240c9cc93.exe)

running 1 test
test constructor_precedes_resource_and_rejects_non_engine_or_relative_paths ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests\supervisor_stubs.rs (src-tauri\target\debug\deps\supervisor_stubs-f1904bb8bb35a89b.exe)

running 8 tests
test absent_executable_immediately_fails_and_does_not_clean_invalid_old_handshake ... MISSING PATH (constructor injection): kind=SpawnFailed elapsed_ms=11 preexisting_handshake_invalid=retained bytes_unchanged=true
ok
test retry_waits_for_cleanup_and_late_a_exit_cannot_change_b ... STUB retry: A_generation=1 B_generation=2 late_A_exit=discarded B=Ready
ok
test stub_alive_without_handshake_times_out_after_actual_30_seconds ... STUB no-handshake: pid=Some(20820) kind=StartupTimeout elapsed_ms=30021 pending_activation=true
ok
test stub_exit_after_ready_produces_exactly_one_failure_transition ... STUB ready-exit: pid=Some(14840) Ready->Failed(EngineExitedAfterReady) count=1
ok
test stub_immediate_exit_reports_actual_exit_code ... STUB immediate-exit: pid=Some(21460) code=23 kind=ExitedBeforeReady elapsed_ms=52
ok
test stub_ready_then_stop_has_no_listening_port_and_separate_app_exit ... STUB ready/stop: pid=Some(6092) port=52917 phase=Stopping port_absent=true app_exit=1 token_leaks=0
ok
test stub_tolerates_disconnected_health_client ... STUB transport: client disconnected without a request; stub remains Ready
ok
test stub_wrong_health_boot_id_fails_only_after_child_identity_validation ... STUB mismatch: pid=Some(11344) child_pid_and_created_at=verified failure_layer=health_boot_id kind=HealthIdentityMismatch
ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 33.17s

     Running tests\win32_failures.rs (src-tauri\target\debug\deps\win32_failures-f2ce3570b7458402.exe)

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


```


**debug 构建原始输出**

```powershell
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' build --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --locked --offline --features test-probes --bin supervisor-probe
```

```text
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.08s

```


**release 构建原始输出**

```powershell
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' build --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --locked --offline --features test-probes --bin supervisor-probe --release
```

```text
   Compiling proc-macro2 v1.0.107
   Compiling unicode-ident v1.0.27
   Compiling quote v1.0.47
   Compiling stable_deref_trait v1.2.1
   Compiling windows-link v0.2.1
   Compiling pin-project-lite v0.2.17
   Compiling writeable v0.6.4
   Compiling litemap v0.8.3
   Compiling futures-core v0.3.34
   Compiling itoa v1.0.18
   Compiling icu_properties_data v2.3.0
   Compiling smallvec v1.16.3
   Compiling icu_normalizer_data v2.3.0
   Compiling utf8_iter v1.0.4
   Compiling bytes v1.12.1
   Compiling futures-sink v0.3.34
   Compiling memchr v2.8.3
   Compiling serde_core v1.0.229
   Compiling slab v0.4.12
   Compiling futures-task v0.3.34
   Compiling windows-sys v0.61.2
   Compiling futures-io v0.3.34
   Compiling percent-encoding v2.3.2
   Compiling httparse v1.10.1
   Compiling once_cell v1.21.4
   Compiling tower-service v0.3.3
   Compiling libc v0.2.191
   Compiling zmij v1.0.23
   Compiling autocfg v1.5.1
   Compiling try-lock v0.2.5
   Compiling form_urlencoded v1.2.2
   Compiling tracing-core v0.1.36
   Compiling sync_wrapper v1.0.2
   Compiling atomic-waker v1.1.2
   Compiling serde_json v1.0.154
   Compiling want v0.3.2
   Compiling tower-layer v0.3.3
   Compiling serde v1.0.229
   Compiling futures-channel v0.3.34
   Compiling bitflags v2.13.2
   Compiling base64 v0.23.1
   Compiling ipnet v2.12.2
   Compiling log v0.4.34
   Compiling futures-util v0.3.34
   Compiling http v1.5.0
   Compiling num-traits v0.2.19
   Compiling tracing v0.1.44
   Compiling syn v3.0.9
   Compiling http-body v1.1.0
   Compiling http-body-util v0.1.5
   Compiling chrono v0.4.45
   Compiling socket2 v0.6.5
   Compiling mio v1.2.4
   Compiling tokio v1.53.3
   Compiling synstructure v0.14.0
   Compiling zerofrom-derive v0.1.8
   Compiling yoke-derive v0.8.4
   Compiling zerovec-derive v0.11.6
   Compiling displaydoc v0.2.7
   Compiling serde_derive v1.0.229
   Compiling zerofrom v0.1.8
   Compiling yoke v0.8.3
   Compiling zerotrie v0.2.5
   Compiling zerovec v0.11.8
   Compiling tinystr v0.8.4
   Compiling potential_utf v0.1.6
   Compiling icu_collections v2.3.0
   Compiling icu_locale_core v2.3.0
   Compiling hyper v1.12.0
   Compiling tower v0.5.3
   Compiling icu_provider v2.3.1
   Compiling icu_normalizer v2.3.0
   Compiling icu_properties v2.3.0
   Compiling hyper-util v0.1.21
   Compiling idna_adapter v1.2.2
   Compiling idna v1.1.0
   Compiling url v2.5.8
   Compiling tower-http v0.6.11
   Compiling reqwest v0.13.5
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `release` profile [optimized] target(s) in 12.72s

```


**最终真实引擎联调完整输出**

```powershell
& E:\AI_Agent\artifacts\step3\checkpoint-2\selfcheck_checkpoint2.ps1 -SkipBuild
```

```text
输出目录=E:\AI_Agent\artifacts\step3\checkpoint-2\evidence-20261018-160306-056134
python=E:\AI_Agent\.venv\Scripts\python.exe
CARGO_HOME=E:\AI_Agent\.cargo-home
CARGO_TARGET_DIR=E:\AI_Agent\src-tauri\target

[dev-ready] command=E:\AI_Agent\src-tauri\target\debug\supervisor-probe.exe --resource-exe E:\AI_Agent\artifacts\step2\dist\app\app.exe
SPECTRUM_ENGINE_EXE=E:\AI_Agent\artifacts\step2\dist\app\app.exe probe_pid=19856
{"elapsed_ms": 627.11, "snapshot": {"generation_id": 1, "phase": "Ready", "pid": 22124, "port": 57854, "boot_id": "ca80b7eb", "failure": null, "cleanup_complete": false, "pending_activation": false}}
Get-CimInstance:
{"ProcessId":22124,"ParentProcessId":19856,"ExecutablePath":"E:\\AI_Agent\\artifacts\\step2\\dist\\app\\app.exe"}


Image Name                     PID Session Name        Session#    Mem Usage
========================= ======== ================ =========== ============
app.exe                      22124 Console                    1     77,200 K

GetProcessTimes UTC ms=1792310586367; handshake UTC ms=1792310586367; pid/boot/created_at=matched
curl.exe /health auth=False (token 经 stdin 配置传入)
{"status":"ok","boot_id":"ca80b7eb","pid":22124,"version":"0.1.0","uptime_s":0.609}
HTTP_STATUS=200

curl.exe /smoke auth=False (token 经 stdin 配置传入)
{"error":"UNAUTHORIZED","detail":"需要本次引擎握手中的 Bearer token。"}
HTTP_STATUS=401

curl.exe /smoke auth=True (token 经 stdin 配置传入)
{"nan_ratio":0.0,"reflectance_range":[-1.5275289241381491,1.5275289241381491],"bands":8,"shape":[8,8,8],"elapsed_ms":155.512}
HTTP_STATUS=200

curl.exe /smoke?blocks=8 auth=True (token 经 stdin 配置传入)
{"nan_ratio":0.0,"reflectance_range":[-1.5275289241381491,1.5275289241381491],"bands":8,"shape":[8,8,8],"elapsed_ms":195.745}
HTTP_STATUS=200

判断前状态：pid=22124 absent=true port=57854 closed=true handshake_present=True
curl.exe /health auth=False (token 经 stdin 配置传入)
{"status": "ok", "boot_id": "ca80b7eb", "pid": 22124, "version": "0.1.0"}
HTTP_STATUS=200


[stale-recovery] command=E:\AI_Agent\src-tauri\target\debug\supervisor-probe.exe --resource-exe E:\AI_Agent\artifacts\step2\dist\app\app.exe
SPECTRUM_ENGINE_EXE=E:\AI_Agent\artifacts\step2\dist\app\app.exe probe_pid=6860
{"elapsed_ms": 643.106, "snapshot": {"generation_id": 1, "phase": "Ready", "pid": 17472, "port": 57875, "boot_id": "b11fe604", "failure": null, "cleanup_complete": false, "pending_activation": false}}
Get-CimInstance:
{"ProcessId":17472,"ParentProcessId":6860,"ExecutablePath":"E:\\AI_Agent\\artifacts\\step2\\dist\\app\\app.exe"}


Image Name                     PID Session Name        Session#    Mem Usage
========================= ======== ================ =========== ============
app.exe                      17472 Console                    1     77,488 K

GetProcessTimes UTC ms=1792310590008; handshake UTC ms=1792310590008; pid/boot/created_at=matched
curl.exe /health auth=False (token 经 stdin 配置传入)
{"status":"ok","boot_id":"b11fe604","pid":17472,"version":"0.1.0","uptime_s":0.594}
HTTP_STATUS=200

陈旧恢复：old_pid=22124 old_boot=ca80b7eb old_port=57854; new_pid=17472 new_boot=b11fe604 new_port=57875; fake_old_health_calls_delta=0
判断前状态：pid=17472 absent=true port=57875 closed=true handshake_present=True
测试卫生（不作为通过依据）：移除本脚本已存档且 owner 已退出的握手/故障夹具。

[dev-invalid-path] command=E:\AI_Agent\src-tauri\target\debug\supervisor-probe.exe --resource-exe E:\AI_Agent\artifacts\step2\dist\app\app.exe
SPECTRUM_ENGINE_EXE=E:\AI_Agent\src-tauri\target\checkpoint2-absent\app.exe probe_pid=18088
{"elapsed_ms": 34.314, "snapshot": {"generation_id": 1, "phase": "Failed", "pid": null, "port": null, "boot_id": null, "failure": {"kind": "SpawnFailed", "exit_reason": {"Win32": {"api": "CreateProcessW", "code": 2}}, "preexisting_handshake_invalid": null, "engine_error": null, "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run/handshake.json", "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl", "data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent"}, "cleanup_complete": true, "pending_activation": false}}

[injection-precedes-env] command=E:\AI_Agent\src-tauri\target\debug\supervisor-probe.exe --resource-exe E:\AI_Agent\artifacts\step2\dist\app\app.exe --injected-exe E:\AI_Agent\artifacts\step2\dist\app\app.exe
SPECTRUM_ENGINE_EXE=E:\AI_Agent\src-tauri\target\checkpoint2-absent\app.exe probe_pid=9996
{"elapsed_ms": 670.595, "snapshot": {"generation_id": 1, "phase": "Ready", "pid": 20392, "port": 57889, "boot_id": "3c8c28f4", "failure": null, "cleanup_complete": false, "pending_activation": false}}
Get-CimInstance:
{"ProcessId":20392,"ParentProcessId":9996,"ExecutablePath":"E:\\AI_Agent\\artifacts\\step2\\dist\\app\\app.exe"}


Image Name                     PID Session Name        Session#    Mem Usage
========================= ======== ================ =========== ============
app.exe                      20392 Console                    1     77,464 K

GetProcessTimes UTC ms=1792310593627; handshake UTC ms=1792310593627; pid/boot/created_at=matched
curl.exe /health auth=False (token 经 stdin 配置传入)
{"status":"ok","boot_id":"3c8c28f4","pid":20392,"version":"0.1.0","uptime_s":0.594}
HTTP_STATUS=200

判断前状态：pid=20392 absent=true port=57889 closed=true handshake_present=True
测试卫生（不作为通过依据）：移除本脚本已存档且 owner 已退出的握手/故障夹具。

[release-ignores-env-library-proof] command=E:\AI_Agent\src-tauri\target\release\supervisor-probe.exe --resource-exe E:\AI_Agent\artifacts\step2\dist\app\app.exe
SPECTRUM_ENGINE_EXE=E:\AI_Agent\src-tauri\target\checkpoint2-absent\app.exe probe_pid=19936
{"elapsed_ms": 651.897, "snapshot": {"generation_id": 1, "phase": "Ready", "pid": 22420, "port": 57904, "boot_id": "d269a528", "failure": null, "cleanup_complete": false, "pending_activation": false}}
Get-CimInstance:
{"ProcessId":22420,"ParentProcessId":19936,"ExecutablePath":"E:\\AI_Agent\\artifacts\\step2\\dist\\app\\app.exe"}


Image Name                     PID Session Name        Session#    Mem Usage
========================= ======== ================ =========== ============
app.exe                      22420 Console                    1     77,344 K

GetProcessTimes UTC ms=1792310596870; handshake UTC ms=1792310596870; pid/boot/created_at=matched
curl.exe /health auth=False (token 经 stdin 配置传入)
{"status":"ok","boot_id":"d269a528","pid":22420,"version":"0.1.0","uptime_s":0.609}
HTTP_STATUS=200

判断前状态：pid=22420 absent=true port=57904 closed=true handshake_present=True
测试卫生（不作为通过依据）：移除本脚本已存档且 owner 已退出的握手/故障夹具。
边界：release probe 验证库的编译分支；Tauri resource resolver/--no-bundle 布局尚未验证。
测试夹具准备：handshake bytes=13 sha256=3c9a3d00c28047c837fa501562738163270e06d0317befb1f87ade5a5b244742

[invalid-json] command=E:\AI_Agent\src-tauri\target\debug\supervisor-probe.exe --resource-exe E:\AI_Agent\artifacts\step2\dist\app\app.exe
SPECTRUM_ENGINE_EXE=E:\AI_Agent\artifacts\step2\dist\app\app.exe probe_pid=1684
{"elapsed_ms": 648.668, "snapshot": {"generation_id": 1, "phase": "Failed", "pid": 512, "port": null, "boot_id": null, "failure": {"kind": "HandshakeInvalid", "exit_reason": {"ProcessExit": {"code": 1}}, "preexisting_handshake_invalid": "InvalidJson", "engine_error": "HANDSHAKE_INVALID_JSON", "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run/handshake.json", "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl", "data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent"}, "cleanup_complete": true, "pending_activation": false}}
本代 handshake_error 原始行：
{"error": "HANDSHAKE_INVALID_JSON", "phase": "startup", "event": "handshake_error", "boot_id": "e2d48d9a", "pid": 512, "logger": "engine.handshake", "level": "error", "timestamp": "2026-10-18T08:03:20.605071Z"}
{"error": "HANDSHAKE_INVALID_JSON", "phase": "finally", "event": "handshake_error", "boot_id": "e2d48d9a", "pid": 512, "logger": "engine.handshake", "level": "error", "timestamp": "2026-10-18T08:03:20.605783Z"}
{"elapsed_ms": 1290.981, "snapshot": {"generation_id": 2, "phase": "Failed", "pid": 12420, "port": null, "boot_id": null, "failure": {"kind": "HandshakeInvalid", "exit_reason": {"ProcessExit": {"code": 1}}, "preexisting_handshake_invalid": "InvalidJson", "engine_error": "HANDSHAKE_INVALID_JSON", "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run/handshake.json", "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl", "data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent"}, "cleanup_complete": true, "pending_activation": false}}
非法握手原字节未变：sha256=3c9a3d00c28047c837fa501562738163270e06d0317befb1f87ade5a5b244742
测试卫生（不作为通过依据）：移除本脚本已存档且 owner 已退出的握手/故障夹具。
测试夹具准备：handshake bytes=22 sha256=b9dba9ed71303bed1f0a6c64909c6ca4993d16eb2d48b79c5c4f5f0e498e55da

[missing-fields] command=E:\AI_Agent\src-tauri\target\debug\supervisor-probe.exe --resource-exe E:\AI_Agent\artifacts\step2\dist\app\app.exe
SPECTRUM_ENGINE_EXE=E:\AI_Agent\artifacts\step2\dist\app\app.exe probe_pid=12836
{"elapsed_ms": 659.471, "snapshot": {"generation_id": 1, "phase": "Failed", "pid": 1448, "port": null, "boot_id": null, "failure": {"kind": "HandshakeInvalid", "exit_reason": {"ProcessExit": {"code": 1}}, "preexisting_handshake_invalid": "InvalidFields", "engine_error": "HANDSHAKE_INVALID_FIELDS", "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run/handshake.json", "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl", "data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent"}, "cleanup_complete": true, "pending_activation": false}}
本代 handshake_error 原始行：
{"error": "HANDSHAKE_INVALID_FIELDS", "phase": "startup", "event": "handshake_error", "pid": 1448, "boot_id": "c3bfe04d", "logger": "engine.handshake", "level": "error", "timestamp": "2026-10-18T08:03:21.920571Z"}
{"error": "HANDSHAKE_INVALID_FIELDS", "phase": "finally", "event": "handshake_error", "pid": 1448, "boot_id": "c3bfe04d", "logger": "engine.handshake", "level": "error", "timestamp": "2026-10-18T08:03:21.920849Z"}
非法握手原字节未变：sha256=b9dba9ed71303bed1f0a6c64909c6ca4993d16eb2d48b79c5c4f5f0e498e55da
测试卫生（不作为通过依据）：移除本脚本已存档且 owner 已退出的握手/故障夹具。
测试夹具准备：handshake bytes=13 sha256=3c9a3d00c28047c837fa501562738163270e06d0317befb1f87ade5a5b244742

[missing-dll-with-invalid-old-handshake] command=E:\AI_Agent\src-tauri\target\debug\supervisor-probe.exe --resource-exe E:\AI_Agent\artifacts\step2\dist\app\app.exe --injected-exe E:\AI_Agent\src-tauri\target\checkpoint2-fixtures\20261018-160306-056134\app\app.exe
SPECTRUM_ENGINE_EXE=None probe_pid=20328
{"elapsed_ms": 85.708, "snapshot": {"generation_id": 1, "phase": "Failed", "pid": 4768, "port": null, "boot_id": null, "failure": {"kind": "ExitedBeforeReady", "exit_reason": {"ProcessExit": {"code": 4294967295}}, "preexisting_handshake_invalid": "InvalidJson", "engine_error": null, "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run/handshake.json", "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl", "data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent"}, "cleanup_complete": true, "pending_activation": false}}
缺 DLL 独立对照（非监督器原次 stderr）：exit_code=4294967295
[PYI-16200:ERROR] Failed to load Python DLL 'E:\AI_Agent\src-tauri\target\checkpoint2-fixtures\20261018-160306-056134\app\_internal\python312.dll'.
LoadLibrary: ?????????


测试卫生（不作为通过依据）：移除本脚本已存档且 owner 已退出的握手/故障夹具。

[exit-after-ready] command=E:\AI_Agent\src-tauri\target\debug\supervisor-probe.exe --resource-exe E:\AI_Agent\artifacts\step2\dist\app\app.exe
SPECTRUM_ENGINE_EXE=E:\AI_Agent\artifacts\step2\dist\app\app.exe probe_pid=10596
{"elapsed_ms": 665.502, "snapshot": {"generation_id": 1, "phase": "Ready", "pid": 16416, "port": 57960, "boot_id": "4c81d4bb", "failure": null, "cleanup_complete": false, "pending_activation": false}}
Get-CimInstance:
{"ProcessId":16416,"ParentProcessId":10596,"ExecutablePath":"E:\\AI_Agent\\artifacts\\step2\\dist\\app\\app.exe"}


Image Name                     PID Session Name        Session#    Mem Usage
========================= ======== ================ =========== ============
app.exe                      16416 Console                    1     77,196 K

GetProcessTimes UTC ms=1792310615468; handshake UTC ms=1792310615468; pid/boot/created_at=matched
curl.exe /health auth=False (token 经 stdin 配置传入)
{"status":"ok","boot_id":"4c81d4bb","pid":16416,"version":"0.1.0","uptime_s":0.594}
HTTP_STATUS=200

taskkill /F /PID 16416
SUCCESS: The process with PID 16416 has been terminated.

{"elapsed_ms": 1280.55, "snapshot": {"generation_id": 1, "phase": "Failed", "pid": 16416, "port": 57960, "boot_id": "4c81d4bb", "failure": {"kind": "EngineExitedAfterReady", "exit_reason": {"ProcessExit": {"code": 1}}, "preexisting_handshake_invalid": null, "engine_error": null, "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run/handshake.json", "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl", "data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent"}, "cleanup_complete": true, "pending_activation": false}}
判断前状态：pid=16416 absent=true port=57960 closed=true handshake_present=True
测试卫生（不作为通过依据）：移除本脚本已存档且 owner 已退出的握手/故障夹具。
{
  "result": "passed",
  "canonical_file_count": 544,
  "canonical_bytes": 255564460,
  "canonical_manifest_match_before_and_after": true,
  "actual_tokens_scanned": 5,
  "token_leaks": 0,
  "actual_token_sha256": [
    "2e882c33a4dc0296c82fb4f8911646dfdf1b1d658311e2325d1a6f7945271e8d",
    "6efb236f3459e4a40cfca0494ea3f348d862c8953c6b2970330a8e94f17527eb",
    "7b69fe51e2d24f96468d24a00a9110ccd1ba241a1f90787bb88e8b816028559f",
    "d4622fb622cfe0080e48e88f4957d5f15ff390cbf0412d8e5bd8c2ee72e10b89",
    "fd079a6ce6ee46f4e44182574561769b724e8bcd15b0c771d2024530066555b0"
  ],
  "original_runtime_log_token_leaks": 0,
  "original_runtime_logs_scanned": [
    "engine-20261018.jsonl",
    "shell-20261018.log"
  ],
  "original_runtime_append_sha256": {
    "engine-20261018.jsonl": "89f746d7fd14159f6f1b5168871d133538b73993ca80d93eba8286632e6f984b",
    "shell-20261018.log": "81d442a4ab367454a59121f35138c8eb1dd2f85f034a1b0316dc78b21b530abc"
  },
  "shell_json_lines_valid": true,
  "shell_token_key_count": 0,
  "probe_residual_count": 0,
  "handshake_absent_after_test_hygiene": true,
  "step2_status": "待实机验证",
  "initial_stub_exit70_internal_cause": "未验证",
  "tauri_resource_layout_and_ui": "未验证",
  "dev_ready_elapsed_ms_probe_to_snapshot": 627.11
}
测试卫生（不作为通过依据）：删除本轮 target 内的 DLL 故障副本。

```


**本代完整握手（仅 token 脱敏）**

```powershell
Get-Content -LiteralPath E:\AI_Agent\artifacts\step3\checkpoint-2\evidence-20261018-160306-056134\dev-ready.handshake.json
```

```json
{
  "boot_id": "ca80b7eb",
  "pid": 22124,
  "process_created_at": "2026-10-18T08:03:06.367Z",
  "port": 57854,
  "token": "<redacted>",
  "protocol": 1,
  "version": "0.1.0",
  "started_at": "2026-10-18T08:03:06.965Z"
}

```


**真实引擎日志三行原始样本**

```powershell
Get-Content -LiteralPath E:\AI_Agent\artifacts\step3\checkpoint-2\evidence-20261018-160306-056134\log-samples.jsonl
```

```jsonl
{"event": "Started server process [22124]", "boot_id": "ca80b7eb", "pid": 22124, "logger": "uvicorn.error", "level": "info", "timestamp": "2026-10-18T08:03:06.912705Z"}
{"event": "Waiting for application startup.", "boot_id": "ca80b7eb", "pid": 22124, "logger": "uvicorn.error", "level": "info", "timestamp": "2026-10-18T08:03:06.913205Z"}
{"event": "Application startup complete.", "boot_id": "ca80b7eb", "pid": 22124, "logger": "uvicorn.error", "level": "info", "timestamp": "2026-10-18T08:03:06.934491Z"}

```


**缺 DLL spawn 计时**

```powershell
Get-Content -LiteralPath E:\AI_Agent\artifacts\step3\checkpoint-2\evidence-20261018-160306-056134\missing-dll-with-invalid-old-handshake.final.timing.json
```

```json
[
  {
    "generation_id": 1,
    "pid": 4768,
    "to": "Failed",
    "process_created_at_ms": 1792310615340,
    "transition_at_ms": 1792310615382,
    "spawn_to_transition_ms": 42
  }
]

```


**原始字节独立审计**

```powershell
& 'E:\AI_Agent\.venv\Scripts\python.exe' artifacts/step3/checkpoint-2/audit_evidence.py artifacts/step3/checkpoint-2/evidence-20261018-160306-056134
```

```text
{
  "exact_original_segment_count": 16,
  "all_exact": true,
  "original_increment_checks": {
    "engine-20261018.jsonl": {
      "start": 699739,
      "end": 713476,
      "bytes": 13737,
      "lines": 75,
      "sha256": "89f746d7fd14159f6f1b5168871d133538b73993ca80d93eba8286632e6f984b",
      "receipt_match": true,
      "hex32_token_pattern_count": 0,
      "literal_token_key_count": 0
    },
    "shell-20261018.log": {
      "start": 61878,
      "end": 82484,
      "bytes": 20606,
      "lines": 145,
      "sha256": "81d442a4ab367454a59121f35138c8eb1dd2f85f034a1b0316dc78b21b530abc",
      "receipt_match": true,
      "hex32_token_pattern_count": 0,
      "literal_token_key_count": 0
    }
  },
  "observed_engine_exit_codes": [
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    4294967295,
    1
  ]
}

```


**当前 VM/锁/缓存路径只读输出**

```powershell
Get-Service vmms; Get-VM/Get-VMMemory/Get-VMSecurity/Get-VMSnapshot -ComputerName localhost; Get-FileHash; Get-Item
```

```text
Command: Get-Service vmms; Get-VM/Get-VMMemory/Get-VMSecurity/Get-VMSnapshot -ComputerName localhost

Name   : vmms
Status : Running



Name           : Win11
State          : Running
Generation     : 2
ProcessorCount : 4
MemoryStartup  : 8589934592



DynamicMemoryEnabled : True
Minimum              : 4294967296
Startup              : 8589934592
Maximum              : 10737418240



TpmEnabled : True



Name         : pristine
Id           : f7ea81cf-6c3a-4823-9a7b-5fe77f4c2300
CreationTime : 2026/10/18 15:41:03


Command: Get-FileHash src-tauri/Cargo.lock, requirements-lock.txt; explicit cache and target paths

Algorithm : SHA256
Hash      : 24A4BEB3D9A41B6B483DA938DC00D28EBD04C7FA2208D0626E863104B07DC51D
Path      : E:\AI_Agent\src-tauri\Cargo.lock

Algorithm : SHA256
Hash      : 58E24B59DA34461A17FD942B4047071E42B5120B3D474BA976A7E28535D40BCC
Path      : E:\AI_Agent\requirements-lock.txt



FullName   : E:\AI_Agent\.cargo-home
Attributes : Directory
LinkType   : 
Target     : 

FullName   : E:\AI_Agent\src-tauri\target
Attributes : Directory
LinkType   : 
Target     : 



```


**收尾原始输出**

```powershell
Get-CimInstance Win32_Process; tasklist /FI "IMAGENAME eq app.exe"; Test-Path handshake.json
```

```text
Command: Get-CimInstance Win32_Process -Filter "Name = 'app.exe' OR Name = 'supervisor-probe.exe'"
workspace_engine_or_probe_process_count=0
Command: tasklist /FI "IMAGENAME eq app.exe"
INFO: No tasks are running which match the specified criteria.

handshake_present_after_test_hygiene=False
Above handshake absence is TEST HYGIENE, not engine cleanup evidence.

```


**完整迁移序列与独立 app_exit**

```powershell
Get-Content -LiteralPath E:\AI_Agent\artifacts\step3\checkpoint-2\evidence-20261018-160306-056134\state-transitions.jsonl
```

```jsonl
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"health_identity_matched","timestamp":"2026-10-18T08:03:06.983Z","to":"Ready"}
{"event":"state_transition","from":"Ready","generation_id":1,"reason":"application_close","timestamp":"2026-10-18T08:03:07.902Z","to":"Stopping"}
{"event":"app_exit","generation_id":1,"timestamp":"2026-10-18T08:03:07.911Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"health_identity_matched","timestamp":"2026-10-18T08:03:10.642Z","to":"Ready"}
{"event":"state_transition","from":"Ready","generation_id":1,"reason":"application_close","timestamp":"2026-10-18T08:03:11.138Z","to":"Stopping"}
{"event":"app_exit","generation_id":1,"timestamp":"2026-10-18T08:03:11.148Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"engine_failure","timestamp":"2026-10-18T08:03:13.564Z","to":"Failed"}
{"event":"state_transition","from":"Failed","generation_id":1,"reason":"application_close","timestamp":"2026-10-18T08:03:13.590Z","to":"Stopping"}
{"event":"app_exit","generation_id":1,"timestamp":"2026-10-18T08:03:13.591Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"health_identity_matched","timestamp":"2026-10-18T08:03:14.286Z","to":"Ready"}
{"event":"state_transition","from":"Ready","generation_id":1,"reason":"application_close","timestamp":"2026-10-18T08:03:14.787Z","to":"Stopping"}
{"event":"app_exit","generation_id":1,"timestamp":"2026-10-18T08:03:14.797Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"health_identity_matched","timestamp":"2026-10-18T08:03:17.506Z","to":"Ready"}
{"event":"state_transition","from":"Ready","generation_id":1,"reason":"application_close","timestamp":"2026-10-18T08:03:17.991Z","to":"Stopping"}
{"event":"app_exit","generation_id":1,"timestamp":"2026-10-18T08:03:18.001Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"engine_failure","timestamp":"2026-10-18T08:03:20.676Z","to":"Failed"}
{"event":"state_transition","from":"Failed","generation_id":2,"reason":"retry_after_cleanup","timestamp":"2026-10-18T08:03:20.712Z","to":"Starting"}
{"event":"state_transition","from":"Starting","generation_id":2,"reason":"engine_failure","timestamp":"2026-10-18T08:03:21.311Z","to":"Failed"}
{"event":"state_transition","from":"Failed","generation_id":2,"reason":"application_close","timestamp":"2026-10-18T08:03:21.354Z","to":"Stopping"}
{"event":"app_exit","generation_id":2,"timestamp":"2026-10-18T08:03:21.354Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"engine_failure","timestamp":"2026-10-18T08:03:21.985Z","to":"Failed"}
{"event":"state_transition","from":"Failed","generation_id":1,"reason":"application_close","timestamp":"2026-10-18T08:03:22.047Z","to":"Stopping"}
{"event":"app_exit","generation_id":1,"timestamp":"2026-10-18T08:03:22.048Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"engine_failure","timestamp":"2026-10-18T08:03:35.382Z","to":"Failed"}
{"event":"state_transition","from":"Failed","generation_id":1,"reason":"application_close","timestamp":"2026-10-18T08:03:35.415Z","to":"Stopping"}
{"event":"app_exit","generation_id":1,"timestamp":"2026-10-18T08:03:35.416Z"}
{"event":"state_transition","from":"Starting","generation_id":1,"reason":"health_identity_matched","timestamp":"2026-10-18T08:03:36.124Z","to":"Ready"}
{"event":"state_transition","from":"Ready","generation_id":1,"reason":"engine_failure","timestamp":"2026-10-18T08:03:36.709Z","to":"Failed"}
{"event":"state_transition","from":"Failed","generation_id":1,"reason":"application_close","timestamp":"2026-10-18T08:03:36.742Z","to":"Stopping"}
{"event":"app_exit","generation_id":1,"timestamp":"2026-10-18T08:03:36.742Z"}

```
