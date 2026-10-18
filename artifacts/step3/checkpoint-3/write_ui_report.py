"""Build the checkpoint report from preserved original outputs; never rewrites earlier reports."""
import json
import re
from pathlib import Path

CP = Path(__file__).resolve().parent
ROOT = CP.parents[2]
tests = (CP / "host-tests-head-output.txt").read_text(encoding="utf-8")
runtime, docs = tests.split("Doc-tests", 1)
assert sum(map(int, re.findall(r"test result: ok\. (\d+) passed", runtime))) == 22
assert "test result: ok. 1 passed; 0 failed" in docs
scope = json.loads((CP / "delivery-scope-receipt.json").read_text(encoding="utf-8"))
audit = json.loads((CP / "original-source-token-audit.json").read_text(encoding="utf-8"))
shell_lines = (CP / "original-log-snapshot-20261018-1744/shell-20261018.log").read_text(encoding="utf-8").splitlines()
shell = [json.loads(line) for line in shell_lines]
current = [row for row in shell if row["timestamp"] >= "2026-10-18T09:30:39.000Z"]
allowed = {("Starting", "Ready"), ("Starting", "Failed"), ("Starting", "Stopping"),
           ("Ready", "Failed"), ("Ready", "Stopping"), ("Failed", "Starting"), ("Failed", "Stopping")}
assert all((row["from"], row["to"]) in allowed for row in current if row["event"] == "state_transition")
assert not any(row.get("to") == "app_exit" for row in current)


def block(value):
    return "```text\n" + (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)) + "\n```\n\n"


text = r"""## 完成到哪一步

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

本轮代码构建与正式复跑命令（实际输出分段完整附后）：

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

fmt --check exit=0、输出为空（host-fmt-delivery-output.txt），clippy exit=0 无 warning；
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

"""
# Keep literal Windows paths single-backslash, including in this generator's raw string.
text = text.replace("\\\\", "\\")
for title, name in [
    ("clippy（最终代码）", "host-clippy-delivery-output.txt"),
    ("Rust HEAD 全量（含预期 compile-fail 原文）", "host-tests-head-output.txt"),
    ("前端代次测试", "frontend-state-tests-output.txt"),
    ("tsc + Vite（最终代码）", "frontend-build-delivery-output.txt"),
    ("reqwest 全功能目标树", "reqwest-features-delivery-output.txt"),
    ("Canonical 暂存", "canonical-staging-fixed-output.txt"),
    ("强制重新优化缓存的 Tauri dev", "tauri-dev-cold-optimizer-output.txt"),
    ("单实例", "ui-single-instance-ready.json"),
    ("单实例进程数", "ui-single-instance-processes.json"),
    ("未知请求", "ui-unknown-input.txt"),
    ("Ctrl+Enter 冒烟完成", "ui-smoke-keyboard-complete.txt"),
    ("Failed 与路径/禁用", "ui-engine-exit-failed-settled.txt"),
    ("最终重试清空结果", "ui-final-retry-ready.txt"),
    ("最终冒烟完成", "ui-final-smoke-complete.txt"),
    ("PID/端口与残留握手", "ui-final-process-port-evidence.json"),
    ("原始日志/实际token审计", "original-source-token-audit.json"),
    ("旧产物逐项核对", "old-product-readonly-verify-output.txt"),
]:
    text += "### " + title + "\n\n" + block((CP / name).read_text(encoding="utf-8"))
selected = [r for r in current if r["event"] in {
    "shell_started", "single_instance_lock_acquired", "process_created_suspended", "job_assigned",
    "thread_resumed_and_closed", "handshake_identity_verified", "health_verified", "state_transition",
    "smoke_requested", "smoke_finished", "window_hidden", "window_shown", "single_instance_activation",
    "activation_requested", "generation_cleanup", "app_exit", "host_cleanup_completed"}]
text += "### 实际外壳关键原始日志（完整未删节源文件已归档）\n\n"
text += block("\n".join(line for line, row in zip(shell_lines, shell) if row in selected))
text += r"""## 遇到的问题

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
"""
with (CP / "UI-REPORT.md").open("x", encoding="utf-8", newline="\n") as out:
    out.write(text)
print("UI-REPORT.md written; runtime_tests=22 compile_fail_tests=1 frontend_race_tests=2")
