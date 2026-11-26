# SpectrumAgent 光谱数据 AI-Agent

Windows 桌面光谱分析工作台，采用 Tauri 2 + React + Python FastAPI。
当前桌面产品版本为 **0.4.1**，以 `src-tauri/tauri.conf.json` 为准。
本目录保留运行源码、已有依赖、工具链、冻结后端和桌面构建产物；清理清单内的历史归档与测试已移除。

源码仓库：[FengKeXiang66/SpectrumAgent](https://github.com/FengKeXiang66/SpectrumAgent)。Git 历史从当前精简版本重新开始。
仓库包含本体源码、锁文件、配置和构建脚本；本机依赖、工具链、缓存、完整冻结后端及 EXE 不上传 Git。
仓库可克隆到任意盘符和目录；下列命令均从仓库根执行。新协作者先按“首次克隆与开发环境”安装依赖。

## 直接运行现有桌面程序

仅适用于已有完整 release 构建产物的目录。在仓库根的 PowerShell 中执行：

```powershell
& '.\src-tauri\target\release\spectrum-agent.exe'
```

必须保留 release 目录旁的完整 `resources/backend/`；单独复制外壳 EXE 不能运行后端。
现有 EXE 是清理前的构建产物，修改源码后需要重新构建才能更新应用。
桌面程序需要 Windows WebView2；打包配置采用 NSIS 当前用户安装和离线 WebView2 安装器。

## 功能与工作流程

1. 导入 ENVI、配对二进制头文件或支持的 MAT 光谱数据，查看波段、伪彩和谱线。
2. 在标注工作台选择类别，使用超像素点选、手工区域等方式标注并保存当前结果。
3. 选择当前预处理配方并处理样品，检查结果后直接勾选样品建模。
4. 执行 PLS 回归或 PLS-DA 分类、波段选择、交叉验证和批量推理。
5. 在结果页查看指标、诊断、实验比较，并按需导出图件、数据和报告。

工作区只维护每张图像的当前标注、每个配方的当前定义和当前处理结果。保存会替换当前内容，不再创建或选择历史版本；数据集与训练集的预览、确认、冻结和回溯入口已移除。正常标注撤销和本地持久化保留，关闭软件后可以继续操作。建模记录与已注册模型保留为独立结果，模型预测使用训练时存储的变换参数。

兼容旧工作区时，读取原来最新保存的标注与配方，不直接删除旧文件或数据库记录。旧表名及部分内部关联字段保留用于兼容存量模型，它们不再提供版本操作。旧预处理记录缺少新的内容校验标识，用于旧配方或回归训练时需要重新处理；分类直接从原图与已保存标注建立统一实验方案。已有模型和结果文件继续保留。修改标注或配方后，对受影响样品重新预处理，避免把旧结果用于建模。

常驻对话入口负责工具编排与结果解释；数值、指标和证据由确定性后端生成。
使用云端对话前，在设置中配置供应商、模型和密钥，并检查“允许外发”设置。
关闭外发仍可使用本地导入、标注、预处理和建模；首次配置前无需联网运行这些本地功能。

## 数据与会话生命周期

- 原始数据按引用读取，导入不等于把原始光谱复制进本仓库；请保留源文件及其路径。
- 桌面程序默认在 `%LOCALAPPDATA%\SpectrumAgent` 保存应用配置和外壳日志。
- 数据库、草稿、标注、配方、数据集/训练集版本、处理与建模记录保存在该固定目录，退出或重新启动均不会删除。
- 重启后自动读取数据目录并恢复上次全局会话；已提交的标注草稿可继续编辑，已完成的处理和建模产物可继续查看、复用和导出。
- 退出时尚未完成的计算会在下次启动时标记为中断/失败，保留已有产物，需核对后重新提交；不会自动重复计算。画布上尚未提交的手势、候选和撤销栈不跨进程恢复。
- 旧版本已在退出时删除的数据无法恢复；遗留的 `sessions/` 目录会保留，但不会自动合并到当前数据库。
- 应用级设置和加密密钥跨会话保留，密钥使用 Windows DPAPI；不要把握手 token 或凭据提交到 Git。
- 后端只监听本机随机端口；Rust 监督器验证握手和进程身份，并随桌面退出回收子进程。

## 目录说明

| 路径 | 用途 |
| --- | --- |
| `src/` | React 页面、组件、状态管理及显示逻辑 |
| `src-python/spectrumagent/` | 数据读取、标注、预处理、建模、Agent、Schema 和内置目录 |
| `backend/` | FastAPI 入口、握手、身份、日志与应用路径 |
| `src-tauri/src/` | Rust 桌面外壳、IPC、进程监督与会话管理 |
| `src-tauri/resources/backend/` | 完整 PyInstaller onedir 后端资源 |
| `src-tauri/target/` | 已有 Rust 构建、桌面程序、后端副本和安装工具缓存 |
| `.venv/`、`node_modules/` | 当前 Python 与前端依赖 |
| `.toolchains/`、`.cargo-home/`、`.npm-cache/` | 本地工具链及离线依赖缓存 |
| `scripts/build_release.ps1`、`scripts/backend.spec` | 当前安装包入口与后端冻结配置 |
| `scripts/dev_sidecar.py`、`scripts/update_api_schema.py` | 开发后端与接口 Schema 维护入口 |
| `.git/` | 从当前精简版本开始的本地 Git 历史 |
| `dist/`、`build/` | 已有前端与冻结构建中间产物 |

## 首次克隆与开发环境

当前目标平台为 Windows x64。先准备以下工具：

- **CPython 3.12.13**：开发后端会检查完整版本号，其他 3.12 补丁版本也会被拒绝。
- **Node.js 24.19.0 / npm 10.8.2**：与 `package.json` 的版本约束一致。
- Rust 的 MSVC 工具链、Visual Studio C++ 构建工具和 WebView2，安装步骤见 [Tauri Windows 官方前置条件](https://v2.tauri.app/start/prerequisites/#windows)。

在自己选择的父目录中打开 PowerShell，再执行：

```powershell
git clone https://github.com/FengKeXiang66/SpectrumAgent.git
Set-Location -LiteralPath '.\SpectrumAgent'

# 必须先安装 3.12.13；确认 py 启动器选中的补丁版本正确。
py -3.12 -c "import sys; assert sys.version_info[:3] == (3, 12, 13), sys.version"
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r '.\requirements-lock.txt'

npm.cmd ci
cargo build --manifest-path '.\src-tauri\Cargo.toml' --locked
```

每条命令成功后再执行下一条。若未安装 `py` 启动器，使用自己安装的 Python 3.12.13 的完整路径替代 `py -3.12`。
Python、npm 和 Cargo 依赖分别锁定在 `requirements-lock.txt`、`package-lock.json` 和 `src-tauri/Cargo.lock`。
首次安装需要下载依赖，不能直接启用 Cargo 离线模式；已有依赖的本机可跳过安装步骤。

## 开发启动与前端构建

在仓库根启动完整开发桌面：

```powershell
# 清除可能遗留的“直接启动另一份引擎”覆盖配置。
Remove-Item Env:SPECTRUM_ENGINE_EXE -ErrorAction SilentlyContinue
npm.cmd run tauri -- dev
```

该入口会启动 Vite（127.0.0.1:1420）；debug 外壳自动通过 `dev_sidecar.py` 启动源码后端。
默认解释器从编译时仓库位置推导为 `.venv\Scripts\python.exe`，不要求 E 盘，也无需设置 Python 路径变量。
源码开发不需要先冻结 Python 后端。安装包的 release 外壳使用随包后端，不读取这个 debug 配置。
仅运行 `npm.cmd run dev` 是浏览器前端，桌面 IPC 需要 Tauri 宿主。

如需使用其他虚拟环境，可在当前终端显式覆盖，值必须是 Python 3.12.13 的绝对路径：

```powershell
$env:SPECTRUMAGENT_DEV_PYTHON = (Resolve-Path -LiteralPath '..\other-env\Scripts\python.exe').Path
```

未设置该变量时使用仓库 `.venv`；若终端曾设置过覆盖值，执行 `Remove-Item Env:SPECTRUMAGENT_DEV_PYTHON -ErrorAction SilentlyContinue` 可恢复默认。

已有仓库内离线工具缓存的本机，可在启动前按需设置，所有路径跟随当前仓库：

```powershell
$repo = (Get-Location).Path
$localNode = Join-Path $repo '.toolchains\node24.19.0-npm10.8.2'
if (Test-Path -LiteralPath (Join-Path $localNode 'node.exe')) {
    $env:PATH = $localNode + ';' + $env:PATH
}
if (Test-Path -LiteralPath (Join-Path $repo '.cargo-home\registry')) {
    $env:CARGO_HOME = Join-Path $repo '.cargo-home'
}
$env:CARGO_TARGET_DIR = Join-Path $repo 'src-tauri\target'
$env:npm_config_cache = Join-Path $repo '.npm-cache'
$env:TEMP = Join-Path $repo 'build\temp'
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
$env:TMP = $env:TEMP
```

检查前端类型并构建：

```powershell
npm.cmd run build
```

结果写入 `dist/`，不会更新已有桌面 EXE 或冻结 Python 后端。

## 持久化回归验证

以下检查覆盖完整进程重启后读取当前标注、配方、处理结果和模型，以及继续编辑与中断任务恢复。Windows 下使用较短的测试目录，避免临时路径超过系统长度限制。

```powershell
New-Item -ItemType Directory -Path '.\build' -Force | Out-Null
& '.\.venv\Scripts\python.exe' -m pytest tests -q --basetemp '.\build\pytest'
node --experimental-strip-types --test tests/annotation-clicks.test.mjs
cargo test --manifest-path '.\src-tauri\Cargo.toml' --lib --locked
```

新项目的标注标签列表为空。导入仅登记数据，桌面端和编排助手均不再根据末级文件夹名称创建标签或绑定材料类别，也不默认创建背景标签。标签统一由用户在 AI 对话中明确创建，标注页仅使用和管理已有标签；标签独立持久化，无需先导入数据，重启后仍可管理。

助手接到通用导入请求后，会提供“尚未标注／已有标注”选择卡；用户已经说明标注情况时直接进入对应路线。可以粘贴原图路径，或使用文件、目录选择器，无需先配置数据源。尚未标注的数据登记后，由用户创建标签、选择超像素分割范围并人工点选。已有标注的数据先提供 ROI JSON 文件或目录，也可检查原图同目录；按 `source_hdr` 或受限于原图范围的 `imagePath` 配对，检查尺寸、区域、类别及来源信息，确认后接入工作台当前标注，在对话中配置预处理与训练，不生成超像素。数据页的“接入已有标注”也能为先前登记的样品打开该入口。

配对卡显示成功、未配对和异常数量，并可查看原图与 JSON 对应关系。用户可接入成功配对的部分，其余样品仍为待标注；不同的已有标注不会被导入覆盖。未标注像素保持未标注，不自动创建背景。导入选择与路径保存在本机会话中，恢复会话后可继续；旧批次按钮不能操作新批次。数据列表显示待标注、已标注可配置训练或已有配方结果，助手导入或接入标注后自动刷新。

通用导入和预处理配置不强制收集训练、测试四类目录。已有明确划分的 ENVI/JSON 和已整理的训练、测试 NPZ 仍可走原有实验入口；尚未划分的数据可在训练时选择按实物、批次或原图分组划分。需要学习参数的预处理仍须仅在训练集拟合，再应用于测试集。当前外部标注接入支持包含 `shapes` 的 ROI JSON（矩形或多边形）；其他标注格式须先适配，不能仅按文件后缀判定为有效标注。

人工标注与导入标注共用分类实验引擎。保存后点击“配置预处理与训练”，或发送“接下来对数据进行预处理”；也可在建模页进入统一对话。系统从保存的像素标注复制准确区域，排除留白、不确定与背景像素，默认单像元、步长 1、无附加预处理，所有设置均可在对话中修改。不会先运行旧配方，也不使用旧的 `workspace.classify` 分类工具。回归及高级配方处理继续保留原预处理页面，历史模型、结果和数据保留。

训练方案会列出每幅图的编号、名称和类别像素数。建议先按编号指定测试图片，例如“将第2、4张设为测试，其余用于训练”，再仅用训练集进行 Study，比较预处理与潜变量并采用推荐方案，审阅后确认正式训练。没有测试集时可先做探索性训练集内寻优，不能执行正式训练测试；全量寻优后需要新的未参与选模数据才能报告独立测试成绩。未知实物编号时明确按原图分组，不把同一张图的像素拆到不同验证折。波长单位缺失或波段轴不一致时需先在对话中明确单位或采用共同网格建议。

现有训练方案使用已复制的标注区域；修改画布不会改变已审阅的来源。若要采用新标注，先保存，再发送“使用当前已标注数据新建训练方案”。流程回归：`python -m pytest tests/test_workspace_training.py tests/test_data_intake.py tests/test_experiment_study.py -q`。

标签接入规则：ROI 文件只提供区域及类别对应关系，不创建项目标签；缺少标签时先在 AI 对话中创建，再点击“重新接入标注”。创建前后保留同一批次和配对结果。匹配不区分大小写；若旧项目同时存在 `pp` 和 `PP` 等多个候选，提示核对而不擅自选择或删除。既有标注与模型的标签身份不因这次升级而自动合并。

推理配色：新训练模型保存类别编号到项目标签颜色的映射，PNG 预测图、推理结果和 HTML 图例共用同一映射。旧模型若没有配色，按训练来源所属项目的明确同名标签读取颜色；无法唯一匹配时使用公共备用色。历史推理图和报告保留当时配色，重新推理才生成使用新规则的结果，不能只给旧报告换图例。已保存的模型配色不随后续项目改色而改变。

数据接入回归：`python -m pytest tests/test_data_intake.py -q`，前端目录与入口回归：`node --test tests/assistant-catalog.test.mjs`。

对话中输入“创建标签”或“请帮我创建标签”，助手会直接展示填写表单；也可以在导入完成卡片点击“创建标签”。支持用顿号、逗号、分号或换行批量填写，例如 `PE、PET、PP`，提交后在本机创建并保存，助手返回新增／复用数量，再点击“进入人工标注”继续。直接发送“为刚导入的数据创建标签，标签名称为：PE、PET、PP”也走相同的本机创建逻辑，不依赖模型联网。标签名称保留首次创建的写法，大小写同名复用同一个活跃标签；创建标签不会自动赋类、修改已有标注或添加背景。输入检查和整批写入为一个事务，重复提交不会重复建标签；恢复会话可读取结果。没有导入图片时，可先为唯一项目或当前选中图片所属项目准备标签。

对话标签回归：`python -m pytest tests/test_chat_labels.py -q`、`node --test tests/chat-labels.test.mjs tests/assistant-catalog.test.mjs`。

标签类别与样品区域标注分别显示：仅创建 `PE、PET、PP` 不会增加“已保存区域标注”数量。创建后点击“下一步：超像素人工标注”，选择本批样品逐张生成（推荐）或提前生成全部；分割就绪后从任务卡片进入画布，点选区域赋类并保存，随后在对话中配置预处理与训练。无需填写外部标注路径。卡片再次响应时会读取当前已保存标注，人工标注也计入数量；旧标签填写表单随历史消息收起。

开发态修改 Python 后端后，需要退出并重新启动桌面应用，前端热更新不会重新加载后台的 Python 模块。若导入后发送“创建标签：PE、PET、PP”却得到“当前没有可确定的数据”，先确认已重启到更新后的后台；标签创建按本次导入所属项目执行，无需先选中单个样品或重新导入。

标签列表提供删除按钮，弹窗确认后永久从可用列表移除，并清除所有图片当前工作态中该类标注和样品关联；撤销、重复导入和重启均不会恢复该标签。已保存的 JSON、标注快照和类别信息原样保留，数据库仅保留用于读取这些已保存结果的类别元数据。删除改变了当前标注，因此后续处理须基于当前标注重新预处理。再次创建同名标签会得到新的身份。

当前流程集成测试使用 6 张临时光谱图像，实际覆盖标注自动保存、配方原地更新、预处理、PLS-DA 分类及真值评价、PLS 回归、模型注册和推理；另有独立进程重启测试。兼容性检查使用提交 `bfe130f` 的旧代码生成带两份历史标注和配方的工作区，验证升级时 30 个产物文件完整保留、采用最新输入、重新处理可继续建模，连续保存不再增加版本行。

## 性能与内存设置

性能改造继续保留上述持久化行为，保留当前标注、配方和建模产物。算法及 `Parameters` 默认值未改变；实测、限制、逐项风险与回退方式见 [PERFORMANCE_REPORT.txt](PERFORMANCE_REPORT.txt)。

可选环境变量（设置后重启应用）：

| 变量 | 用途 |
| --- | --- |
| `SPECTRUMAGENT_CACHE_RETAINED_MIB` | 标注驻留预算，默认 128 MiB |
| `SPECTRUMAGENT_CACHE_RSS_FRACTION` | 物理内存占比上限，默认 0.5，须在 `(0,1]` |
| `SPECTRUMAGENT_CACHE_MEMORY_POLICY=legacy` | 回退到旧的保守临时预算 |
| `SPECTRUMAGENT_SOURCE_HASH_POLICY=strict` | 禁用操作内哈希去重，每次均全量校验 |
| `SPECTRUMAGENT_RASTER_CACHE=0` | 禁用相同草稿的像素图复用 |
| `SPECTRUMAGENT_HTTP_CLIENT_REUSE=0` | 禁用 Rust HTTP 连接池复用 |
| `SPECTRUMAGENT_EARLY_WINDOW=0` | 恢复等待引擎就绪后显示窗口 |
| `SPECTRUMAGENT_SLIM_BACKEND=1` | 构建时启用可选裁剪；默认关闭，保留 GDAL 驱动与数值依赖 |

测量脚本：`scripts/benchmark_performance.py`（真实数据与逐字节摘要）、`scripts/benchmark_desktop_startup.py`（隔离桌面进程）、`scripts/verify_frozen_backend.py`（onedir 真实 HTTP/数值/资源冒烟）。输出应放在 `.runtime/` 等忽略目录中；测试不会更改输入数据。

超像素点选支持连续点击：画布斜纹表示待同步预览，后台按点击顺序逐次落盘，每次点击保留独立撤销步骤。同步期间可切换已有标签；保存、撤销和切图等待同步完成。传输失败会停止后续点击并尝试读回实际状态，不自动重试状态未知的写入。待同步预览尚不代表落盘完成，退出前应等待同步结束。

`node --test tests/annotation-clicks.test.mjs` 覆盖快速连点、标签快照、刷新期间新增点击、失败停止及卸载边界。`scripts/benchmark_annotation_clicks.py --source <数据源> --output <全新绝对目录> --refresh-every 4` 测量真实标注请求，并记录每一步像素图、撤销图及最终光谱摘要。

当前分割仍使用整图 PCA/SLIC。框选提示只选择已有超像素，不等同于局部分割；面向目标物体的 ROI 掩膜分割需独立实现，并将区域信息纳入缓存与持久化标识。

## 重新生成发布安装包

使用 PowerShell 7，在仓库根执行：

```powershell
pwsh -NoProfile -File '.\scripts\build_release.ps1'
```

脚本使用现有 Python、Node、Cargo、NSIS 和 WebView2 工具缓存，执行 PyInstaller 冻结、包内 JSON 校验、完整后端资源暂存和 Tauri NSIS 构建。
该发布入口要求仓库内已有 `.venv`、`.toolchains/node24.19.0-npm10.8.2`、完整 Cargo 离线缓存，以及 `src-tauri/target/.tauri/NSIS/Bin/makensis.exe` 等打包工具。它们不会随 Git 克隆提供，前面的开发安装步骤也不会自动准备全部离线打包缓存。
资源暂存核对逐文件 SHA256，并把旧资源移入本次构建目录备份；禁止只替换 `app.exe` 或混用不同批次资源。
生产外壳必须启用 `custom-protocol`；发布脚本已包含该特性及 Cargo `--locked --offline`。
新的日志、备份和安装包写入 `artifacts/releases/0.4.1-<时间戳>/`，最终路径由 `SUCCESS:` 输出。
Cargo 离线模式不保证 WebView2 安装器封装完全离线，工具准备可能需要网络；失败时检查该批次日志。
历史 Python 端到端、冻结冒烟及清单内测试已移除；打包完成仍需验证实际桌面启动、关键业务链路和安装行为。
本次目录精简的 `npm run build` 检查不能替代重新冻结、安装包构建或安装态验收。

## 版本管理

保留 `.git/`、`.venv/`、`node_modules/` 和 `src-tauri/target/`，以及运行所需资源、锁文件与工具缓存。
根目录任务卡、`docs/`、`milestone*/`、临时目录和历史安装包不属于运行依赖。
本地与 GitHub 的默认分支均从当前本体快照建立唯一初始提交，旧分支和旧标签已移除。
旧任务卡、测试、历史安装包和旧提交不属于这份新历史，不能再用新仓库恢复它们。
后续开发在该初始提交上正常提交和推送；版本号以 `src-tauri/tauri.conf.json` 为准。
