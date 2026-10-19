# 里程碑 #02 · 数据接入交付（等复核）

2026-10-19，E:\AI_Agent。4.1–4.6 已按序实现；本报告的 UI/IPC 验收范围是获批的 **debug + venv 3.12.13**，不冒充封版安装包能力。#01 的 22a13e6a / d8492536 不改动、不重冻、不重打包。git 源码边界核对见 `tests/evidence/4.6-evidence-audit.json` 与 `4.6-release-boundary.diff`。

## 提交范围与接口

| 子任务 | 提交 | 产出 |
|---|---|---|
| 4.1 | f7876c5 | SpectrumDataSet/Pydantic dataclass、JSON Schema、有界读取、raw-only to_numpy |
| 4.2 | 6c450ea | spectral ENVI reader、精确大小校验、11 文件真实数据验证脚本 |
| 4.3 | d058ad4 | BinaryReader，共用 JSON/TXT 字段/brace parser、懒 memmap |
| 4.4 | d19c879 | 缺 interleave、ENVI5 包裹/平铺 JSON、失败兜底与大小红线 |
| 4.5 | bb7cc6f | 原子/幂等 SQLite 引用登记、import/get/band/region/preview、有界 PNG |
| 4.6 | 本笔提交（以 git log 为准） | dialog、单出口 IPC、列表/进度/Canvas、cfg(debug) venv 双 PID 监督、验收证据 |

模型 shape 恒为 (lines,samples,bands)；wavelengths 未提供为 []，fwhm 未提供为 null。默认有界读取为 float64、除 scale_factor；raw 保持原始 dtype/DN，塑料样本为 uint16。缩放模式 to_numpy 抛结构化 FULL_ARRAY_DISABLED；raw 返回只读零拷贝 memmap。显式 read_region(全图) 是调用方知情选择。未使用 load() 或隐式全立方体缩放。

数据登记只存规范化源路径、默认 raw 与元数据，不复制/移动/修改源文件；目录全量头解析和大小校验先于登记事务，失败列出全部无效项。同一路径+raw 返回既有 ID。band/region 可覆盖 raw。PNG 采样最长边≤512；JSON 读取≤65536 个值，Rust 响应≤8MiB。OpenAPI 快照在 `spectrumagent/api/openapi.json`，模型 schema 在 `spectrumagent/data/schema.json`。

## 本轮实测与原始输出

| 验证 | 命令/输出 | 结果 |
|---|---|---|
| Python 回归 | `.venv\Scripts\python.exe -m pytest backend/tests src-python/tests/data -q --basetemp .runtime/m02-tests/4.6-regression`；`tests/evidence/4.6-python-regression.txt` | 141 passed，10 warnings，5.62s；其中 #02 为102项 |
| 真 HTTP | `.venv\Scripts\python.exe scripts/selfcheck_milestone02.py`；`4.6-live-http.txt` | health200/无token401/import200/缺文件400，幂等、raw覆盖、PNG、3路并发及health200，JSON日志21行、凭证匹配0 |
| Rust 当前源码 | `cargo test --locked --offline --lib --test dev_identity --test dev_lifecycle -- --nocapture --test-threads=1`；`4.6-rust-tests-final.txt` | 9/9：6个datasets安全用例、1个既有closed-route用例、1个身份拒绝矩阵、1个真实双PID两轮生命周期 |
| clippy | `cargo clippy --locked --offline --all-targets -- -D warnings`；`4.6-clippy-final.txt` | 通过；unwrap_used/expect_used/panic deny 未放宽 |
| Rust格式 | rustfmt --check 仅本轮新增3个模块、2个测试文件 | exit0；不声称全仓fmt通过，不重排原release代码行 |
| 前端 | Node24.19.0 执行 tsc --noEmit、Node --test、Vite build | 类型检查exit0，Node2/2；`4.6-ui-unit-final.txt`、`4.6-vite-build-final.txt`；产物仅在.runtime/m02-vite-dist |
| 真实数据 | `scripts/verify_plastic_dataset.py`；`tests/evidence/plastic-11.txt` | 11/11，逐值 raw==memmap、每波段scaled==DN/65535，metadata与只读约束通过；完整输出附后 |

所有 Python 命令实际使用 E:\AI_Agent\.venv\Scripts\python.exe。Cargo_HOME=E:\AI_Agent\.cargo-home，CARGO_TARGET_DIR=E:\AI_Agent\src-tauri\target\milestone02，TEMP/TMP 在 E 盘；详见 `4.6-build-environment.json`。没有构建release，没有复跑#01发布态矩阵或安装回归。

