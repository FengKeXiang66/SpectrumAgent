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
2. 在标注工作台选择类别，使用超像素点选、手工区域等方式标注并保存版本。
3. 选择标注/训练集版本和预处理配方，检查处理结果，再进行建模。
4. 执行 PLS 回归或 PLS-DA 分类、波段选择、交叉验证和批量推理。
5. 在结果页查看指标、诊断、实验比较，并按需导出图件、数据和报告。

常驻对话入口负责工具编排与结果解释；数值、指标和证据由确定性后端生成。
使用云端对话前，在设置中配置供应商、模型和密钥，并检查“允许外发”设置。
关闭外发仍可使用本地导入、标注、预处理和建模；首次配置前无需联网运行这些本地功能。

## 数据与会话生命周期

- 原始数据按引用读取，导入不等于把原始光谱复制进本仓库；请保留源文件及其路径。
- 桌面程序默认在 `%LOCALAPPDATA%\SpectrumAgent` 保存应用配置和外壳日志。
- 数据库、草稿、标注、处理与训练产物位于该目录的 `sessions/<时间戳>-<PID>/`。
- **退出应用会清理本次会话数据**，崩溃残留会在下次启动时回收；需保留的结果应先显式导出到自选位置。
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
