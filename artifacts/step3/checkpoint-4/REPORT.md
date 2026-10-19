## #03 P0：负责人裁定的三项补丁（2026-10-19）

本节为 #03 执行提示词明确授权的文档收尾；下文保留原检查点历史。#01 已封账，最终交付仍固定为 22a13e6a / d8492536，不改安装包或既有冻结批次。封账权威详见 `release-custom-protocol-20261018/final-canonical-20261019/REPORT.md`。

1. **记忆键归属改正**：`HKCU\Software\spectrumagent\SpectrumAgent` 是 **Tauri 2 NSIS 安装器标准行为**，不是 harness 残留。`src-tauri/nsis/installer.nsi:68-69` 定义 MANUKEY/MANUPRODUCTKEY，`:698` 写入安装目录，`:164-166` 配置 Installer Language，`:889` 在勾选清理应用数据且非更新时删除该键。安装后、首跑关窗后、重启后三时点按安装器标准行为判读；reboot 独立轮和记忆键值细节仍记缓测，不用历史消失异常倒推归属。
2. **握手残留拍板 A**：负责人已裁定记已知问题、**不进 0.1.1 热修、不阻塞封账**；无孤儿进程/端口、每 boot 随机 token、陈旧握手自愈已实测两次。保留“未用脚本删除冒充修复”的原始判定，不为清理该残留改封版二进制。
3. **计时档位订正**：24.146ms 尚未获负责人指认轮次，**不采用**。可采的 engine 算法档位为 211.154ms（22a 宿主：`release-custom-protocol-20261018/final-canonical-20261019/analysis-20261019T015517607982Z.json` 的 `timing.metrics.elapsed_ms`），以及 208.095ms（最终安装态 PID18680 的真实 smoke，见同目录 REPORT 的安装态响应与 `installed-delivery-engine.jsonl`）。desktop 呈现档位 1292/1060/1178ms，分别在同目录 `original-source-snapshot/shell-20261019.log:966/:2257/:3025` 的 desktop_presented 事件；该历史日志的 SHADOW 血缘按封账报告既有裁定引用，只说明对应 UI 呈现档位。desktop 呈现、engine 算法耗时和包含人工等待的首次完成耗时不得混用；这些历史值不充当 #03 成品或干净机计时。

## 完成到哪一步

检查点 4：最终 release 宿主机验收、FaultFixture/Canonical 暂存、资源 resolver、两 exe 的 RT_MANIFEST、三段计时、完整 DOM/存储审计及三组各 10 轮进程矩阵已执行，提交负责人复核。NSIS 工具下载及安装目录提案等待明确批准，setup.exe 尚未产生，安装/卸载/断网安装均未执行。第 3 步尚不关闭。

本报告以负责人最新授权为准：第 2 步继续“待实机验证”，旧 exit code=70 的内部原因仍“未验证”。不回写旧 STATUS/REPORT，不以新批次取代旧批次证据。Hyper-V 的旧 Disabled 探针不再作为当前结论；负责人已确认 Enabled、vmms 运行及模块可用。本轮没有执行启用命令、重启或恢复 VM。后续 pristine 只引用 f7ea81cf-6c3a-4823-9a7b-5fe77f4c2300（2026-10-18 15:41:03），不使用已删除的 bb3d1cac。

最终外壳：`E:\AI_Agent\src-tauri\target\release\spectrum-agent.exe`，10,785,792 字节，SHA256 **36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f**，源码提交 **83e8c37**。验收控制器/复核器另提交 **171f162**，不冒充外壳构建来源。后续仅 bundle 现有 exe，并使用 `--no-binary-patching`；不重新 build 已验收 exe。

引擎唯一权威清单：[新冻结批次 product-manifest.json](E:/AI_Agent/artifacts/step2/revision-20261018-smoke-headers/product-manifest.json)。artifact_source_commit=3acd979f3b5a94ad32283eb1608c95f0b8721696；manifest_generator_commit=e7c3c9d90f83d23639a4ee54832c8b4bc75bf706。引擎 app.exe SHA256=3f62c1895152a01eb0a92b61a733985c15ca7888d233fd9408ca5b9dc61d7703；最终 resources/backend 整树 **544 文件、255,564,789 字节**，路径/字节数/SHA256 全量一致。本轮不改引擎、接口或 Python 锁。

历史 A7 候选的文件及失败尝试全部保留，但本报告最终矩阵只采用 36fb 候选的三组：

| 模式 | 最终原始目录 | 结果 |
|---|---|---|
| Ready 后强杀 | 20261018T141341066Z-KillReady | 10/10 |
| 握手发布前强杀 | 20261018T141558694Z-KillStarting | 10/10 |
| 正常关窗 | 20261018T141931529Z-Close | 10/10 |

`all-thirty-matrix-results.json`、`final-matrix-lock-output.txt` 以及无 `36` 前缀的旧 UI/计时文件对应旧 A7 候选，是历史记录，不是最终 SHA 的证据。最终复核输出为 [release-36-analysis-committed-output.txt](E:/AI_Agent/artifacts/step3/checkpoint-4/release-36-analysis-committed-output.txt)，详细派生数据为 release-36-analysis-20261018T150041946516Z.json。其证据生成提交为 171f162，外壳源码提交仍为 83e8c37。

## 命令与原始输出

以下命令均使用已批准工具链，不安装依赖。Cargo 缓存、target、TEMP/TMP 明确落 E 盘；frontend.ps1 校验 Node SHA 并只调整子进程环境，不改用户/系统 PATH。

```powershell
$env:CARGO_HOME='E:\AI_Agent\.cargo-home'
$env:CARGO_TARGET_DIR='E:\AI_Agent\src-tauri\target'
$env:TEMP='E:\AI_Agent\artifacts\step3\checkpoint-4\temp'
$env:TMP=$env:TEMP
$env:CARGO_NET_OFFLINE='true'
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' fmt --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --check
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' clippy --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --all-targets --all-features --locked --offline -- -D warnings
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' test --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --all-features --locked --offline -- --nocapture --test-threads=1
& .\frontend.ps1 run tauri -- build --no-bundle --runner C:\Users\Administrator\.cargo\bin\cargo.exe
& 'E:\AI_Agent\.venv\Scripts\python.exe' artifacts\step3\checkpoint-4\analyze_release_evidence.py
```

fmt 的实际空 stdout 另有执行元数据，不能把“没有文件”当作通过。clippy 无警告；Rust 为 **22 个运行时测试 + 1 个 compile-fail 文档测试**，全部通过。E0308 是拒绝任意 URL/第三路径的预期编译错误，不是失败的测试。Tauri 构建实际执行 `tsc --noEmit && vite build`，并生成上述 release。静态检查的完整原始输出及构建输出附在本节后部。

FaultFixture/Canonical 的实际暂存输出、543/544 文件清单及独立专用 release 失败页证据保留在 fault-*、canonical-* 与 staging-reports/。专用 FaultFixture 外壳 SHA=301ab78355ec50b96b3e58dc776a6651dc5fb002085f86d82d25388495931767，只缺 `_internal/python312.dll`，故障标记在资源树外。其真实宿主日志显示失败页 687 ms；随后已重新 Canonical 暂存并重建。最终 36fb 还在测试副本上复测缺 DLL+非法旧握手，失败页观测上界 772.557 ms，主因仍 ExitedBeforeReady，不抢归 HandshakeInvalid。此上界包含观测和第二实例检查的开销，不能冒充精确 actor 转态耗时。

真实失败脚本命令：

```powershell
& 'E:\AI_Agent\.venv\Scripts\python.exe' E:\AI_Agent\artifacts\step3\checkpoint-4\selfcheck_release_failures.py
```

该脚本显式造非法 JSON/缺字段握手，使用真实冻结引擎；fixture 字节前后不变，失败页可见。两案 startup/finally 各一条本子 PID 的 handshake_error，startup 恰好一条；缺 DLL 对照没有 Python 因果行。每案 Failed 下再开第二实例，退出 0、只激活原窗口、engine_start_attempt 恰好一次。脚本最后恢复 fixture 属 **TEST_HYGIENE_ONLY（测试卫生，不作为产品通过依据）**；不声称外壳清理握手，不把脚本 terminate 失败页算作正常关窗轮次。

进程矩阵采用已有 Explorer 的 COM broker 启动，非测试控制器直接作为父进程。实际 launch：

```powershell
$broker=(New-Object -ComObject Shell.Application).Windows().Item(0).Document.Application
$broker.ShellExecute('C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
 '-NoProfile -NonInteractive -WindowStyle Hidden -File E:\AI_Agent\artifacts\step3\checkpoint-4\matrix-runner.ps1 -Mode KillReady -Rounds 10',
 'E:\AI_Agent','open',0)
# 另外两组分别传 -Mode KillStarting / -Mode Close，均为 -Rounds 10。
```

控制器同样经该 Explorer broker 直接启动 release exe；逐轮记录实际父进程 Explorer PID 8292、`IsProcessInJob(parent)=false`、CIM 和 QueryFullProcessImageName 双路径。外壳按完整 exe 路径计数，引擎按记录 PID+完整路径核对。正常关窗由真实窗口 Alt+F4，10 份 close-36-round-N-ui.txt 对应每轮。强杀实际执行 `C:\Windows\System32\taskkill.exe /PID <本轮外壳PID> /F`。不是按 app.exe 通用名称清场。

Starting 组每轮在自己的握手出现前杀：端口为 null，准确含义是 `unpublished_before_kill`，不是“已知端口关闭”。随后按完整资源 exe 路径确认无孤儿；Ready/Close 组均有具体端口并确认关闭。矩阵未捕获主外壳的实际 exit code，不能写成“退出码 0”；通过依据是独立 app_exit/清理日志、进程及端口核验。第二实例退出码 0 与 dev CLI 退出码 0 则有实际观测。

### 三段计时与真实 UI

| 模式/起点 | 引擎就绪 ms | 界面可交互 ms | 首次 smoke 完成 ms | 交互后人工等待 ms | smoke 往返 ms | 引擎指标 elapsed_ms |
|---|---:|---:|---:|---:|---:|---:|
| dev，tauri dev 命令发出前 | 19655.677 | 19719.677 | 78315.677 | 58388 | 208 | 201.758 |
| release 36fb，直接 spawn 前 | 1353.161 | 1400.161 | 35917.161 | 34386 | 131 | 125.013 |

dev 使用 Vite --force、新 WebView profile，包含编译时间；release 使用新 WebView profile。两者 **未清 OS 文件缓存、不是干净 VM**。首次 smoke 总时长包括人工操作等待，已独立拆出，不据此推导算法耗时。完整 JSON/事件时间戳已归档。本步不设 ≤3 秒通过线，不提前声称定稿干净 Win10/11 冷启动验收通过。

最终 release 从无资源的工作目录 `E:\AI_Agent\artifacts\step3\checkpoint-4\temp` 启动，故意设置无效 SPECTRUM_ENGINE_EXE；实际 selection_source=resolved_resource，路径为 `\\?\E:\AI_Agent\src-tauri\target\release\resources\backend\app.exe`。环境覆盖被忽略且 Ready；真实 /health 原始 HTTP 和脱敏握手全文附后。前端 Ctrl+Enter 调用无参 run_smoke 并显示五个真实指标；Ctrl+K 聚焦、未知输入“验收未知输入”显示“当前地基演示仅支持冒烟测试”。没有 LLM 调用。