## 依赖审计与授权落地

负责方执行安装，Codex 未执行 cargo fetch/npm install。Cargo.lock 445→458（+13），npm 64→65（+1），全部新增可达 dialog/rfd/fs，既有 npm resolved URL 无变化。Rust dialog=2.8.3、fs=2.7.1、rfd=0.16.0，npm dialog=2.8.3；详情见 `4.6-lock-audit.json`、`4.6-cargo-tree.txt`、`4.6-npm-ls.txt`。Python lock SHA256 保持 58e24b59da34461a17fd942b4047071e42b5120b3d474ba976a7e28535d40bcc。

首次离线编译发现负责方新增 Cargo 缓存在 C 盘；只读检查还发现该缓存包含 official/USTC 两个命名空间。将已有457份本地归档逐个按 Cargo.lock SHA256 核验后复制/复用到E盘，13份来源于负责方已下载的镜像命名空间；索引对应版本的checksum同样校验。没有网络请求、没有改系统/用户Cargo配置、没有再次下载或安装。实际来源逐文件记录在 `4.6-cargo-cache-copy.json`，不把镜像来源写成官方来源。

原批准写法中的 tauri_plugin_dialog::Builder 在实际2.8.3是私有导入，不能编译；本地lib.rs:203公开的是 init()，因此改用 tauri_plugin_dialog::init() 注册同一插件。原错误见 `4.6-dialog-api-compile-failure.txt`。这属于锁定API写法订正，未换版本/依赖/权限/技术栈。

single-instance 仍第一个注册；仅增加 dialog:allow-open，没有 dialog:default 或fs权限。main.json 另加获批的声明性 allow-datasets-forward，真正边界是 handler：release 四命令原字面量逐字不变，datasets_forward 仅 cfg(debug_assertions) 注册。AppManifest及自动生成ACL/schema同步入库。前端只有 `components/datasets/api.ts` 调用该 IPC；选择器精确使用 directory:true、multiple:true、获批filters，路径只作为 import 请求体传到sidecar，没有JS文件读取或直接HTTP。

Rust转发仅本代127.0.0.1握手端口、类型化GET/POST路由；拒绝其它host/path/method输入。无代理、无重定向，连接500ms/总30s；先校验所有状态的boot_id/pid头，再处理正文。Content-Length与无长度流式正文均受8MiB限制；明文/JSON转义凭证反射都拒绝；工作线程完成后再次校验代次。

## 桌面与进程证据血缘

桌面验收使用显式 E:\AI_Agent\.runtime\m02-desktop\SpectrumAgent，**没有使用#01真实或AppContainer影子数据根**。`scripts/verify_m02_desktop.ps1` 在宿主运行debug外壳，等待实际UI关窗，并在测试宿主退出前观察两个子进程。独立Popen自检的强制回收仅是测试卫生，不能替代此项。

- 外壳6456，launcher22952，实际Python28324，boot c20179d5，端口61011；debug外壳SHA256=4b668c06e5043299689980fae741ef82aadece1fd6f778296eb5082af5def96e。`tests/evidence/desktop/run.json` 绑定本次二进制；该SHA与#01交付候选无关。
- 原生选择 plastic 目录→新增11项，11幅首波段缩略图；`ui-imported.txt`。重复选择→新增0、已有11且列表不重复；`ui-idempotent.txt`。
- 预览首样本波段0、199，Canvas宽320×高116；`ui-preview-band0.txt`、`ui-preview-band199.txt`，分别由对应引擎GET访问日志佐证。PNG解码用ImageBitmap/Blob，不增加外部图像URL或修改既有CSP。
- 选择独立构造坏头目录→HEADER_INVALID，显示源路径/原因，已登记11项保留；`ui-invalid-header.txt`，引擎日志14:12:13.504Z的import400对应。
- 正常关窗（14:12:37Z）：Stopping→actual Python exit1（Job终止）→generation_cleanup complete→app_exit→host_cleanup_completed success；外壳exit0，launcher/Python均无残留，`close-receipt.json`。不能把Job终止的引擎exit1误写成外壳失败。
- `dom-6456.jsonl` 为既有45s探针原文件，共450条：Starting12/Ready438，URL=http://127.0.0.1:1420/；localStorage/sessionStorage均空，凭证匹配0。**数据导入等操作发生在45s之后**，由ui-*.txt与引擎时间戳日志证明，不能写成这450条DOM已覆盖后续预览或Stopping。

