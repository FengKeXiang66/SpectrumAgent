"""Append-only Chinese checkpoint report from already archived, separately scoped evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

ROOT = Path(r"E:\AI_Agent")
B = Path(__file__).resolve().parent
F = B / "final-canonical-20261019"


def load(path):
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"))


def link(path):
    return f"[{path.name}]({path.as_posix()})"


def text(path):
    raw = path.read_bytes()
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")


def main():
    candidate = load(F / "candidate.json")
    analysis = load(sorted(F.glob("analysis-*.json"))[-1])
    package = load(sorted(F.glob("package-verification-*.json"))[-1])
    uninstall = load(F / "host-uninstall-result.json")
    bundle = load(F / "bundle-idle-execution.json")
    assert bundle["exit_code"] == 0
    timing = analysis["timing"]
    generation = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    report = f'''## 完成到哪一步

检查点 4 的生产态修正、最终 release 本机验收和 NSIS 本机安装/卸载已完成，提交负责人复核。当前交付候选为 {link(ROOT / 'artifacts/step4/setup.exe')}（{bundle['setup_bytes']:,} 字节，SHA256 `{bundle['setup_sha256'].lower()}`）。**未做干净 VM 实机验收，第 2 步继续“待实机验证”，第 3/4 步均不声明最终关闭。**

外壳 exe 已显式使用 `--features custom-protocol` **重新编译**。最终源码提交 `{candidate['source_commit']}`，外壳 {candidate['shell_bytes']:,} 字节、SHA256 `{candidate['shell_sha256']}`；本报告生成提交 `{generation}`，二者分列。最终 Canonical 重建后产生 22a13e6a 候选，所有最终矩阵、真实 UI、DOM、计时、manifest 和安装包证据均重新以此 SHA 采集。此前 cba991aa 候选及更旧 features=[] 批次保留为历史，不能冒充最终发布态证据。

引擎批次始终为 {link(Path(candidate['engine_manifest']))}；app.exe SHA256 `{candidate['engine_sha256']}`。artifact_source_commit=`{candidate['engine_artifact_source_commit']}`；manifest_generator_commit=`{candidate['engine_manifest_generator_commit']}`。Canonical 整树 **544 文件、255,564,789 字节**，逐路径/字节数/SHA256 匹配；_internal 543 文件。封版引擎、三份 lock、旧 REPORT/manifest/原始输出均未改写。

当前 Hyper-V/VM 仅引用负责人更新：Hyper-V Enabled、vmms 运行、模块可用；pristine=`f7ea81cf-6c3a-4823-9a7b-5fe77f4c2300`，2026-10-18 15:41:03。本轮没有恢复检查点、修改 VM、安全策略、系统代理或用户/系统 PATH。旧 exit code=70 内部原因继续“未验证”。

## 命令与原始输出

本批次目录名保留首次工作日期 20261018，最终验收继续于 2026-10-19；逐事件使用实际 UTC 时间，不改写旧时间戳。以下附录完整嵌入命令输出；大体积原始日志、完整 DOM 和逐文件清单保留为独立原件，可按证据清单 SHA 复核。

实际工具路径：Node `E:\\AI_Agent\\.toolchains\\node24.19.0-npm10.8.2\\node.exe`；Cargo `C:\\Users\\Administrator\\.cargo\\bin\\cargo.exe`。CARGO_HOME=`E:\\AI_Agent\\.cargo-home`，CARGO_TARGET_DIR=`E:\\AI_Agent\\src-tauri\\target`。frontend.ps1 实际 TEMP/TMP 为 `E:\\AI_Agent\\artifacts\\step3\\checkpoint-3\\temp`（覆盖调用会话的 TEMP），未落 C 盘。没有新增依赖。

```powershell
$env:CARGO_HOME='E:\\AI_Agent\\.cargo-home'
$env:CARGO_TARGET_DIR='E:\\AI_Agent\\src-tauri\\target'
$env:CARGO_NET_OFFLINE='true'
& 'C:\\Users\\Administrator\\.cargo\\bin\\cargo.exe' fmt --manifest-path E:\\AI_Agent\\src-tauri\\Cargo.toml --check
& 'C:\\Users\\Administrator\\.cargo\\bin\\cargo.exe' clippy --manifest-path E:\\AI_Agent\\src-tauri\\Cargo.toml --all-targets --all-features --locked --offline -- -D warnings
& 'C:\\Users\\Administrator\\.cargo\\bin\\cargo.exe' test --manifest-path E:\\AI_Agent\\src-tauri\\Cargo.toml --all-features --locked --offline -- --nocapture --test-threads=1
& .\\frontend.ps1 run tauri -- build --no-bundle --features custom-protocol --runner C:\\Users\\Administrator\\.cargo\\bin\\cargo.exe
Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:http_proxy,Env:https_proXY,Env:ALL_PROXY -ErrorAction SilentlyContinue
$env:NO_PROXY='*'
& .\\frontend.ps1 run tauri -- bundle --bundles nsis --no-binary-patching --features custom-protocol --verbose
```

fmt 退出 0（空 stdout 有单独执行收据）；clippy 无 warning；22 个运行时测试及 1 个 compile-fail 文档测试通过。E0308 是拒绝第三路径的预期编译错误。两次本轮生产构建均实际跑 strict `tsc --noEmit && vite build`。最终 bin/lib/build-script 指纹均为 `["custom-protocol"]`，不含 test-probes；安装内容中无 supervisor-probe/stub。

**下载与校验。** 官方 CDN 两请求使用负责人文件中的完整 URL 原串，curl 显式 `--noproxy '*'`，进程代理变量清除、NO_PROXY=*，均实返 200；系统 WinINET 127.0.0.1:7897 配置未改。此前直连 github.com 的 HTTP000/curl28、代理通道的 EOF/TLS 失败原文保留，不把其错误称作 CDN 下载结果。缓存入口为 `target/tauri/`，CLI 实际工具根为 `target/.tauri/NSIS`，由上游检查逻辑及真实 makensis 命令交叉确认。CLI 未报工具缺失且实际调用 makensis v3.13。

| 工具 | 字节数 | SHA1 固定锚点 | SHA256 / 签名 |
|---|---:|---|---|
| nsis-3.13.zip | 2,363,925 | DB14F8AF2EA346B786C6AE19343F61AAF5E09B8E | BA63DFFC4410EE89193E1CB5A41989991BD77C61068DA17E3156D136B7B0B3D8 |
| nsis_tauri_utils.dll | 34,304 | 75197FEE3C6A814FE035788D1C34EAD39349B860 | 5BA143B5DB4A87D32D6E7802E033330AAE56CBCEABE0D1E3BA41948385AD4709；NotSigned |
| WebView2 x64 离线安装器 | 214,156,024 | 以 Authenticode 验签 | 0625FB5C1E75BE58A164E14F95AA58A3E5BADB859B3D17C952385F3E4A9FF3E8；Valid，Microsoft Corporation |

NSIS.exe / makensis.exe 实测 NotSigned，不冒称微软签名，使用批准的官方 SHA 锚点。WebView2 交 CLI 下载/缓存核验，真实日志 proxy=None、微软 HEAD302→200、GET200；全过程不关 TLS/吊销校验、不用镜像。外层安装器版本 1.3.287.9；已签名载荷的 XML 明确 WebView2 Runtime **155.0.4283.62**，不是把外层版本当运行时版本。{link(B / 'WEBVIEW2-RUNTIME.md')} 及载荷 XML 原输出为依据；VM 注册表 pv 核对未执行。

**模板与布局。** CLI2.12.3 原生二进制中完整内嵌模板原件 33,780 字节，SHA256 c36f2746493870577c584db49ca99cf5ee77ab211d893ff6851ccc4375866cf3；在线 tag 全文字节比对“未验证”，不混称完成。唯一变更第 524 行 currentUser 默认目录为 `$LOCALAPPDATA\\Programs\\${{PRODUCTNAME}}`；新模板 33,789 字节，SHA256 e78b55ce753c8ef4ff99554a9fd4f8b29c287cda890b5aad64ee8ee3e9205a89。第509行占位守卫、perMachine、卸载段保持。配置仅引用相对模板路径；installMode=currentUser，offlineInstaller，不用 hooks。后续升级须重新提取、算 SHA、diff 后重施同一处修改。

专用生产 FaultFixture 的源码暂存清单为 543 文件、fault_fixture=true，标记在资源树外；只缺 python312.dll。失败页实际从内嵌资源加载，退出码4294967295，中文握手/日志路径与诊断按钮均可见；从引擎尝试启动至 Failed DOM **{package['dedicated_custom_protocol_fault_fixture']['failed_page_after_attempt_ms']} ms**，实际 exe 路径见复核 JSON。然后重新 Canonical 暂存 544 文件并重建最终22a13e6a，资源全量无差异。原样保留首次 FaultFixture 输出中旧 DLL 残留的探针，未把那次误算成有效缺 DLL 验收。

**最终三组矩阵。** 每组10轮；控制器通过现有 Explorer COM broker 直接创建 release 外壳，真实父进程 Explorer、IsProcessInJob(parent)=false。PID、CIM 与 QueryFullProcessImageName 完整路径双核验；正常关窗为真实窗口 Alt+F4。Starting 组无已发布端口，记录“未发布”，不写成测试关闭某个不存在的端口。所有行均绑定最终22a13e6a，残留进程为0。

| 模式 | 轮次 | 外壳PID | 引擎PID | 端口 | 结果 |
|---|---:|---:|---:|---|---|
'''
    for matrix in analysis["matrix"]:
        for r in matrix["rows"]:
            report += f"| {matrix['mode']} | {r['round']} | {r['shell_pid']} | {r['engine_pid']} | {r['port'] if r['port'] else '未发布'} | 进程0；{'端口关闭' if r['port'] else '握手未发布'} |\n"
    report += f'''
**真实 UI、审计与计时。** 最终 release 完整 DOM **{sum(analysis['production_dom_phases'].values())} 份**：{json.dumps(analysis['production_dom_phases'], ensure_ascii=False)}。每份保存 documentElement.outerHTML、输入活值/disabled、完整 localStorage/sessionStorage，全部真实 URL=`http://tauri.localhost/`，脚本为本地 assets；无1420监听，恶意 SPECTRUM_ENGINE_EXE 被忽略。存储条目均为0，Stopping输入与发送按钮禁用、“正在关闭”有真实帧。探针只在显式开启时有界运行；350ms关窗观察窗口位于引擎清理之后，不阻塞 UI，30轮普通矩阵未开启。

原始日志/DOM 在复制之前，以11个实际 token、9份完整握手原串精确扫描：token0、完整握手0、Authorization: Bearer0。矩阵各自还有每轮实际 token/握手原串的独立原始日志扫描。安装态的附加扫描及完整 DOM 单列于 package-verification，不冒充前述782份。token从未输出到报告、DOM或JS命令参数。

| 时间段 | dev 历史实测（同冻结引擎） | 最终 release 22a13e6a |
|---|---:|---:|
| 启动命令/进程前基点→引擎就绪 | 19655.677 ms | {timing['engine_ready_ms']} ms |
| →界面可交互 | 19719.677 ms | {timing['interactive_ms']} ms |
| →首次smoke完成 | 78315.677 ms | {timing['first_smoke_completed_ms']} ms |
| 其中人工等待 | 58388 ms | {timing['manual_wait_before_smoke_ms']} ms |
| smoke往返 | 208 ms | {timing['smoke_round_trip_ms']} ms |
| 引擎指标elapsed_ms | 201.758 ms | {timing['metrics']['elapsed_ms']} ms |

dev 基点含构建；Vite --force、新WebView目录，OS缓存未清。release新WebView目录，OS缓存未清。**两者均不是干净VM冷启动，不判≤3秒验收通过。** `/health` 完整响应与 `/smoke` 五字段原 JSON 在附录；/smoke 通过 Rust 无参 invoke 请求并在真实界面显示。Ctrl+K、Ctrl+Enter、未知输入中文提示、Ready→Failed→重试第二代Ready均重新操作并保留原件。

30秒界面不冻结由同源码 Tauri debug 测试宿主单列：298个Starting心跳、最大队列8ms、最大心跳间隔104ms、Starting可见true=0、30010ms进入StartupTimeout；第二实例激活与内部invoke均处理。不是假称由真实引擎制造超时。Starting→Stopping由当前源码core harness记录；其他允许迁移由实际主机日志记录，不将core观测冒充隐藏窗口截图。

**安装与卸载（宿主机）。** 默认路径注册表实证 `%LOCALAPPDATA%\\Programs\\SpectrumAgent`，数据根仍 `%LOCALAPPDATA%\\SpectrumAgent`。安装包里的外壳与本次release源exe逐字节一致，引擎同样一致；资源544、_internal543，全清单匹配；持久546文件=外壳+resources/backend+NSIS卸载器，无probe/stub。运行前后各比对一次程序文件，均未变。安装后内嵌UI/真实health/smoke已复验，正常关窗进程与端口消失。握手是否残留按真实结果记录，外壳不删改握手。

实际调用自带uninstall.exe /S，程序目录移除、卸载注册表项消失。卸载前后 **{uninstall['data_files_after']} 个数据文件** 名称/字节数/SHA256 全部相同，run/logs/testdata均保留。比较发生在测试卫生之前；随后仅删除3个本轮、精确SHA匹配的标记。脚本卫生不作为产品通过依据。宿主机已有WebView2，不能声称验证了干净机器首次缺Runtime的离线安装。

20项验收逐条结果：

| 项 | 结果 | 证据与边界 |
|---:|---|---|
| 1 静态检查/构建 | 通过 | fmt0、clippy无warning、22+1测试、strict TS/Vite、显式custom-protocol --no-bundle。 |
| 2a stub确定性场景 | 通过 | 当前源码tests-output完整stub原文；超时/假服务专用stub，不冒称真实引擎。 |
| 2b Win32注入 | 通过 | 五失败调用序列、终止方式、wait与句柄恰关一次，完整输出。 |
| 2c 真实集成 | 通过 | 最终health/smoke、三类真实失败、30轮矩阵；主因不被非法旧握手抢占。 |
| 2d 握手解析 | 通过 | 当前22+1测试精确字段/边界/非法格式镜像断言。 |
| 3 dev/test SpawnFailed | 通过（限定测试态） | 既有Tauri测试宿主CreateProcessW=2、失败页652ms；本轮当前源码stub/注入测试再次通过。 |
| 4a dev故障副本 | 通过（历史分层） | 检查点2专用副本证据不冒充release。 |
| 4b 专用release FaultFixture | 通过 | 本轮custom-protocol专用构建、显式543文件暂存、真实中文Failed DOM及实际路径。 |
| 4c 恢复Canonical | 通过 | 最终重新暂存544、重建22a13e6a、全量清单；最终全部证据重绑。 |
| 5 Resume清理 | 通过 | 当前注入序列TerminateJobObject→Wait→句柄恰关一次。 |
| 6 代次/停止竞态 | 通过 | 当前Rust测试、前端已归档状态测试；最终重试主机日志无旧代次覆写，Stopping不误报退出失败。 |
| 7 事件循环响应 | 通过（测试宿主） | 同源码30秒心跳/激活/invoke；普通发布不持续定时日志。 |
| 8 窗口可见性 | 通过 | 最终生产Ready/Failed真实页面，Starting隐藏日志；debug超时宿主隐藏。 |
| 9 单实例 | 通过 | 最终Ready/Failed二实例exit0、无新引擎；Starting用测试宿主专门验证。 |
| 10 四态对话条/快捷键 | 通过 | 最终782份完整DOM含4个Stopping帧；真实smoke、CtrlK/CtrlEnter、未知输入。 |
| 11 三段计时 | 宿主机已记录；VM待验证 | dev/release分列、人工等待与缓存定义单列；不判≤3秒通过。 |
| 12 正常关窗 | 通过 | 最终22a13e6a 10/10；真实Alt+F4、PID/端口逐轮表。 |
| 13 Ready强杀 | 通过 | 最终22a13e6a 10/10；Explorer父且不在Job，无孤儿。 |
| 14 Starting强杀 | 通过 | 最终22a13e6a 10/10；握手未发布、完整引擎路径计数0。 |
| 15 陈旧握手 | 通过 | 最终矩阵旧boot_id→新boot_id，Ready匹配本次PID/创建时间/health；外壳不清洗。 |
| 16 token审计 | 通过（已采样范围） | 原始源文件先精确扫描再复制；矩阵逐轮另有扫描；完整DOM和存储，不只截屏。 |
| 17 四态迁移 | 通过（分层） | 全部7允许对由最终日志+同源码debug+当前core覆盖；app_exit独立，非第五态。 |
| 18 资源路径 | 通过 | 相对配置、ignored resources、实际--no-bundle路径、无效环境覆盖反向用例、安装资源全清单。 |
| 19 锁/Git | **锁通过；全仓干净未通过** | 三锁指纹不变并已归档；负责人3项未跟踪文件保留，绝不擅删/代提交。 |
| 20 RT_MANIFEST | 通过（只验manifest） | 最终源与安装后两exe各提取，SHA绑定、正确命名空间/asInvoker/CommonControls6；LongPathsEnabled=0，>260功能待VM。 |

第4步本机附加项：setup生成、currentUser默认路径、内置WebView安装器签名、安装完整性、启动冒烟、关窗回收、卸载程序目录移除/数据不变均已有原始输出。**标准用户权限、断网首次安装、VM恢复验证、干净VM三段计时、Win10兼容性、>260路径功能仍未验证。** VM-BUILD-Win11Clean.md已同步安装路径/卸载数据两项与Runtime pv核验说明。

'''
    appendices = [
        (B / 'fmt-prebuild-execution.json', 'fmt --check执行收据（stdout为空）'),
        (B / 'clippy-output.txt', 'cargo clippy完整输出'), (B / 'tests-output.txt', 'cargo test完整输出'),
        (B / 'custom-protocol-build-output.txt', '首次生产特性构建'),
        (B / 'faultfixture-production-stage-output.txt', '显式FaultFixture暂存'),
        (B / 'faultfixture-production-build-output.txt', '专用生产FaultFixture构建'),
        (B / 'faultfixture-production-build-binding.json', '首次输出旧DLL残留探针（不算缺DLL通过）'),
        (B / 'staged-fault-launch.json', '清除已核验夹具DLL后的实际启动'),
        (B / 'staged-fault-failed-ui.txt', '专用生产FaultFixture完整界面文本'),
        (B / 'canonical-production-restage-output.txt', '最终Canonical暂存'),
        (B / 'canonical-production-rebuild-output.txt', '最终Canonical重建'),
        (B / 'canonical-production-rebuild-binding.json', '重建SHA改变，未沿用旧矩阵'),
        (F / 'candidate-binding-output.txt', '最终生产候选与三个特性指纹'),
        (F / 'failure-cases-output.txt', '最终真实失败三案例完整输出'),
        (F / 'release-health-http.txt', '最终真实health完整HTTP响应'),
        (F / 'smoke-close-handshake-redacted.json', '最终握手全文（仅token打码）'),
        (F / 'smoke-close-result-ui.txt', '真实smoke完整五字段和界面'),
        (F / 'rt-manifest-nobundle-output.txt', '最终两个exe提取命令与完整XML'),
        (F / 'bundle-output.txt', '最终候选打包首次失败原文'),
        (F / 'bundle-retry-output.txt', '最终候选第二次失败原文'),
        (F / 'bundle-idle-preflight.json', '单独打包前无运行映像'),
        (F / 'bundle-idle-write-open-probe-output.txt', '只开写句柄探针，不写文件'),
        (F / 'bundle-idle-output.txt', '单独打包成功完整输出'),
        (F / 'bundle-idle-execution.json', '成功打包收据'),
        (F / 'host-install-output.txt', '最终包本机安装原始输出'),
        (F / 'installed-payload-before-run-output.txt', '安装资源全量校验'),
        (F / 'rt-manifest-installed-output.txt', '安装后两个exe提取命令与完整XML'),
        (F / 'installed-health-http.txt', '安装后health完整JSON'),
        (F / 'installed-smoke-result-ui.txt', '安装后smoke真实结果'),
        (F / 'installed-normal-close-output.txt', '安装后正常关窗PID/端口/握手事实'),
        (F / 'installed-payload-after-run-output.txt', '运行后程序资源仍逐项一致'),
        (F / 'host-uninstall-output.txt', '最终包卸载输出及卫生边界'),
        (F / 'package-copy-and-uninstall-sanity.json', '交付副本及卸载后状态'),
        (B / 'cdn-nsis-3.13.zip-download-output.txt', 'NSIS官方CDN HTTP原文'),
        (B / 'cdn-nsis_tauri_utils.dll-download-output.txt', 'utils官方CDN HTTP原文'),
        (B / 'bundle-artifact-provenance-output.txt', '工具哈希/签名/实际缓存与生成脚本行号'),
        (B / 'webview2-runtime-manifest-output.txt', '签名载荷Runtime版本XML'),
        (ROOT / 'artifacts/step3/checkpoint-4/dev-three-stage-timing.json', 'dev历史完整计时及基点'),
        (ROOT / 'artifacts/step3/checkpoint-4/spawn-failed-result.json', 'dev/test SpawnFailed真实宿主历史实测'),
        (B / 'sealed-engine-reverify-output.txt', '封版新旧引擎证据只读复核'),
    ]
    for mode in ('KillReady', 'KillStarting', 'Close'):
        appendices.append((sorted(F.glob('explorer-' + mode + '*console.txt'))[-1], mode + '最终10轮控制台原文'))
    for filename in ('analysis-committed-output.txt', 'package-verification-committed-output.txt'):
        appendices.append((F / filename, '已提交生成器只读复核：' + filename))
    for path, label in appendices:
        assert path.exists(), f'Cannot report missing evidence: {path}'
        raw = text(path)
        report += f'<details>\n<summary>{label}：{link(path)}</summary>\n\n```text\n{raw}\n```\n\n</details>\n\n'
    report += '''## 遇到的问题

1. 官方github.com直连超时、旧代理TLS/EOF；负责人提供官方CDN后HTTP200且固定SHA/大小通过，未改系统代理或验证策略。
2. 专用FaultFixture构建虽暂存543，--no-bundle旧输出仍留python312.dll；首次探针如实false，不算通过。只在测试输出删除已核对的该DLL后实跑专用失败页，后续重新Canonical暂存/构建/全量比对。
3. Canonical重建外壳SHA由cba变为22a；最终全部30轮、UI/DOM、计时、manifest和安装证据已重采，不用旧SHA倒推新产物通过。
4. 两次最终包在压缩完成后报“另一个程序正在使用此文件，进程无法访问。(os error32)”，CLI退出1均保留且不作交付依据。上游bundler即使--no-binary-patching仍在收尾打开原exe写回；此前测试曾与打包重叠。只读无进程/写句柄探针通过后，保持全程不运行外壳，单独第三次CLI退出0。具体占用句柄持有者未定位，不猜杀毒/系统组件归因。依据：[Tauri bundler](https://raw.githubusercontent.com/tauri-apps/tauri/tauri-cli-v2.12.3/crates/tauri-bundler/src/bundle.rs)。
5. 正常关窗stderr1412在生产exe与安装exe再次复现，原文保留；原因未定位。PID/端口已退出与该stderr现象分开记录，不互相替代。
6. 正常关窗可留下指向已死PID的握手：本轮真实记录，不写成外壳自动清理；新版契约外壳只读，下一代引擎原子覆盖的恢复已有矩阵证据。卸载验证也包含该文件且字节保留。
7. 生成辅助分析脚本的首次复制误用系统默认GBK解码而失败，改为显式UTF-8后生成和复核通过；没有修改产品源码或旧输出迁就脚本。
8. 负责人3项未跟踪内容保持原状：.runtime/、光谱平台_阶段一_代码审查与进度分析_20261018.md、光谱数据AI-Agent处理平台_阶段一技术选型_定稿v1.1_1792327262075_csvb.md。因此验收19“git全仓干净”未通过，不擅自删除、隐藏或代提交。

## 下一步打算

在此检查点停下等待负责人复核；获准后使用当前pristine进行VM恢复验证、断网首次安装/Runtime pv核对、三段冷启动、退出矩阵、默认路径与卸载数据保留以及长路径实测。现不声明第2步正式关闭，不使用宿主机证据代替VM。
'''
    with (B / 'REPORT.md').open('x', encoding='utf-8', newline='') as handle:
        handle.write(report)
    print(json.dumps({'report': str(B / 'REPORT.md'), 'shell_sha256': candidate['shell_sha256'],
                      'setup_sha256': bundle['setup_sha256'], 'vm_status': '待 VM 实机'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