主例 PID14352，第一代引擎9252/port56792/boot05b2e4ab；Ready 第二实例15844退出0且握手字节不变。强杀本代引擎后恰好一次 EngineExitedAfterReady；真实点击重试，代次2引擎25744/port58004/boot49fa02c2，旧指标清空并恢复 Ready；最后 Alt+F4 正常关窗，app_exit恰好一次、无 Stopping→Failed。完整迁移日志附后。

30 秒 timeout 使用实际 Tauri **测试宿主+专用 stub**，不是伪造真实引擎超时：Starting 心跳299，最大主循环排队9ms，最大相邻间隔103ms，Starting visible=true为0；第二实例回调置pending_activation，内部engine_status返回Starting。测试探针由 `SPECTRUM_ACCEPTANCE_PROBE=1` 显式开启，45秒有界；普通启动不创建持续定时器。该证据不冒充36fb正式资源引擎证据。

完整 DOM 审计读取 documentElement.outerHTML、全部 input/textarea/select 活值及 disabled、完整 localStorage/sessionStorage，并用实际 token 在原始回调上先扫描后归档。最终四文件 **469 回调、469 完整文档**：Starting23 / Ready443 / Failed3；两种存储均为空。主例450份中含真实smoke指标。Stopping DOM **未捕获**，不能靠代码里有分支声称观测到；已有 Stopping 状态/清理日志，不作为最终对话条渲染证据。

对原始 C 盘源文件再扫描后复制：实际4个token原串、2份完整握手JSON，shell 7208合法JSON行、engine5030行、四DOM文件均0命中，Bearer0；记录原始源路径、字节数、SHA256，复制后逐字节哈希复核。矩阵各自另保留实际token样本数、完整握手样本数与原始shell日志哈希。该复核器验证归档哈希与运行时审计收据；已退出进程的秘密串不落盘，不声称它能从脱敏文件重新取得旧token。

### 20 项验收逐条结果

| 项 | 结果 | 依据与边界 |
|---|---|---|
| 1 静态/构建 | 通过 | fmt空输出+执行元数据；clippy无警告；22+1测试；strict TS/Vite；--no-bundle实际构建。 |
| 2a 专用stub | 通过 | tests-delivery-output.txt：Ready、立即退出23、真实30秒超时、health_boot_id层失败、Ready后退出恰好一次；与真实引擎证据分列。 |
| 2b Win32注入 | 通过 | 同文件五类失败，调用顺序/参数/实际句柄恰关一次；无虚构句柄清理。 |
| 2c 真实release | 通过 | 36fb真实health/smoke/恢复/矩阵；两非法握手有本PID因果行；缺DLL无因果行且直接主因。 |
| 2d 握手纯函数 | 通过 | exact-set/JSON顶层/类型范围/UTC真实日期/协议版本/token错误路径覆盖，完整测试输出。 |
| 3 dev SpawnFailed | 通过 | 真实Tauri测试宿主不存在路径，CreateProcessW=2，无子进程，失败界面652ms。 |
| 4 Fault/Canonical | 通过 | 显式FaultFixture专用release687ms；Canonical全量544；最终36fb副本缺DLL772.557ms。fault标记及XML在资源外。 |
| 5 Resume失败 | 通过 | 注入记录ResumeThread→TerminateJobObject→Wait→Close各实际句柄，完整输出。 |
| 6 代次/Stopping | 通过 | 旧A迟到回调丢弃、B Ready；Stopping后预期退出不产生新EngineExitedAfterReady。真实重试链亦归档。 |
| 7 Starting不冻结 | 通过（测试宿主） | 299心跳/9ms排队/103ms间隔、第二实例与内部invoke、始终隐藏；普通启动无定时写日志。 |
| 8 可见性 | 通过 | Starting隐藏，Ready/Failed实际显示；Starting激活只挂起，不提前显示。 |
| 9 单实例 | 通过 | 最终Ready第二实例退出0，三种Failed各一次退出0、无第二引擎；Starting以真实测试宿主证据验证。 |
| 10 对话条四态/快捷键 | **部分通过** | 真实smoke/Ready/Failed/CtrlK/CtrlEnter/未知输入通过；Starting日志符合隐藏预期；**Stopping对话条最终渲染未捕获**，不判全通过。 |
| 11 三段计时 | 宿主机数据已记录；VM未验证 | dev与最终release三段、人工等待和冷定义分列；干净VM冷启动未执行。 |
| 12 正常关窗 | 通过 | 最终36fb10轮，每轮PID/具体端口，无残留；真实AltF4操作证据。 |
| 13 Ready强杀 | 通过 | 最终36fb10轮，实际Explorer父进程且不在父级Job；本代引擎PID/路径/端口无残留。 |
| 14 发布握手前强杀 | 通过 | 最终36fb10轮，本代HS未发布，端口null，不冒称已知端口关闭；按完整路径查无孤儿。 |
| 15 陈旧握手 | 通过 | 最终Ready矩阵第1→2轮，旧死PID/boot与本代不同，foreign_identity忽略后本代HS及health才Ready；CP2旧端口隔离证据原样引用。 |
| 16 token泄漏 | 通过（已观察范围） | 实际token/完整HS/Bearer先扫原始源再复制，全部0；覆盖smoke与完整DOM/存储。 |
| 17 四态迁移 | 通过（分层证据） | 7允许对无非法对；最终主例5次迁移/独立app_exit；Starting→Stopping另以core harness记录，不冒称TauriUI观测。 |
| 18 资源路径 | 通过 | 最终release无效env仍启动、任意cwd、实际resolver；资源544全量；相对配置；资源/target等未入库；dev指定新冻结批次，旧批次启动证据引用CP2。 |
| 19 锁与Git干净 | **未通过全部条件** | 三锁SHA保持、两新锁旧同笔已验；本轮证据提交后仍有负责人三项未跟踪内容，保留原样，不能声称全仓干净。 |
| 20 RT_MANIFEST | 通过（仅manifest） | 从最终36fb与实际资源引擎提取，两SHA绑定、正确命名空间longPathAware/asInvoker/CommonControls6；LongPathsEnabled实测0；>260功能仍待VM。 |

本节后附完整的静态检查、失败案例、矩阵控制台、两manifest XML、计时/审计输出；大体积原始日志及469份DOM作为独立文件完整保留，不用节选替代原件。

<!-- RAW_OUTPUTS_BEGIN -->

<details>
<summary>fmt 空输出对应的执行元数据：fmt-committed-source-execution.json</summary>

````text
{
  "command": "C:\\Users\\Administrator\\.cargo\\bin\\cargo.exe fmt --manifest-path E:\\AI_Agent\\src-tauri\\Cargo.toml --check",
  "exit_code": 0,
  "stdout_bytes": 0
}
````

</details>

<details>
<summary>clippy 完整原始输出：clippy-delivery-output.txt</summary>

````text
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.44s
````

</details>

<details>
<summary>Rust 全量22+1测试原始输出（包括Win32参数与句柄顺序）：tests-delivery-output.txt</summary>

````text
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `test` profile [unoptimized + debuginfo] target(s) in 4.41s
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

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.06s

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
test absent_executable_immediately_fails_and_does_not_clean_invalid_old_handshake ... FAILURE DISPLAY handshake_path=E:\AI_Agent\src-tauri\target\stub-runtime\23288-1792332013768-1\run\handshake.json
MISSING PATH (constructor injection): kind=SpawnFailed elapsed_ms=15 preexisting_handshake_invalid=retained bytes_unchanged=true
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
test stub_alive_without_handshake_times_out_after_actual_30_seconds ... STUB no-handshake: pid=Some(23448) kind=StartupTimeout elapsed_ms=30031 pending_activation=true
ok
test stub_exit_after_ready_produces_exactly_one_failure_transition ... STUB ready-exit: pid=Some(20688) Ready->Failed(EngineExitedAfterReady) count=1
ok
test stub_immediate_exit_reports_actual_exit_code ... STUB immediate-exit: pid=Some(12692) code=23 kind=ExitedBeforeReady elapsed_ms=52
ok
test stub_ready_then_stop_has_no_listening_port_and_separate_app_exit ... STUB ready/stop: pid=Some(16832) port=63448 phase=Stopping port_absent=true app_exit=1 token_leaks=0
ok
test stub_tolerates_disconnected_health_client ... STUB transport: client disconnected without a request; stub remains Ready
ok
test stub_wrong_health_boot_id_fails_only_after_child_identity_validation ... STUB mismatch: pid=Some(26372) child_pid_and_created_at=verified failure_layer=health_boot_id kind=HealthIdentityMismatch
ok

test result: ok. 9 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 33.94s

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

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.21s

````

</details>

<details>
<summary>正式 --no-bundle 构建及strict TS/Vite原始输出：release-committed-source-build-output.txt</summary>

````text

> spectrum-agent@0.1.0 tauri
> tauri build --no-bundle --runner C:\Users\Administrator\.cargo\bin\cargo.exe

        Info Looking up installed tauri packages to check mismatched versions...
     Running beforeBuildCommand `npm run build`

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

✓ built in 145ms
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `release` profile [optimized] target(s) in 31.62s
       Built application at: E:\AI_Agent\src-tauri\target\release\spectrum-agent.exe
````

</details>

<details>
<summary>专用FaultFixture暂存：fault-staging-output.txt</summary>

````text
validated_absolute_target=E:\AI_Agent\src-tauri\resources\backend source=E:\AI_Agent\artifacts\step3\checkpoint-4\temp\fault-source mode=FaultFixture
report=E:\AI_Agent\artifacts\step3\staging-reports\20261018T103006252Z-FaultFixture-304c0de3.json matched_files=543 fault_fixture=True source_unchanged=true
````

</details>

<details>
<summary>专用FaultFixture实际宿主全量事件：fault-host-events.jsonl</summary>