初次在沙箱内启动遇WebView2 HRESULT0x800700AA，stderr已保存为 `4.6-desktop-sandbox-failure.txt`；随后在宿主运行成功。关窗仍复现Chrome_WidgetWin_0 unregister 1412，原文在desktop/stderr.txt；原因未定位，不将其与旧exit70或注册键异常互相解释。

## dev/release 差异与已知问题

1. venv launcher与实际CPython为两个PID；debug握手仍记录实际Python。IsProcessInJob明确检查本Job，GetProcessTimes核对握手创建时间并检查存活，失败返回结构化错误，不降级只监督launcher。核验后监督/退出等待均切到实际CPython，保留launcher句柄与原Job。原解释器路径与env覆盖机制不变。release单PID校验及原启动/Job代码行未改。
2. 真实核心两轮及GUI关闭后，握手均观察到残留（文件仍在）；进程均已退出。核心第二轮不清洗直接启动，boot_id改变且Ready，证明陈旧握手自愈。**未用脚本删除冒充修复**，不宣称“握手自动清理通过”。沿用#01负责人已知问题口径，不动封版二进制。
3. release datasets IPC未实现/注册，封版onedir没有这些新路由。本轮不重冻、不打包；后续打包里程碑须决定发布IPC、复验成品与venv运行时差异、dialog常驻依赖体积。
4. 进度表示完成目录数/summary，单目录校验期间是不定进度；没有伪造全文件字节读取进度。登记账本持久化，UI本会话列表重启后可通过重选目录幂等恢复，未新增未获批的列表路由或自动路径存储。
5. 初次HTTP检查假定launcher_pid==Python_pid而失败，原输出保留；后续修正“HTTP自检的判定口径”，不把它冒充监督器验收。真正监督验收另有Native Job和GUI证据。Python单测既有弃用warning没有通过装新包处理。
6. 较早4.5失败诊断出现测试凭证repr：原始诊断隔离.runtime，入库副本明确标注脱敏；随后测试使用安全repr。没有声称这份历史原始诊断零泄漏。当前runtime/转发/UI审计独立通过。
7. #01旧exit code=70仍未验证/未定位，注册键历史消失原因未定位，未追查；本轮结果不改变封版裁定。

## TASK-02 §5 逐项自评（开发态，等负责人复核）

| 项 | 自评 | 依据 |
|---|---|---|
|5.1.1 ENVI全部plastic样本|通过|真实11/11完整输出|
|5.1.2 raw为uint16 DN|通过|全部值与直接memmap相等；raw-only to_numpy单测|
|5.1.3 BinaryReader同数据不同头|通过|JSON/TXT、布局/类型/已知值fixture|
|5.1.4 三种fallback边界|通过|缺interleave、两种JSON、截断/超大明确报错|
|5.1.5 API schema稳定|通过|Pydantic/OpenAPI快照精确断言|
|5.1.6 选择→导入→列表→预览不卡死|通过|宿主原生选择11项、两波段Canvas、重复及错误提示；UI按批准目录模式|
|5.2.1 59MB metadata≤500ms|通过|本轮11文件2.955–4.969ms，仅头解析；不泛化为冷缓存承诺|
|5.2.2 单波段≤100ms|通过|本轮最大23.1ms|
|5.2.3 大文件懒加载|通过|拒绝隐式全数组、memmap、导入不调用asarray/load；未另量RSS峰值|
|5.2.4 三路导入不阻塞sidecar|通过|Barrier并发单测+真实HTTP三路与health200|
|5.3.1 reflectance与DN/65535一致|通过|全部样本逐波段精确相等，比1e-5更严|
|5.3.2 L/S方向不转置|通过|已知像素PNG解压断言、UI320×116|
|5.3.3 波长/索引顺序一致|通过|metadata精确数组+读波段逐值对照|
|5.4.1 文件不存在|通过|HTTP400结构化FILE_NOT_FOUND|
|5.4.2 头损坏|通过|单测HTTP400+宿主UI明确原因|
|5.4.3 大小不符|通过|截断、多余字节、再次读取变大均SIZE_MISMATCH|
|5.4.4 >2GB不全读|通过|2,147,516,416B稀疏fixture、np.memmap、禁fromfile、有界末像素/小区域读取|

以上均为自评，不代替负责人复核；发布态datasets、安装包体积与运行时差异留给后续打包里程碑，未标通过。

## 完整真实样本输出

以下原样嵌入 `tests/evidence/plastic-11.txt`（含当时警告），没有重新编造逐文件数字。

```text
E:\AI_Agent\scripts\verify_plastic_dataset.py:3: SyntaxWarning: invalid escape sequence '\A'
  Run with E:\AI_Agent\.venv\Scripts\python.exe scripts/verify_plastic_dataset.py
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pe\\20260804205214_64.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 4.159, "max_read_band_ms": 2.579}
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:43 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pe\\20260804205217_70.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 4.969, "max_read_band_ms": 23.1}
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:44 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pe\\20260804205301_143.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 3.068, "max_read_band_ms": 19.347}
2026-10-19 20:38:45 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:45 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:45 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:45 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:45 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:45 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:45 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:45 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:45 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:45 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:45 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:45 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pet\\20260804195714_53.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 3.526, "max_read_band_ms": 22.01}
2026-10-19 20:38:46 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:46 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:46 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:46 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:46 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:46 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:46 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:46 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:46 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:46 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:46 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:46 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pet\\20260804195723_72.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 3.076, "max_read_band_ms": 19.92}
2026-10-19 20:38:47 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:47 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:47 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:47 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:47 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:47 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:47 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:47 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:47 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:47 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:47 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:47 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pet\\20260804195732_93.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 4.542, "max_read_band_ms": 21.08}
2026-10-19 20:38:48 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:48 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:48 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:48 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:48 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:48 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:48 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:48 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:48 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:48 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:48 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:48 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pet\\20260804195826_186.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 4.777, "max_read_band_ms": 20.465}
2026-10-19 20:38:49 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:49 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:49 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:49 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:49 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:49 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:49 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:49 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:49 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:49 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:49 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:49 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pp\\20260804210313_15.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 2.955, "max_read_band_ms": 20.685}
2026-10-19 20:38:50 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:50 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:50 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:50 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:50 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:50 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:50 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:50 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:50 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:50 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:50 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:50 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pp\\20260804210353_75.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 3.371, "max_read_band_ms": 20.401}
2026-10-19 20:38:51 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:51 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:51 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:51 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:51 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:51 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:51 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:51 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:51 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:51 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:51 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:51 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pp\\20260804210443_152.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 2.985, "max_read_band_ms": 20.95}
2026-10-19 20:38:52 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:52 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:52 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:52 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:52 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:52 [warning  ] unknown_header_key             key=relative
2026-10-19 20:38:52 [warning  ] unknown_header_key             key='file type'
2026-10-19 20:38:52 [warning  ] unknown_header_key             key='sensor type'
2026-10-19 20:38:52 [warning  ] unknown_header_key             key='wavelength units'
2026-10-19 20:38:52 [warning  ] unknown_header_key             key='default stretch'
2026-10-19 20:38:52 [warning  ] unknown_header_key             key='band names'
2026-10-19 20:38:52 [warning  ] unknown_header_key             key=relative
{"file": "E:\\高光谱数据集\\plastic\\pp\\20260804210509_189.hdr", "status": "PASS", "shape": [231, 640, 200], "dtype": "uint16", "interleave": "bil", "wavelength_nm": [881.85, 1714.13], "scale_factor": 65535, "bytes": 59136000, "raw_all_values_equal": true, "scaled_all_bands_equal": true, "open_ms": 3.404, "max_read_band_ms": 20.748}
{"samples": 11, "passed": 11, "failed": 0}
```

## 变更文件完整清单

相对封账提交205f0ad，包含4.1–4.6；两份负责人公司文档排除。