````text
{"event": "shell_started", "pid": 22192, "timestamp": "2026-10-18T10:31:58.079Z"}
{"event": "single_instance_lock_acquired", "timestamp": "2026-10-18T10:31:58.726Z"}
{"event": "shell_log_started", "timestamp": "2026-10-18T10:31:58.727Z"}
{"event": "engine_start_attempt", "exe": "\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe", "generation_id": 1, "selection_source": "resolved_resource", "timestamp": "2026-10-18T10:31:58.727Z"}
{"event": "preexisting_handshake_snapshot", "generation_id": 1, "old_identity": {"boot_id": "885a547a", "pid": 22664, "port": 56086, "process_created_at_ms": 1792316553162}, "preexisting_handshake_invalid": null, "timestamp": "2026-10-18T10:31:58.728Z"}
{"event": "process_created_suspended", "generation_id": 1, "pid": 21284, "timestamp": "2026-10-18T10:31:58.736Z"}
{"event": "job_assigned", "generation_id": 1, "pid": 21284, "timestamp": "2026-10-18T10:31:58.737Z"}
{"event": "thread_resumed_and_closed", "generation_id": 1, "pid": 21284, "timestamp": "2026-10-18T10:31:58.737Z"}
{"event": "process_identity_recorded", "generation_id": 1, "pid": 21284, "process_created_at_ms": 1792319518730, "timestamp": "2026-10-18T10:31:58.737Z"}
{"event": "handshake_ignored", "generation_id": 1, "reason": "foreign_identity", "timestamp": "2026-10-18T10:31:58.738Z"}
{"event": "window_hidden", "generation_id": 1, "success": true, "timestamp": "2026-10-18T10:31:58.740Z", "visible": false}
{"event": "engine_process_exit", "exit_code": 4294967295, "generation_id": 1, "pid": 21284, "timestamp": "2026-10-18T10:31:58.760Z", "wait_error": null}
{"event": "state_transition", "from": "Starting", "generation_id": 1, "reason": "engine_failure", "timestamp": "2026-10-18T10:31:58.761Z", "to": "Failed"}
{"event": "engine_failure", "failure": {"data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent", "engine_error": null, "exit_reason": {"ProcessExit": {"code": 4294967295}}, "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run\\handshake.json", "kind": "ExitedBeforeReady", "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl", "preexisting_handshake_invalid": null}, "generation_id": 1, "timestamp": "2026-10-18T10:31:58.761Z"}
{"activated": true, "event": "window_shown", "generation_id": 1, "success": true, "timestamp": "2026-10-18T10:31:58.765Z", "visible": true}
{"elapsed_ms": 687, "event": "desktop_presented", "generation_id": 1, "phase": "Failed", "timestamp": "2026-10-18T10:31:58.765Z"}
{"complete": true, "errors": [], "event": "generation_cleanup", "generation_id": 1, "timestamp": "2026-10-18T10:31:58.779Z"}
{"event": "shell_log_started", "timestamp": "2026-10-18T10:32:27.107Z"}
{"event": "shell_started", "pid": 25560, "timestamp": "2026-10-18T10:32:27.107Z"}
{"event": "single_instance_activation", "timestamp": "2026-10-18T10:32:27.114Z"}
{"event": "activation_requested", "generation_id": 1, "pending_activation": true, "phase": "Failed", "timestamp": "2026-10-18T10:32:27.114Z"}
{"activated": true, "event": "window_shown", "generation_id": 1, "success": true, "timestamp": "2026-10-18T10:32:27.115Z", "visible": true}
{"activated": true, "event": "window_shown", "generation_id": 1, "success": true, "timestamp": "2026-10-18T10:32:27.115Z", "visible": true}
{"elapsed_ms": 29038, "event": "desktop_presented", "generation_id": 1, "phase": "Failed", "timestamp": "2026-10-18T10:32:27.116Z"}
````

</details>

<details>
<summary>Canonical暂存：canonical-staging-output.txt</summary>

````text
validated_absolute_target=E:\AI_Agent\src-tauri\resources\backend source=E:\AI_Agent\artifacts\step2\revision-20261018-smoke-headers\dist\app mode=Canonical
report=E:\AI_Agent\artifacts\step3\staging-reports\20261018T103342515Z-Canonical-1c3eaad4.json matched_files=544 fault_fixture=False source_unchanged=true
````

</details>

<details>
<summary>最终36fb源码/资源绑定：release-36fbc-source-binding.json</summary>

````text
{
  "shell_source_commit": "83e8c37",
  "shell_sha256": "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f",
  "shell_bytes": 10785792,
  "canonical_backup": "E:\\AI_Agent\\artifacts\\step3\\checkpoint-4\\temp\\canonical-36fbc3df",
  "resource_files": 544,
  "resource_full_manifest_match": true,
  "engine_manifest": "artifacts/step2/revision-20261018-smoke-headers/product-manifest.json",
  "engine_artifact_source_commit": "3acd979f3b5a94ad32283eb1608c95f0b8721696",
  "engine_manifest_generator_commit": "e7c3c9d90f83d23639a4ee54832c8b4bc75bf706",
  "fault_fixture": false
}
````

</details>

<details>
<summary>最终36fb失败三案例，含因果原行与测试卫生声明：release-36-failure-cases-output.txt</summary>

````text
{"case": "invalid-json", "shell_pid": 19480, "shell_sha256": "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f", "engine_pid": 27092, "failure": {"data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent", "engine_error": "HANDSHAKE_INVALID_JSON", "exit_reason": {"ProcessExit": {"code": 1}}, "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run\\handshake.json", "kind": "HandshakeInvalid", "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl", "preexisting_handshake_invalid": "InvalidJson"}, "causal_rows": [{"error": "HANDSHAKE_INVALID_JSON", "phase": "startup", "event": "handshake_error", "pid": 27092, "boot_id": "f20acec5", "logger": "engine.handshake", "level": "error", "timestamp": "2026-10-18T14:25:44.616518Z"}, {"error": "HANDSHAKE_INVALID_JSON", "phase": "finally", "event": "handshake_error", "pid": 27092, "boot_id": "f20acec5", "logger": "engine.handshake", "level": "error", "timestamp": "2026-10-18T14:25:44.617399Z"}], "fixture_bytes_unchanged": true, "failure_page_observed": true, "elapsed_ms_to_dom_observation": 1447.925, "fault_fixture": false, "fault_fixture_resource_files": null, "failed_second_instance_pid": 20952, "failed_second_instance_exit": 0, "engine_start_attempts": 1, "activation_received": true}
TEST_HYGIENE_ONLY: terminate observed failure-page shell PID=19480; not a normal-close test
{"case": "missing-fields", "shell_pid": 21520, "shell_sha256": "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f", "engine_pid": 24780, "failure": {"data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent", "engine_error": "HANDSHAKE_INVALID_FIELDS", "exit_reason": {"ProcessExit": {"code": 1}}, "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run\\handshake.json", "kind": "HandshakeInvalid", "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl", "preexisting_handshake_invalid": "InvalidFields"}, "causal_rows": [{"error": "HANDSHAKE_INVALID_FIELDS", "phase": "startup", "event": "handshake_error", "boot_id": "919eeb9d", "pid": 24780, "logger": "engine.handshake", "level": "error", "timestamp": "2026-10-18T14:25:46.025446Z"}, {"error": "HANDSHAKE_INVALID_FIELDS", "phase": "finally", "event": "handshake_error", "boot_id": "919eeb9d", "pid": 24780, "logger": "engine.handshake", "level": "error", "timestamp": "2026-10-18T14:25:46.026555Z"}], "fixture_bytes_unchanged": true, "failure_page_observed": true, "elapsed_ms_to_dom_observation": 1347.925, "fault_fixture": false, "fault_fixture_resource_files": null, "failed_second_instance_pid": 3028, "failed_second_instance_exit": 0, "engine_start_attempts": 1, "activation_received": true}
TEST_HYGIENE_ONLY: terminate observed failure-page shell PID=21520; not a normal-close test
{"case": "missing-dll-plus-invalid-json", "shell_pid": 11612, "shell_sha256": "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f", "engine_pid": 21320, "failure": {"data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent", "engine_error": null, "exit_reason": {"ProcessExit": {"code": 4294967295}}, "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run\\handshake.json", "kind": "ExitedBeforeReady", "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl", "preexisting_handshake_invalid": "InvalidJson"}, "causal_rows": [], "fixture_bytes_unchanged": true, "failure_page_observed": true, "elapsed_ms_to_dom_observation": 772.557, "fault_fixture": true, "fault_fixture_resource_files": 543, "failed_second_instance_pid": 27140, "failed_second_instance_exit": 0, "engine_start_attempts": 1, "activation_received": true}
TEST_HYGIENE_ONLY: terminate observed failure-page shell PID=11612; not a normal-close test
FAILURE_CASES_PASSED count=3 output=E:\AI_Agent\artifacts\step3\checkpoint-4\failure-cases-20261018T142530759302Z
TEST_HYGIENE_ONLY: restored pre-test handshake bytes; not an acceptance predicate
````

</details>

<details>
<summary>真实Tauri dev/test SpawnFailed：spawn-failed-result.json</summary>

````text
{
  "failure": {
    "event": "engine_failure",
    "failure": {
      "data_directory": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent",
      "engine_error": null,
      "exit_reason": {
        "Win32": {
          "api": "CreateProcessW",
          "code": 2
        }
      },
      "handshake_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\run\\handshake.json",
      "kind": "SpawnFailed",
      "log_path": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\engine-20261018.jsonl",
      "preexisting_handshake_invalid": null
    },
    "generation_id": 1,
    "timestamp": "2026-10-18T14:01:31.660Z"
  },
  "desktop_presented": {
    "elapsed_ms": 652,
    "event": "desktop_presented",
    "generation_id": 1,
    "phase": "Failed",
    "timestamp": "2026-10-18T14:01:31.685Z"
  },
  "child_created": false
}
````

</details>

<details>
<summary>Starting 30秒测试宿主断言（完整原事件另存timeout-events.jsonl）：timeout-assertions.json</summary>

````text
{
  "starting_heartbeats": 299,
  "max_queue_ms": 9,
  "max_heartbeat_gap_ms": 103,
  "starting_visible_true": 0,
  "internal_invoke_returned_starting": true,
  "pending_activation_starting": true,
  "timeout_transition": "2026-10-18T10:39:29.582Z",
  "all_audit_token_hits": 0
}
````

</details>

<details>
<summary>Starting第二实例：timeout-second-instance.txt</summary>

````text
starting_second_instance_pid=26844 exit=0
````

</details>

<details>
<summary>最终36fb Ready第二实例：release-36-ready-single-instance.json</summary>

````text
{
  "secondary_pid": 15844,
  "secondary_exit": 0,
  "handshake_bytes_unchanged": true
}
````

</details>

<details>
<summary>最终36fb实际 /health HTTP原文：release-36-health-http.txt</summary>

````text
HTTP/1.1 200 OK
date: Sun, 18 Oct 2026 14:37:13 GMT
server: uvicorn
content-length: 83
content-type: application/json

{"status":"ok","boot_id":"05b2e4ab","pid":9252,"version":"0.1.0","uptime_s":40.375}
````

</details>

<details>
<summary>最终36fb握手全文（仅token打码）：release-36-handshake-redacted.json</summary>

````text
{
  "boot_id": "05b2e4ab",
  "pid": 9252,
  "process_created_at": "2026-10-18T14:36:33.067Z",
  "port": 56792,
  "token": "[REDACTED]",
  "protocol": 1,
  "version": "0.1.0",
  "started_at": "2026-10-18T14:36:33.697Z"
}
````

</details>

<details>
<summary>最终36fb真实前端smoke操作及完整五指标：release-36-smoke-ui.txt</summary>