```text
TASK-02-数据接入.md
package-lock.json
package.json
scripts/audit_m02_evidence.py
scripts/dev_sidecar.py
scripts/selfcheck_milestone02.py
scripts/verify_m02_desktop.ps1
scripts/verify_plastic_dataset.py
src-python/PROGRESS-4.6.md
src-python/README.md
src-python/REPORT.md
src-python/spectrumagent/__init__.py
src-python/spectrumagent/api/README.md
src-python/spectrumagent/api/__init__.py
src-python/spectrumagent/api/datasets.py
src-python/spectrumagent/api/openapi.json
src-python/spectrumagent/api/registry.py
src-python/spectrumagent/api/schemas.py
src-python/spectrumagent/app.py
src-python/spectrumagent/data/__init__.py
src-python/spectrumagent/data/error-schema.json
src-python/spectrumagent/data/errors.py
src-python/spectrumagent/data/model.py
src-python/spectrumagent/data/readers/__init__.py
src-python/spectrumagent/data/readers/binary.py
src-python/spectrumagent/data/readers/envi.py
src-python/spectrumagent/data/readers/fallback.py
src-python/spectrumagent/data/readers/header.py
src-python/spectrumagent/data/schema.json
src-python/tests/conftest.py
src-python/tests/data/test_api.py
src-python/tests/data/test_binary.py
src-python/tests/data/test_envi.py
src-python/tests/data/test_fallback.py
src-python/tests/data/test_model.py
src-python/tests/evidence/4.2-final-pytest.txt
src-python/tests/evidence/4.2-pytest.txt
src-python/tests/evidence/4.3-pytest.txt
src-python/tests/evidence/4.4-final-pytest.txt
src-python/tests/evidence/4.4-pytest.txt
src-python/tests/evidence/4.5-complete-pytest.txt
src-python/tests/evidence/4.5-final-pytest.txt
src-python/tests/evidence/4.5-pytest-failed-redacted.txt
src-python/tests/evidence/4.6-audit-output.txt
src-python/tests/evidence/4.6-build-environment.json
src-python/tests/evidence/4.6-cargo-cache-copy.json
src-python/tests/evidence/4.6-cargo-tree.txt
src-python/tests/evidence/4.6-clippy-final.txt
src-python/tests/evidence/4.6-clippy-first.txt
src-python/tests/evidence/4.6-clippy-test-lint.txt
src-python/tests/evidence/4.6-clippy.txt
src-python/tests/evidence/4.6-debug-build.txt
src-python/tests/evidence/4.6-desktop-sandbox-failure.txt
src-python/tests/evidence/4.6-dialog-api-compile-failure.txt
src-python/tests/evidence/4.6-evidence-audit.json
src-python/tests/evidence/4.6-files.txt
src-python/tests/evidence/4.6-live-http-pid-failure.txt
src-python/tests/evidence/4.6-live-http.txt
src-python/tests/evidence/4.6-lock-audit.json
src-python/tests/evidence/4.6-npm-ls.txt
src-python/tests/evidence/4.6-python-process-probe-host.txt
src-python/tests/evidence/4.6-python-process-probe.txt
src-python/tests/evidence/4.6-python-regression.txt
src-python/tests/evidence/4.6-release-boundary.diff
src-python/tests/evidence/4.6-reqwest-features.txt
src-python/tests/evidence/4.6-rust-lib-first.txt
src-python/tests/evidence/4.6-rust-tests-final.txt
src-python/tests/evidence/4.6-rust-tests.txt
src-python/tests/evidence/4.6-ui-unit-final.txt
src-python/tests/evidence/4.6-ui-unit.txt
src-python/tests/evidence/4.6-vite-build-final.txt
src-python/tests/evidence/4.6-vite-build.txt
src-python/tests/evidence/desktop/close-receipt.json
src-python/tests/evidence/desktop/dom-6456.jsonl
src-python/tests/evidence/desktop/engine-20261019.jsonl
src-python/tests/evidence/desktop/run.json
src-python/tests/evidence/desktop/shell-20261019.log
src-python/tests/evidence/desktop/stderr.txt
src-python/tests/evidence/desktop/stdout.txt
src-python/tests/evidence/desktop/ui-idempotent.txt
src-python/tests/evidence/desktop/ui-imported.txt
src-python/tests/evidence/desktop/ui-invalid-header.txt
src-python/tests/evidence/desktop/ui-preview-band0.txt
src-python/tests/evidence/desktop/ui-preview-band199.txt
src-python/tests/evidence/dialog-registry-readonly.json
src-python/tests/evidence/plastic-11.txt
src-python/tests/fixtures/README.md
src-python/tests/fixtures/cube-u16.bin
src-python/tests/fixtures/cubes.py
src-tauri/Cargo.lock
src-tauri/Cargo.toml
src-tauri/build.rs
src-tauri/capabilities/main.json
src-tauri/gen/schemas/acl-manifests.json
src-tauri/gen/schemas/capabilities.json
src-tauri/gen/schemas/desktop-schema.json
src-tauri/gen/schemas/windows-schema.json
src-tauri/permissions/autogenerated/datasets_forward.toml
src-tauri/src/datasets_dev.rs
src-tauri/src/dev_engine.rs
src-tauri/src/dev_supervision.rs
src-tauri/src/lib.rs
src-tauri/src/main.rs
src-tauri/src/process.rs
src-tauri/src/supervisor.rs
src-tauri/src/win32.rs
src-tauri/tests/dev_identity.rs
src-tauri/tests/dev_lifecycle.rs
src/App.tsx
src/components/datasets/DatasetPanel.tsx
src/components/datasets/api.ts
src/components/datasets/types.test.ts
src/components/datasets/types.ts
src/style.css
```