````text
Window: "光谱数据 AI Agent", App: spectrum-agent.exe.
	0 窗口 光谱数据 AI Agent Secondary Actions: Raise
		7 窗格
			8 窗格 光谱数据 AI Agent
				9 窗格 (disabled)
				10 区域 光谱数据 AI Agent - Web 内容
					11 区域
						12 区域
							13 区域
								14 区域
								15 区域
									16 区域
										17 区域
											18 区域
												19 区域
												20 文档 光谱数据 AI Agent Value: http://tauri.localhost/ ID: RootWebArea
													21 组 ID: root
														22 主要
															23 标题 光谱数据 AI Agent · 地基演示
															24 状态
																25 文本 引擎已就绪
															26 文本 本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。
															27 文本 进程
															28 文本 9252
															29 文本 · 端口
															30 文本 56792
															31 文本 · 启动代次
															32 文本 1
															42 组 冒烟测试真实结果
																43 文本 { "nan_ratio": 0, "reflectance_range": [ -1.5275289241381491, 1.5275289241381491 ], "bands": 8, "shape": [ 8, 8, 8 ], "elapsed_ms": 125.013 }
														33 页脚 常驻对话条
															34 状态
																35 文本 冒烟测试完成。
															36 文本 hello 对话条
															37 编辑 (settable, string) hello 对话条 Description: 运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送） ID: agent-input
															38 按钮 发送
								39 区域
						40 区域
						41 区域
		1 标题栏 (settable, string) Value: 光谱数据 AI Agent
			2 菜单栏 系统 ID: MenuBar
				3 菜单项目 系统
			4 按钮 最小化
			5 按钮 最大化
			6 按钮 关闭

Document text: ```
光谱数据 AI Agent · 地基演示
引擎已就绪
本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。
进程 9252 · 端口 56792 · 启动代次 1
{
  "nan_ratio": 0,
  "reflectance_range": [
    -1.5275289241381491,
    1.5275289241381491
  ],
  "bands": 8,
  "shape": [
    8,
    8,
    8
  ],
  "elapsed_ms": 125.013
}
冒烟测试完成。
hello 对话条
￼
发送
```
````

</details>

<details>
<summary>最终36fb Ctrl+K操作证据：release-36-ctrl-k.txt</summary>

````text
{
  "document_text": "￼",
  "focused_element": "20 文档 光谱数据 AI Agent Value: http://tauri.localhost/ ID: RootWebArea",
  "tree": "Window: \"光谱数据 AI Agent\", App: spectrum-agent.exe.\n\t0 窗口 光谱数据 AI Agent Secondary Actions: Raise\n\t\t7 窗格\n\t\t\t8 窗格 光谱数据 AI Agent\n\t\t\t\t9 窗格 (disabled)\n\t\t\t\t10 区域 光谱数据 AI Agent - Web 内容\n\t\t\t\t\t11 区域\n\t\t\t\t\t\t12 区域\n\t\t\t\t\t\t\t13 区域\n\t\t\t\t\t\t\t\t14 区域\n\t\t\t\t\t\t\t\t15 区域\n\t\t\t\t\t\t\t\t\t16 区域\n\t\t\t\t\t\t\t\t\t\t17 区域\n\t\t\t\t\t\t\t\t\t\t\t18 区域\n\t\t\t\t\t\t\t\t\t\t\t\t19 区域\n\t\t\t\t\t\t\t\t\t\t\t\t20 文档 光谱数据 AI Agent Value: http://tauri.localhost/ ID: RootWebArea\n\t\t\t\t\t\t\t\t\t\t\t\t\t21 组 ID: root\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t58 主要\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t59 标题 光谱数据 AI Agent · 地基演示\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t60 状态\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t61 文本 引擎已就绪\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t62 文本 本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t63 文本 进程\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t64 文本 25744\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t65 文本 · 端口\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t66 文本 58004\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t67 文本 · 启动代次\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t68 文本 2\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t69 页脚 常驻对话条\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t70 状态\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t71 文本 输入“运行冒烟测试”，或点击发送。\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t72 文本 hello 对话条\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t73 编辑 (settable, string) hello 对话条 Description: 运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送） ID: agent-input\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t74 按钮 发送\n\t\t\t\t\t\t\t\t39 区域\n\t\t\t\t\t\t40 区域\n\t\t\t\t\t\t41 区域\n\t\t1 标题栏 (settable, string) Value: 光谱数据 AI Agent\n\t\t\t2 菜单栏 系统 ID: MenuBar\n\t\t\t\t75 菜单项目 系统\n\t\t\t4 按钮 最小化\n\t\t\t5 按钮 最大化\n\t\t\t6 按钮 关闭\n\nDocument text: ```\n￼\n```"
}
````

</details>

<details>
<summary>最终36fb Failed页面：release-36-failed-ui.txt</summary>

````text
Window: "光谱数据 AI Agent", App: spectrum-agent.exe.
	0 窗口 光谱数据 AI Agent Secondary Actions: Raise
		7 窗格
			8 窗格 光谱数据 AI Agent
				9 窗格 (disabled)
				10 区域 光谱数据 AI Agent - Web 内容
					11 区域
						12 区域
							13 区域
								14 区域
								15 区域
									16 区域
										17 区域
											18 区域
												19 区域
												20 文档 光谱数据 AI Agent Value: http://tauri.localhost/ ID: RootWebArea
													21 组 ID: root
														22 主要
															23 标题 光谱数据 AI Agent · 地基演示
															44 警报
																45 标题 引擎启动或运行失败
																46 文本 引擎意外退出。
																47 文本 退出码：1
																48 文本 握手路径：
																49 文本 C:\Users\Administrator\AppData\Local\SpectrumAgent\run\handshake.json
																50 文本 日志路径：
																51 文本 C:\Users\Administrator\AppData\Local\SpectrumAgent\logs\engine-20261018.jsonl
																52 文本 数据目录：
																53 文本 C:\Users\Administrator\AppData\Local\SpectrumAgent
																54 按钮 重试
																55 按钮 打开数据目录
														33 页脚 常驻对话条
															34 状态
																35 文本 引擎不可用，请查看失败原因与诊断入口。
															36 文本 hello 对话条
															37 编辑 (disabled) hello 对话条 Description: 运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送） ID: agent-input
															38 按钮 (disabled) 发送
								39 区域
						40 区域
						41 区域
		1 标题栏 (settable, string) Value: 光谱数据 AI Agent
			2 菜单栏 系统 ID: MenuBar
				3 菜单项目 系统
			4 按钮 最小化
			5 按钮 最大化
			6 按钮 关闭

Document text: ```
光谱数据 AI Agent · 地基演示
引擎启动或运行失败
引擎意外退出。
退出码：1
握手路径：C:\Users\Administrator\AppData\Local\SpectrumAgent\run\handshake.json
日志路径：C:\Users\Administrator\AppData\Local\SpectrumAgent\logs\engine-20261018.jsonl
数据目录：C:\Users\Administrator\AppData\Local\SpectrumAgent
重试打开数据目录
引擎不可用，请查看失败原因与诊断入口。
hello 对话条
￼
发送
```
````

</details>

<details>
<summary>最终36fb重试后界面：release-36-retry-ui.txt</summary>

````text
Window: "光谱数据 AI Agent", App: spectrum-agent.exe.
	0 窗口 光谱数据 AI Agent Secondary Actions: Raise
		7 窗格
			8 窗格 光谱数据 AI Agent
				9 窗格 (disabled)
				10 区域 光谱数据 AI Agent - Web 内容
					11 区域
						12 区域
							13 区域
								14 区域
								15 区域
									16 区域
										17 区域
											18 区域
												19 区域
												20 文档 光谱数据 AI Agent Value: http://tauri.localhost/ ID: RootWebArea
													21 组 ID: root
														58 主要
															59 标题 光谱数据 AI Agent · 地基演示
															60 状态
																61 文本 引擎已就绪
															62 文本 本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。
															63 文本 进程
															64 文本 25744
															65 文本 · 端口
															66 文本 58004
															67 文本 · 启动代次
															68 文本 2
														69 页脚 常驻对话条
															70 状态
																71 文本 输入“运行冒烟测试”，或点击发送。
															72 文本 hello 对话条
															73 编辑 (settable, string) hello 对话条 Description: 运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送） ID: agent-input
															74 按钮 发送
								39 区域
						40 区域
						41 区域
		1 标题栏 (settable, string) Value: 光谱数据 AI Agent
			2 菜单栏 系统 ID: MenuBar
				75 菜单项目 系统
			4 按钮 最小化
			5 按钮 最大化
			6 按钮 关闭

Document text: ```
光谱数据 AI Agent · 地基演示
引擎已就绪
本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。
进程 25744 · 端口 58004 · 启动代次 2
输入“运行冒烟测试”，或点击发送。
hello 对话条
￼
发送
```
````

</details>

<details>
<summary>最终36fb未知输入处理完成后的界面：release-36-unknown-settled-ui.txt</summary>

````text
Window: "光谱数据 AI Agent", App: spectrum-agent.exe.
	0 窗口 光谱数据 AI Agent Secondary Actions: Raise
		7 窗格
			8 窗格 光谱数据 AI Agent
				9 窗格 (disabled)
				10 区域 光谱数据 AI Agent - Web 内容
					11 区域
						12 区域
							13 区域
								14 区域
								15 区域
									16 区域
										17 区域
											18 区域
												19 区域
												20 文档 光谱数据 AI Agent Value: http://tauri.localhost/ ID: RootWebArea
													21 组 ID: root
														58 主要
															59 标题 光谱数据 AI Agent · 地基演示
															60 状态
																61 文本 引擎已就绪
															62 文本 本页为阶段一骨架占位；仅提供 ENVI / SNV 冒烟演示。
															63 文本 进程
															64 文本 25744
															65 文本 · 端口
															66 文本 58004
															67 文本 · 启动代次
															68 文本 2
														69 页脚 常驻对话条
															70 状态
																71 文本 当前地基演示仅支持冒烟测试
															72 文本 hello 对话条
															73 编辑 (settable, string) hello 对话条 Description: 运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送） Value: 验收未知输入 ID: agent-input
															74 按钮 发送
								39 区域
						40 区域
						41 区域
		1 标题栏 (settable, string) Value: 光谱数据 AI Agent
			2 菜单栏 系统 ID: MenuBar
				75 菜单项目 系统
			4 按钮 最小化
			5 按钮 最大化
			6 按钮 关闭

Document text: ```
验收未知输入
```
````

</details>

<details>
<summary>dev实际计时与冷启动定义：dev-three-stage-timing.json</summary>

````text
{
  "mode": "dev",
  "launch": {
    "command": "frontend.ps1 run tauri -- dev --no-watch --config E:\\AI_Agent\\artifacts\\step3\\checkpoint-3\\cold-dev-config.json",
    "launch_utc": "2026-10-18T13:50:33.1443236Z",
    "cold_definition": "Vite --force dependency optimizer; new WebView user data directory; OS file cache not purged",
    "engine": "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\app.exe"
  },
  "shell_pid": 26608,
  "shell_sha256": "5a3caa102d8e92d39a646c43ab422a69bcd5776c7116ae2c75e349ccc5355265",
  "engine_ready_from_command_ms": 19655.677,
  "interactive_from_command_ms": 19719.677,
  "interactive_from_host_ms": 2097,
  "first_smoke_from_command_ms": 78315.677,
  "manual_wait_before_smoke_ms": 58388.0,
  "smoke_round_trip_ms": 208.0,
  "smoke": {
    "event": "smoke_finished",
    "generation_id": 1,
    "result": {
      "Ok": {
        "bands": 8,
        "elapsed_ms": 201.758,
        "nan_ratio": 0.0,
        "reflectance_range": [
          -1.5275289241381491,
          1.5275289241381491
        ],
        "shape": [
          8,
          8,
          8
        ]
      }
    },
    "timestamp": "2026-10-18T13:51:51.460Z"
  },
  "clean_vm": false
}
````

</details>

<details>
<summary>dev真实CLI完整输出与1412：dev-timing-output.txt</summary>

````text

> spectrum-agent@0.1.0 tauri
> tauri dev --no-watch --config E:\AI_Agent\artifacts\step3\checkpoint-3\cold-dev-config.json

     Running BeforeDevCommand (`npm run dev -- --force`)

> spectrum-agent@0.1.0 dev
> vite --force

21:50:35 [vite] (client) Forced re-optimization of dependencies

  VITE v8.3.4  ready in 382 ms

  ➜  Local:   http://127.0.0.1:1420/
     Running DevCommand (`cargo  run --no-default-features --color always --`)
   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Building [=======================> ] 382/385: spectru…
    Building [=======================> ] 383/385: spectru…
    Building [=======================> ] 384/385: spectru…
                                                            
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 12.86s
     Running `target\debug\spectrum-agent.exe`
[1018/215235.302:ERROR:ui\gfx\win\window_impl.cc:172] Failed to unregister class Chrome_WidgetWin_0. Error = 1412
````

</details>

<details>
<summary>最终36fb Ready强杀10轮完整控制台：explorer-KillReady-20261018T141340640Z-console.txt</summary>

````text
{"round":1,"mode":"KillReady","shell_pid":15404,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":26728,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":57014,"boot_id":"762f81de","handshake_published":true,"elapsed_ms":1339}
成功: 已终止 PID 为 15404 的进程。
{"round":1,"mode":"KillReady","shell_pid":15404,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":26728,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":57014,"port_status":"closed","boot_id":"762f81de","old_boot_id":"5a1b269f","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":2,"mode":"KillReady","shell_pid":5676,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":16644,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":59574,"boot_id":"caa59c59","handshake_published":true,"elapsed_ms":1285}
成功: 已终止 PID 为 5676 的进程。
{"round":2,"mode":"KillReady","shell_pid":5676,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":16644,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":59574,"port_status":"closed","boot_id":"caa59c59","old_boot_id":"762f81de","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":3,"mode":"KillReady","shell_pid":24628,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":27076,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":57548,"boot_id":"33fd499a","handshake_published":true,"elapsed_ms":1300}
成功: 已终止 PID 为 24628 的进程。
{"round":3,"mode":"KillReady","shell_pid":24628,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":27076,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":57548,"port_status":"closed","boot_id":"33fd499a","old_boot_id":"caa59c59","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":4,"mode":"KillReady","shell_pid":17192,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":21144,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":61586,"boot_id":"4706d594","handshake_published":true,"elapsed_ms":1263}
成功: 已终止 PID 为 17192 的进程。
{"round":4,"mode":"KillReady","shell_pid":17192,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":21144,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":61586,"port_status":"closed","boot_id":"4706d594","old_boot_id":"33fd499a","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":5,"mode":"KillReady","shell_pid":22068,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":16236,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":53976,"boot_id":"d2aede59","handshake_published":true,"elapsed_ms":1287}
成功: 已终止 PID 为 22068 的进程。
{"round":5,"mode":"KillReady","shell_pid":22068,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":16236,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":53976,"port_status":"closed","boot_id":"d2aede59","old_boot_id":"4706d594","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":6,"mode":"KillReady","shell_pid":21544,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":3384,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":53187,"boot_id":"2fa21744","handshake_published":true,"elapsed_ms":1255}
成功: 已终止 PID 为 21544 的进程。
{"round":6,"mode":"KillReady","shell_pid":21544,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":3384,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":53187,"port_status":"closed","boot_id":"2fa21744","old_boot_id":"d2aede59","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":7,"mode":"KillReady","shell_pid":23040,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":10292,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":50134,"boot_id":"72e71c41","handshake_published":true,"elapsed_ms":1258}
成功: 已终止 PID 为 23040 的进程。
{"round":7,"mode":"KillReady","shell_pid":23040,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":10292,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":50134,"port_status":"closed","boot_id":"72e71c41","old_boot_id":"2fa21744","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":8,"mode":"KillReady","shell_pid":16236,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":4228,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":58770,"boot_id":"f80f03e1","handshake_published":true,"elapsed_ms":1277}
成功: 已终止 PID 为 16236 的进程。
{"round":8,"mode":"KillReady","shell_pid":16236,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":4228,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":58770,"port_status":"closed","boot_id":"f80f03e1","old_boot_id":"72e71c41","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":9,"mode":"KillReady","shell_pid":1108,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":26760,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":49923,"boot_id":"86d2efe6","handshake_published":true,"elapsed_ms":1292}
成功: 已终止 PID 为 1108 的进程。
{"round":9,"mode":"KillReady","shell_pid":1108,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":26760,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":49923,"port_status":"closed","boot_id":"86d2efe6","old_boot_id":"f80f03e1","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":10,"mode":"KillReady","shell_pid":24088,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":19756,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":50282,"boot_id":"7ee44e9b","handshake_published":true,"elapsed_ms":1290}
成功: 已终止 PID 为 24088 的进程。
{"round":10,"mode":"KillReady","shell_pid":24088,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":19756,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":50282,"port_status":"closed","boot_id":"7ee44e9b","old_boot_id":"86d2efe6","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{
    "mode":  "KillReady",
    "rounds":  10,
    "actual_token_samples":  11,
    "full_handshake_samples":  11,
    "whole_handshake_json_hits":  0,
    "original_source":  "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\shell-20261018.log",
    "exact_token_hits":  0,
    "authorization_bearer":  false,
    "sha256":  "76fb19e6f71e35adfab1f30562b1e77f5505f0bc6756edbcae02eddd32cce606",
    "binary_sha256_after":  "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f"
}
MATRIX_PASSED mode=KillReady rounds=10 output=E:\AI_Agent\artifacts\step3\checkpoint-4\20261018T141341066Z-KillReady
````

</details>

<details>
<summary>最终36fb发布握手前强杀10轮完整控制台：explorer-KillStarting-20261018T141558561Z-console.txt</summary>

````text
{"round":1,"mode":"KillStarting","shell_pid":24820,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":23044,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"boot_id":null,"handshake_published":false,"elapsed_ms":682}
成功: 已终止 PID 为 24820 的进程。
{"round":1,"mode":"KillStarting","shell_pid":24820,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":23044,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"port_status":"unpublished_before_kill","boot_id":null,"old_boot_id":"7ee44e9b","handshake_published_before_action":false,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":2,"mode":"KillStarting","shell_pid":23880,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":27580,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"boot_id":null,"handshake_published":false,"elapsed_ms":636}
成功: 已终止 PID 为 23880 的进程。
{"round":2,"mode":"KillStarting","shell_pid":23880,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":27580,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"port_status":"unpublished_before_kill","boot_id":null,"old_boot_id":"7ee44e9b","handshake_published_before_action":false,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":3,"mode":"KillStarting","shell_pid":23092,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":13188,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"boot_id":null,"handshake_published":false,"elapsed_ms":661}
成功: 已终止 PID 为 23092 的进程。
{"round":3,"mode":"KillStarting","shell_pid":23092,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":13188,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"port_status":"unpublished_before_kill","boot_id":null,"old_boot_id":"7ee44e9b","handshake_published_before_action":false,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":4,"mode":"KillStarting","shell_pid":24588,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":25668,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"boot_id":null,"handshake_published":false,"elapsed_ms":639}
成功: 已终止 PID 为 24588 的进程。
{"round":4,"mode":"KillStarting","shell_pid":24588,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":25668,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"port_status":"unpublished_before_kill","boot_id":null,"old_boot_id":"7ee44e9b","handshake_published_before_action":false,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":5,"mode":"KillStarting","shell_pid":15108,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":26740,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"boot_id":null,"handshake_published":false,"elapsed_ms":621}
成功: 已终止 PID 为 15108 的进程。
{"round":5,"mode":"KillStarting","shell_pid":15108,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":26740,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"port_status":"unpublished_before_kill","boot_id":null,"old_boot_id":"7ee44e9b","handshake_published_before_action":false,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":6,"mode":"KillStarting","shell_pid":24556,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":20252,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"boot_id":null,"handshake_published":false,"elapsed_ms":633}
成功: 已终止 PID 为 24556 的进程。
{"round":6,"mode":"KillStarting","shell_pid":24556,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":20252,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"port_status":"unpublished_before_kill","boot_id":null,"old_boot_id":"7ee44e9b","handshake_published_before_action":false,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":7,"mode":"KillStarting","shell_pid":26232,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":16920,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"boot_id":null,"handshake_published":false,"elapsed_ms":644}
成功: 已终止 PID 为 26232 的进程。
{"round":7,"mode":"KillStarting","shell_pid":26232,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":16920,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"port_status":"unpublished_before_kill","boot_id":null,"old_boot_id":"7ee44e9b","handshake_published_before_action":false,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":8,"mode":"KillStarting","shell_pid":24924,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":15948,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"boot_id":null,"handshake_published":false,"elapsed_ms":655}
成功: 已终止 PID 为 24924 的进程。
{"round":8,"mode":"KillStarting","shell_pid":24924,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":15948,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"port_status":"unpublished_before_kill","boot_id":null,"old_boot_id":"7ee44e9b","handshake_published_before_action":false,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":9,"mode":"KillStarting","shell_pid":18968,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":10084,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"boot_id":null,"handshake_published":false,"elapsed_ms":653}
成功: 已终止 PID 为 18968 的进程。
{"round":9,"mode":"KillStarting","shell_pid":18968,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":10084,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"port_status":"unpublished_before_kill","boot_id":null,"old_boot_id":"7ee44e9b","handshake_published_before_action":false,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":10,"mode":"KillStarting","shell_pid":15896,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":19848,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"boot_id":null,"handshake_published":false,"elapsed_ms":647}
成功: 已终止 PID 为 15896 的进程。
{"round":10,"mode":"KillStarting","shell_pid":15896,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":19848,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":null,"port_status":"unpublished_before_kill","boot_id":null,"old_boot_id":"7ee44e9b","handshake_published_before_action":false,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{
    "mode":  "KillStarting",
    "rounds":  10,
    "actual_token_samples":  1,
    "full_handshake_samples":  1,
    "whole_handshake_json_hits":  0,
    "original_source":  "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\shell-20261018.log",
    "exact_token_hits":  0,
    "authorization_bearer":  false,
    "sha256":  "96f9a520f9780dcb183e3ae79069f12402ce72b5d9fc1a45a8a9b419ed655dfb",
    "binary_sha256_after":  "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f"
}
MATRIX_PASSED mode=KillStarting rounds=10 output=E:\AI_Agent\artifacts\step3\checkpoint-4\20261018T141558694Z-KillStarting
````

</details>

<details>
<summary>最终36fb正常关窗10轮完整控制台：explorer-Close-20261018T141931396Z-console.txt</summary>

````text
{"round":1,"mode":"Close","shell_pid":7588,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":1564,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":51500,"boot_id":"42cf026a","handshake_published":true,"elapsed_ms":1352}
WAITING_FOR_WINDOW_CLOSE round=1 shell_pid=7588 engine_pid=1564 port=51500
{"round":1,"mode":"Close","shell_pid":7588,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":1564,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":51500,"port_status":"closed","boot_id":"42cf026a","old_boot_id":"7ee44e9b","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":2,"mode":"Close","shell_pid":27464,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":26232,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":56687,"boot_id":"a8c012ed","handshake_published":true,"elapsed_ms":1315}
WAITING_FOR_WINDOW_CLOSE round=2 shell_pid=27464 engine_pid=26232 port=56687
{"round":2,"mode":"Close","shell_pid":27464,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":26232,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":56687,"port_status":"closed","boot_id":"a8c012ed","old_boot_id":"42cf026a","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":3,"mode":"Close","shell_pid":26388,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":17844,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":53302,"boot_id":"97a8d3b7","handshake_published":true,"elapsed_ms":1232}
WAITING_FOR_WINDOW_CLOSE round=3 shell_pid=26388 engine_pid=17844 port=53302
{"round":3,"mode":"Close","shell_pid":26388,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":17844,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":53302,"port_status":"closed","boot_id":"97a8d3b7","old_boot_id":"a8c012ed","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":4,"mode":"Close","shell_pid":20188,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":24924,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":58796,"boot_id":"86f13b8b","handshake_published":true,"elapsed_ms":1293}
WAITING_FOR_WINDOW_CLOSE round=4 shell_pid=20188 engine_pid=24924 port=58796
{"round":4,"mode":"Close","shell_pid":20188,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":24924,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":58796,"port_status":"closed","boot_id":"86f13b8b","old_boot_id":"97a8d3b7","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":5,"mode":"Close","shell_pid":18980,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":17732,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":51976,"boot_id":"8734578d","handshake_published":true,"elapsed_ms":1260}
WAITING_FOR_WINDOW_CLOSE round=5 shell_pid=18980 engine_pid=17732 port=51976
{"round":5,"mode":"Close","shell_pid":18980,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":17732,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":51976,"port_status":"closed","boot_id":"8734578d","old_boot_id":"86f13b8b","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":6,"mode":"Close","shell_pid":13132,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":26092,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":59924,"boot_id":"05edf227","handshake_published":true,"elapsed_ms":1249}
WAITING_FOR_WINDOW_CLOSE round=6 shell_pid=13132 engine_pid=26092 port=59924
{"round":6,"mode":"Close","shell_pid":13132,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":26092,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":59924,"port_status":"closed","boot_id":"05edf227","old_boot_id":"8734578d","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":7,"mode":"Close","shell_pid":24136,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":15720,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":55761,"boot_id":"55194504","handshake_published":true,"elapsed_ms":1217}
WAITING_FOR_WINDOW_CLOSE round=7 shell_pid=24136 engine_pid=15720 port=55761
{"round":7,"mode":"Close","shell_pid":24136,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":15720,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":55761,"port_status":"closed","boot_id":"55194504","old_boot_id":"05edf227","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":8,"mode":"Close","shell_pid":22372,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":21320,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":64133,"boot_id":"95849c99","handshake_published":true,"elapsed_ms":1270}
WAITING_FOR_WINDOW_CLOSE round=8 shell_pid=22372 engine_pid=21320 port=64133
{"round":8,"mode":"Close","shell_pid":22372,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":21320,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":64133,"port_status":"closed","boot_id":"95849c99","old_boot_id":"55194504","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":9,"mode":"Close","shell_pid":27580,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":25464,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":62086,"boot_id":"39de7742","handshake_published":true,"elapsed_ms":1248}
WAITING_FOR_WINDOW_CLOSE round=9 shell_pid=27580 engine_pid=25464 port=62086
{"round":9,"mode":"Close","shell_pid":27580,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":25464,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":62086,"port_status":"closed","boot_id":"39de7742","old_boot_id":"95849c99","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{"round":10,"mode":"Close","shell_pid":24152,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":21828,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":60330,"boot_id":"835b4190","handshake_published":true,"elapsed_ms":1276}
WAITING_FOR_WINDOW_CLOSE round=10 shell_pid=24152 engine_pid=21828 port=60330
{"round":10,"mode":"Close","shell_pid":24152,"shell_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","shell_cim_path":"E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe","parent_pid":8292,"parent_path":"C:\\Windows\\explorer.exe","parent_cim_path":"C:\\Windows\\Explorer.EXE","parent_in_job":false,"engine_pid":21828,"engine_path":"E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","engine_cim_path":"\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe","port":60330,"port_status":"closed","boot_id":"835b4190","old_boot_id":"39de7742","handshake_published_before_action":true,"engine_remaining":0,"shell_remaining":0,"port_open":false,"binary_sha256":"36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f","passed":true}
{
    "mode":  "Close",
    "rounds":  10,
    "actual_token_samples":  11,
    "full_handshake_samples":  11,
    "whole_handshake_json_hits":  0,
    "original_source":  "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\logs\\shell-20261018.log",
    "exact_token_hits":  0,
    "authorization_bearer":  false,
    "sha256":  "5caddfa9e1db101a81c7cda0fdd2aabd97b0224af1af6e40ef40a10536ff083d",
    "binary_sha256_after":  "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f"
}
MATRIX_PASSED mode=Close rounds=10 output=E:\AI_Agent\artifacts\step3\checkpoint-4\20261018T141931529Z-Close
````

</details>

<details>
<summary>最终36fb陈旧握手原始事件节选（完整原件不变）：release-36-stale-handshake-excerpt.json</summary>

````text
{
  "source": "E:\\AI_Agent\\artifacts\\step3\\checkpoint-4\\20261018T141341066Z-KillReady",
  "previous_round_verbatim": {
    "round": 1,
    "mode": "KillReady",
    "shell_pid": 15404,
    "shell_path": "E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe",
    "shell_cim_path": "E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe",
    "parent_pid": 8292,
    "parent_path": "C:\\Windows\\explorer.exe",
    "parent_cim_path": "C:\\Windows\\Explorer.EXE",
    "parent_in_job": false,
    "engine_pid": 26728,
    "engine_path": "E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe",
    "engine_cim_path": "\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe",
    "port": 57014,
    "port_status": "closed",
    "boot_id": "762f81de",
    "old_boot_id": "5a1b269f",
    "handshake_published_before_action": true,
    "engine_remaining": 0,
    "shell_remaining": 0,
    "port_open": false,
    "binary_sha256": "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f",
    "passed": true
  },
  "next_round_selected_verbatim_events": [
    {
      "event": "engine_start_attempt",
      "exe": "\\\\?\\E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe",
      "generation_id": 1,
      "selection_source": "resolved_resource",
      "timestamp": "2026-10-18T14:13:44.058Z"
    },
    {
      "event": "preexisting_handshake_snapshot",
      "generation_id": 1,
      "old_identity": {
        "boot_id": "762f81de",
        "pid": 26728,
        "port": 57014,
        "process_created_at_ms": 1792332821963
      },
      "preexisting_handshake_invalid": null,
      "timestamp": "2026-10-18T14:13:44.058Z"
    },
    {
      "event": "process_identity_recorded",
      "generation_id": 1,
      "pid": 16644,
      "process_created_at_ms": 1792332824075,
      "timestamp": "2026-10-18T14:13:44.081Z"
    },
    {
      "event": "handshake_ignored",
      "generation_id": 1,
      "reason": "foreign_identity",
      "timestamp": "2026-10-18T14:13:44.082Z"
    },
    {
      "boot_id": "caa59c59",
      "event": "handshake_identity_verified",
      "generation_id": 1,
      "pid": 16644,
      "process_created_at_ms": 1792332824075,
      "timestamp": "2026-10-18T14:13:44.690Z"
    },
    {
      "event": "health_verified",
      "generation_id": 1,
      "pid": 16644,
      "port": 59574,
      "timestamp": "2026-10-18T14:13:44.712Z"
    },
    {
      "event": "state_transition",
      "from": "Starting",
      "generation_id": 1,
      "reason": "health_identity_matched",
      "timestamp": "2026-10-18T14:13:44.712Z",
      "to": "Ready"
    }
  ],
  "scope": "derived excerpt; complete original event file remains unchanged"
}
````

</details>

<details>
<summary>原始C盘源日志/完整DOM扫描后再复制的审计收据：release-36-source-audit.json</summary>

````text
{
  "scan_original_before_copy": true,
  "records": [
    {
      "source": "C:/Users/Administrator/AppData/Local/SpectrumAgent/logs/shell-20261018.log",
      "bytes": 2105736,
      "sha256": "e423fd5505ca1c9477a7185c66d517d97169dc5293105c51e832beea01dd69a0",
      "json_lines": 7208,
      "actual_token_samples": 4,
      "full_handshake_samples": 2,
      "exact_token_hits": 0,
      "whole_handshake_hits": 0,
      "authorization_bearer": false
    },
    {
      "source": "C:/Users/Administrator/AppData/Local/SpectrumAgent/logs/engine-20261018.jsonl",
      "bytes": 890324,
      "sha256": "5faeb31ec173a526ffa873fd224c988664e5554b25a6c6016268f6cdd999831e",
      "json_lines": 5030,
      "actual_token_samples": 4,
      "full_handshake_samples": 2,
      "exact_token_hits": 0,
      "whole_handshake_hits": 0,
      "authorization_bearer": false
    },
    {
      "source": "C:/Users/Administrator/AppData/Local/SpectrumAgent/acceptance/dom-14352.jsonl",
      "bytes": 629689,
      "sha256": "2f99b1e764b2c555ea53198e885681c676ce89967db219f27732cd78176336d3",
      "json_lines": 450,
      "actual_token_samples": 4,
      "full_handshake_samples": 2,
      "exact_token_hits": 0,
      "whole_handshake_hits": 0,
      "authorization_bearer": false
    },
    {
      "source": "C:/Users/Administrator/AppData/Local/SpectrumAgent/acceptance/dom-19480.jsonl",
      "bytes": 7354,
      "sha256": "b3c4a55a20e8c84171a303507d8c101a2506f9f3bcd74298d6cbf268d2539175",
      "json_lines": 9,
      "actual_token_samples": 4,
      "full_handshake_samples": 2,
      "exact_token_hits": 0,
      "whole_handshake_hits": 0,
      "authorization_bearer": false
    },
    {
      "source": "C:/Users/Administrator/AppData/Local/SpectrumAgent/acceptance/dom-21520.jsonl",
      "bytes": 6646,
      "sha256": "2bfb0d06724fcf50b1a58e3a0c82a7054edc668a2a95b6ed7c440284e135bb18",
      "json_lines": 8,
      "actual_token_samples": 4,
      "full_handshake_samples": 2,
      "exact_token_hits": 0,
      "whole_handshake_hits": 0,
      "authorization_bearer": false
    },
    {
      "source": "C:/Users/Administrator/AppData/Local/SpectrumAgent/acceptance/dom-11612.jsonl",
      "bytes": 2742,
      "sha256": "4e9865436ed62dc6b26caa9430b801b32cbe5d26a5165d769a8f91e41a6770db",
      "json_lines": 2,
      "actual_token_samples": 4,
      "full_handshake_samples": 2,
      "exact_token_hits": 0,
      "whole_handshake_hits": 0,
      "authorization_bearer": false
    }
  ]
}
````

</details>

<details>
<summary>提交后的只读全量复核及最终release三段计时：release-36-analysis-committed-output.txt</summary>

````text
{
  "analysis": "E:\\AI_Agent\\artifacts\\step3\\checkpoint-4\\release-36-analysis-20261018T150041946516Z.json",
  "shell_sha256": "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f",
  "matrix": {
    "KillReady": 10,
    "KillStarting": 10,
    "Close": 10
  },
  "documents": [
    {
      "path": "artifacts\\step3\\checkpoint-4\\release-36-source-snapshot\\dom-11612.jsonl",
      "callback_records": 2,
      "complete_documents": 2,
      "phases": {
        "Starting": 1,
        "Failed": 1
      },
      "max_localStorage_entries": 0,
      "max_sessionStorage_entries": 0,
      "has_real_smoke_metrics": false
    },
    {
      "path": "artifacts\\step3\\checkpoint-4\\release-36-source-snapshot\\dom-14352.jsonl",
      "callback_records": 450,
      "complete_documents": 450,
      "phases": {
        "Starting": 7,
        "Ready": 443
      },
      "max_localStorage_entries": 0,
      "max_sessionStorage_entries": 0,
      "has_real_smoke_metrics": true
    },
    {
      "path": "artifacts\\step3\\checkpoint-4\\release-36-source-snapshot\\dom-19480.jsonl",
      "callback_records": 9,
      "complete_documents": 9,
      "phases": {
        "Starting": 8,
        "Failed": 1
      },
      "max_localStorage_entries": 0,
      "max_sessionStorage_entries": 0,
      "has_real_smoke_metrics": false
    },
    {
      "path": "artifacts\\step3\\checkpoint-4\\release-36-source-snapshot\\dom-21520.jsonl",
      "callback_records": 8,
      "complete_documents": 8,
      "phases": {
        "Starting": 7,
        "Failed": 1
      },
      "max_localStorage_entries": 0,
      "max_sessionStorage_entries": 0,
      "has_real_smoke_metrics": false
    }
  ],
  "timing": {
    "engine_ready_from_pre_spawn_ms": 1353.161,
    "interactive_from_pre_spawn_ms": 1400.161,
    "first_smoke_from_pre_spawn_ms": 35917.161,
    "manual_wait_before_smoke_ms": 34386.0,
    "smoke_round_trip_ms": 131.0,
    "metrics": {
      "bands": 8,
      "elapsed_ms": 125.013,
      "nan_ratio": 0.0,
      "reflectance_range": [
        -1.5275289241381491,
        1.5275289241381491
      ],
      "shape": [
        8,
        8,
        8
      ]
    },
    "cold_definition": "new WebView profile; OS file cache not purged",
    "clean_vm": false
  },
  "all_allowed_transition_pairs": 7
}
````

</details>

<details>
<summary>Starting→Stopping core harness（不是TauriUI证据）：starting-stop-probe-output.txt</summary>

````text
{
  "command": [
    "E:\\AI_Agent\\src-tauri\\target\\debug\\supervisor-probe.exe",
    "--resource-exe",
    "E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe",
    "--injected-exe",
    "E:\\AI_Agent\\artifacts\\step3\\checkpoint-4\\temp\\timeout-stub\\app.exe"
  ],
  "scope": "core acceptance harness; not Tauri single-instance evidence",
  "exit_code": 0,
  "transitions": [
    {
      "event": "state_transition",
      "from": "Starting",
      "generation_id": 1,
      "reason": "application_close",
      "timestamp": "2026-10-18T14:32:50.035Z",
      "to": "Stopping"
    }
  ],
  "app_exit": 1
}
````

</details>

<details>
<summary>两个最终exe的mt命令、完整XML、SHA256及LongPathsEnabled：rt-manifest-final-output.txt</summary>

````text
& 'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\mt.exe' '-inputresource:E:\AI_Agent\src-tauri\target\release\spectrum-agent.exe;#1' '-out:E:\AI_Agent\artifacts\step3\staging-reports\20261018T140935128Z-shell.manifest.xml'
Microsoft (R) Manifest Tool

Copyright (c) Microsoft Corporation. 

All rights reserved.

<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">  <dependency><dependentAssembly>  <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"></assemblyIdentity>  </dependentAssembly></dependency>  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges><requestedExecutionLevel level="asInvoker" uiAccess="false"></requestedExecutionLevel></requestedPrivileges></security></trustInfo>  <application xmlns="urn:schemas-microsoft-com:asm.v3"><windowsSettings><longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware></windowsSettings></application>  </assembly>
{
  "exe": "E:\\AI_Agent\\src-tauri\\target\\release\\spectrum-agent.exe",
  "sha256": "36FBC3DF1D220D51C2A1B9E6D347A0EBDB99EB6FA6318D20A18F82D1B9DA713F",
  "manifest": "E:\\AI_Agent\\artifacts\\step3\\staging-reports\\20261018T140935128Z-shell.manifest.xml",
  "manifest_sha256": "36E8D77BAC798D5C4BBF6CF3547F443A9E4074A54621F42E3C60633E8C994A93",
  "longPathAware": true,
  "asInvoker": true,
  "commonControlsV6": true
}
& 'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\mt.exe' '-inputresource:E:\AI_Agent\src-tauri\target\release\resources\backend\app.exe;#1' '-out:E:\AI_Agent\artifacts\step3\staging-reports\20261018T140935128Z-engine.manifest.xml'
Microsoft (R) Manifest Tool

Copyright (c) Microsoft Corporation. 

All rights reserved.

<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"></requestedExecutionLevel>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{e2011457-1546-43c5-a5fe-008deee3d3f0}"></supportedOS>
      <supportedOS Id="{35138b9a-5d96-4fbd-8e2d-a2440225f93a}"></supportedOS>
      <supportedOS Id="{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}"></supportedOS>
      <supportedOS Id="{1f676c76-80e1-4239-95bb-83d0f6d0da78}"></supportedOS>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"></supportedOS>
    </application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
    </windowsSettings>
  </application>
  <dependency>
    <dependentAssembly>
      <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"></assemblyIdentity>
    </dependentAssembly>
  </dependency>
</assembly>
{
  "exe": "E:\\AI_Agent\\src-tauri\\target\\release\\resources\\backend\\app.exe",
  "sha256": "3F62C1895152A01EB0A92B61A733985C15CA7888D233FD9408CA5B9DC61D7703",
  "manifest": "E:\\AI_Agent\\artifacts\\step3\\staging-reports\\20261018T140935128Z-engine.manifest.xml",
  "manifest_sha256": "0EE298C1B1FE6D499988B60309DBC208E90C53C061FDEEA39E63F6FFCF153D79",
  "longPathAware": true,
  "asInvoker": true,
  "commonControlsV6": true
}
LongPathsEnabled=0; over_260_functional_test=UNVERIFIED_VM
````

</details>

<details>
<summary>最终36fb stderr原文：release-36.stderr.txt</summary>

````text
[1018/224118.953:ERROR:ui\gfx\win\window_impl.cc:172] Failed to unregister class Chrome_WidgetWin_0. Error = 1412
````

</details>

<details>
<summary>旧证据封存/新批次全量复核：engine-batch-delivery-output.txt</summary>

````text
sealed_old_evidence_unchanged=true new_product_manifest_match=true
````

</details>

<details>
<summary>三锁、进程/端口、资源未入库等授权只读复核：delivery-readonly-authorized-output.txt</summary>

````text
COMMAND: Get-FileHash three lock files
E:\AI_Agent\requirements-lock.txt SHA256=58E24B59DA34461A17FD942B4047071E42B5120B3D474BA976A7E28535D40BCC
E:\AI_Agent\package-lock.json SHA256=5122B8E2DBD8B84CE2D7365088D01E657DE7C178037533194AB17504EB7ECB14
E:\AI_Agent\src-tauri\Cargo.lock SHA256=19677A37D746C188184F4948D8BC5739759BE755E3AFEAA2C9F58471FEC13B12
COMMAND: Get-CimInstance Win32_Process (own executable paths only)
[]
COMMAND: git ls-files forbidden product directories
[]
COMMAND: Test-Path E-drive NSIS cache location / configured bundle mode
{
  "nsis_cache": false,
  "configured_local_tools_dir": true
}
COMMAND: git diff --name-only HEAD -- artifacts/step2
COMMAND: closed matrix and final UI ports via Get-NetTCPConnection
{
  "observed_ports": [
    49923,
    50134,
    50282,
    51500,
    51976,
    53187,
    53302,
    53976,
    55761,
    56687,
    56792,
    57014,
    57548,
    58004,
    58770,
    58796,
    59574,
    59924,
    60330,
    61586,
    62086,
    64133
  ],
  "current_matching_listeners": []
}
````

</details>

<details>
<summary>本机已安装Tauri CLI bundle --help原始输出：tauri-bundle-help-output.txt</summary>

````text

> spectrum-agent@0.1.0 tauri
> tauri bundle --help

Generate bundles and installers for your app (already built by `tauri build`). This run `build.beforeBundleCommand` before generating the bundles and installers of your app.

Usage: npm run tauri bundle [OPTIONS]

Options:
  -d, --debug
          Builds with the debug flag

  -v, --verbose...
          Enables verbose logging

  -b, --bundles [<BUNDLES>...]
          Space or comma separated list of bundles to package
          
          [possible values: msi, nsis]

  -c, --config <CONFIG>
          JSON strings or paths to JSON, JSON5 or TOML files to merge with the default configuration file
          
          Configurations are merged in the order they are provided, which means a particular value overwrites previous values when a config key-value pair conflicts.
          
          Note that a platform-specific file is looked up and merged with the default file by default (tauri.macos.conf.json, tauri.linux.conf.json, tauri.windows.conf.json, tauri.android.conf.json and tauri.ios.conf.json) but you can use this for more specific use cases such as different build flavors.

  -f, --features [<FEATURES>...]
          Space or comma separated list of features, should be the same features passed to `tauri build` if any

  -t, --target <TARGET>
          Target triple to build against.
          
          It must be one of the values outputted by `$rustc --print target-list` or `universal-apple-darwin` for an universal macOS application.
          
          Note that compiling an universal macOS application requires both `aarch64-apple-darwin` and `x86_64-apple-darwin` targets to be installed.

      --ci
          Skip prompting for values
          
          [env: CI=]

      --skip-stapling
          Skip stapling the notarization ticket onto the app and do not wait for notarization to finish.
          
          Gatekeeper will look for stapled tickets to tell whether your app was notarized without reaching out to Apple's servers which is helpful in offline environments.
          
          Enabling this option will also result in `tauri build` not waiting for notarization to finish which is helpful for the very first time your app is notarized as this can take multiple hours. On subsequent runs, it's recommended to disable this setting again.

      --no-sign
          Skip code signing during the build or bundling process.
          
          Useful for local development and CI environments where signing certificates or environment variables are not available or not needed.

      --no-binary-patching
          Skip patching the main executable with bundle type information.
          
          The patching rewrites the binary in place, invalidating an existing code signature. Skipping it preserves an already-signed binary at the cost of per-bundle-type updater support (only relevant when shipping multiple bundle types per platform).

  -h, --help
          Print help (see a summary with '-h')

  -V, --version
          Print version
````

</details>

### 最终36fb逐轮PID/端口核验（原始完整行见上方控制台）

| 模式 | 轮 | 外壳PID | 引擎PID | 端口/状态 | 引擎残留 | 外壳残留 | 父级Job |
|---|---:|---:|---:|---|---:|---:|---|
| KillReady | 1 | 15404 | 26728 | 57014 closed | 0 | 0 | False |
| KillReady | 2 | 5676 | 16644 | 59574 closed | 0 | 0 | False |
| KillReady | 3 | 24628 | 27076 | 57548 closed | 0 | 0 | False |
| KillReady | 4 | 17192 | 21144 | 61586 closed | 0 | 0 | False |
| KillReady | 5 | 22068 | 16236 | 53976 closed | 0 | 0 | False |
| KillReady | 6 | 21544 | 3384 | 53187 closed | 0 | 0 | False |
| KillReady | 7 | 23040 | 10292 | 50134 closed | 0 | 0 | False |
| KillReady | 8 | 16236 | 4228 | 58770 closed | 0 | 0 | False |
| KillReady | 9 | 1108 | 26760 | 49923 closed | 0 | 0 | False |
| KillReady | 10 | 24088 | 19756 | 50282 closed | 0 | 0 | False |
| KillStarting | 1 | 24820 | 23044 | null / unpublished_before_kill | 0 | 0 | False |
| KillStarting | 2 | 23880 | 27580 | null / unpublished_before_kill | 0 | 0 | False |
| KillStarting | 3 | 23092 | 13188 | null / unpublished_before_kill | 0 | 0 | False |
| KillStarting | 4 | 24588 | 25668 | null / unpublished_before_kill | 0 | 0 | False |
| KillStarting | 5 | 15108 | 26740 | null / unpublished_before_kill | 0 | 0 | False |
| KillStarting | 6 | 24556 | 20252 | null / unpublished_before_kill | 0 | 0 | False |
| KillStarting | 7 | 26232 | 16920 | null / unpublished_before_kill | 0 | 0 | False |
| KillStarting | 8 | 24924 | 15948 | null / unpublished_before_kill | 0 | 0 | False |
| KillStarting | 9 | 18968 | 10084 | null / unpublished_before_kill | 0 | 0 | False |
| KillStarting | 10 | 15896 | 19848 | null / unpublished_before_kill | 0 | 0 | False |
| Close | 1 | 7588 | 1564 | 51500 closed | 0 | 0 | False |
| Close | 2 | 27464 | 26232 | 56687 closed | 0 | 0 | False |
| Close | 3 | 26388 | 17844 | 53302 closed | 0 | 0 | False |
| Close | 4 | 20188 | 24924 | 58796 closed | 0 | 0 | False |
| Close | 5 | 18980 | 17732 | 51976 closed | 0 | 0 | False |
| Close | 6 | 13132 | 26092 | 59924 closed | 0 | 0 | False |
| Close | 7 | 24136 | 15720 | 55761 closed | 0 | 0 | False |
| Close | 8 | 22372 | 21320 | 64133 closed | 0 | 0 | False |
| Close | 9 | 27580 | 25464 | 62086 closed | 0 | 0 | False |
| Close | 10 | 24152 | 21828 | 60330 closed | 0 | 0 | False |

### 最终36fb主例完整迁移序列（从原日志逐行提取）

````json
[
  {
    "event": "state_transition",
    "from": "Starting",
    "generation_id": 1,
    "reason": "health_identity_matched",
    "timestamp": "2026-10-18T14:36:33.726Z",
    "to": "Ready"
  },
  {
    "event": "state_transition",
    "from": "Ready",
    "generation_id": 1,
    "reason": "engine_failure",
    "timestamp": "2026-10-18T14:38:00.134Z",
    "to": "Failed"
  },
  {
    "event": "state_transition",
    "from": "Failed",
    "generation_id": 2,
    "reason": "retry_after_cleanup",
    "timestamp": "2026-10-18T14:38:59.374Z",
    "to": "Starting"
  },
  {
    "event": "state_transition",
    "from": "Starting",
    "generation_id": 2,
    "reason": "health_identity_matched",
    "timestamp": "2026-10-18T14:39:00.064Z",
    "to": "Ready"
  },
  {
    "event": "state_transition",
    "from": "Ready",
    "generation_id": 2,
    "reason": "application_close",
    "timestamp": "2026-10-18T14:41:18.734Z",
    "to": "Stopping"
  }
]
````

<!-- RAW_OUTPUTS_END -->

## 遇到的问题

1. **真实失败先存原文**：首次最终SHA的Ready矩阵在第5轮失败，前4轮不计作最终10轮。原始引擎启动报HANDSHAKE_DELETE_FAILED、实际退出1，已落盘 explorer-context-20261018T141127465Z/；它不是旧exit70。只读受控探针做1000次删除：Get-Content读者930次WinError32，显式FileShare.ReadWrite|Delete读者0次。证明测试读者存在干扰风险；原故障未记录WinError细节，**不宣称唯一根因已定位**。只修测试控制器共享删除模式，未改封版引擎；之后最终SHA三组全部重新跑满10轮。失败原文、共享探针和最终证据并存。
2. **候选SHA改变必须重验**：第一次Canonical A7候选完成过矩阵，源码提交后再构建发现SHA变为36fb，SHA守卫按预期阻止沿用。pefile只读探针对比全文件：24个不同字节全部落在COFF/debug时间戳和PDB GUID，.text/.data/.pdata/.rsrc/.reloc相同，未解释偏移0；触发重链接的原因仍未验证。没有以“语义相同”跳过验收，最终矩阵/失败案例/真实UI/DOM/计时/manifest均按36fb重验。后续bundle不再重建、不patch二进制。
3. **上下文可见文件不同**：工具进程与Explorer进程读同一个字面C盘数据路径曾得到不同内容，双侧只读探针均为同用户/会话、GetCurrentPackageFullName=15700。原因未验证，不猜测UAC/MSIX。最终矩阵控制器经实际Explorer上下文执行，扫描原始源后复制到共享E盘；父进程与Job归属逐轮实测。早期Shell.Application新实例未证明Explorer父进程、CIM标量/数组形状及路径前缀问题的尝试保留，不计入最终矩阵。
4. **release1412复现**：最终release stderr原文为 `[1018/224118.953:ERROR:ui\gfx\win\window_impl.cc:172] Failed to unregister class Chrome_WidgetWin_0. Error = 1412`。关闭后本轮进程与端口均已退出；原因未定位，不猜测归因。旧exit70保持未验证，不能用测试22+1通过倒推原因。
5. **测试/工具开发中的真实失败**：未安装psutil（只读探针ModuleNotFoundError），改用标准库ctypes，不新增依赖；失败脚本原断言只容许一条handshake_error，实际startup/finally两条，改为startup恰好一条且全部PID/错误族一致；首次失败后遗留fixture仅在字节精确相同条件下测试卫生清理，单独留原文。首次分析器把UTF-16LE BOM的PowerShell5 Tee原始JSON当UTF-8读取报错，改为识别BOM；没有重写原始证据编码。fmt开发期差异、过期窗口几何错误及重选窗口后的重试均不当作产品通过证据。
6. 一次猜测 `C:\Program Files\PowerShell\7\pwsh.exe` 导致找不到路径的系统提示，已关闭；后续使用只读探针查到的真实解释器路径。模板只读GET曾遇unexpectedEOF，未关闭证书验证、未声称取得完整上游模板哈希。交付只读CIM在沙箱内返回拒绝访问，授权上下文重跑成功；保留两份原始输出，不是自动审批拒绝。
7. **未完成项**：Stopping对话条最终DOM未捕获；全仓Git干净条件未达到；NSIS工具/完整模板/安装包、安装卸载、断网安装及VM三段冷启动/restore/>260路径均未执行。等待批准的安装目录提案只改默认程序目录，不动数据目录。不能用脚本测试卫生清理冒充产品自动清理。

用户三项未跟踪内容：`.runtime/`、`光谱平台_阶段一_代码审查与进度分析_20261018.md`、`光谱数据AI-Agent处理平台_阶段一技术选型_定稿v1.1_1792327262075_csvb.md`。不擅自提交、删除或忽略。最终状态另存 git-status-after-evidence-output.txt；旧第2步证据字节不改。

## 下一步打算

停在本检查点等负责人复核；明确批准NSIS工具下载及默认程序目录后，使用现有36fb exe进行bundle，核对打包前后SHA和资源全清单，再做宿主机安装/卸载及干净VM验收，并补足Stopping对话条渲染证据。

两项待批准的具体内容（由用户“安装类命令先列清单、等确认”及“目录约定变动先说明”要求触发）：

- 下载NSIS **3.13**、nsis_tauri_utils **0.5.3**、微软官方WebView2 x64 Evergreen离线安装器，缓存为 **E:\AI_Agent\src-tauri\target\.tauri**；后者版本/签名/SHA将在下载后实测归档，不预写版本号。不开TLS绕过、不新增npm/Cargo/Python依赖。
- currentUser上游默认 `$LOCALAPPDATA\${PRODUCTNAME}` 与数据根重叠；提案仅将默认安装位置改成 **%LOCALAPPDATA%\Programs\SpectrumAgent**，数据仍在 **%LOCALAPPDATA%\SpectrumAgent**。一行差异已归档 nsis-install-directory-proposal.diff。完整上游模板/哈希及实际生成行为未验证，不提前报通过。

待批准后的拟执行命令（**尚未执行**；模板配置通过 `--config` 指定，将另存精确配置）：

```powershell
& .\frontend.ps1 run tauri -- bundle --bundles nsis --no-binary-patching --features custom-protocol
```

本机CLI `bundle --help`已实测确认只打包已构建程序，`--no-binary-patching`跳过原地改写exe。test-probes不启用，专用probe二进制不得进安装包；CLI源码required-features过滤证明只是准备证据，实际NSIS内容仍待包产出后核对。

上游依据：[CLI 2.12.3 NSIS实现](https://raw.githubusercontent.com/tauri-apps/tauri/tauri-cli-v2.12.3/crates/tauri-bundler/src/bundle/windows/nsis/mod.rs)、[NSIS模板](https://raw.githubusercontent.com/tauri-apps/tauri/tauri-cli-v2.12.3/crates/tauri-bundler/src/bundle/windows/nsis/installer.nsi)、[required-features过滤](https://raw.githubusercontent.com/tauri-apps/tauri/tauri-cli-v2.12.3/crates/tauri-cli/src/interface/rust.rs)。本轮报告未将上游推断写成已实测的安装结果。
