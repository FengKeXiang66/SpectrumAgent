# 检查点 3：前端与 Tauri 工具链审批清单

状态：待负责人批准。下列安装、复制工具链、修改正式 package.json/Cargo.toml 的步骤尚未执行。本轮只修了握手路径显示，读取官方元数据并检查版本约束。

## 版本选择与核验依据

选 **Node 24.19.0 + 已有 npm 10.8.2**。Node 使用应用自带的现有二进制，不更换系统 PATH 的 Node；批准后复制到 E 盘项目工具链目录固定版本。npm 使用 D 盘已有 10.8.2 的本地副本，不下载另一版 npm。已经实际运行 Node 24.19.0 驱动该 npm CLI 的 `--version`，返回 10.8.2。

| 层 | 约束或实测 | 选择理由 |
|---|---|---|
| Tauri 2 | 官方 prerequisites 推荐 Node LTS；官方 Vite 接入页明确适用 Vite 8 | Node 官方当前把 v24 列为 LTS，采用已有 24 系列，不另装系统 Node |
| Vite 8.3.4 | engines.node=`^20.19.0 || >=22.12.0` | PATH 20.18.0 不满足；24.19.0 满足 |
| @vitejs/plugin-react 6.1.2 | 同一 Node engines；peer vite=`^8.0.0` | 与 Vite 8.3.4 相容 |
| ReactDOM 19.3.1 | peer react=`^19.3.1` | React 与 ReactDOM 都精确锁 19.3.1，对齐 ui-v2.3 §6.3 React 19 |
| TypeScript 5.9.3 | engines.node=`>=14.17` | 本轮只需严格 TS/TSX 检查；采用已验证版本，不在此里程碑引入 TypeScript 7 编译器迁移 |
| 类型包 | @types/react 与 @types/react-dom 最低 TS 5.6；@types/node 最低 TS 5.2 | TS 5.9.3 均满足；Node 类型锁在 24 系列，与实际 Node 主版本一致 |
| npm 10.8.2 | engines.node=`^18.17.0 || >=20.5.0`；Node 24 下 `--version` 实跑通过 | 重用已有 npm；不需要全局安装或升级 |
| Rust | 现有 rustc/cargo=1.99.1；下列四个 Tauri crate rust_version=1.90 | 满足四个直接 crate 的声明下限；实际 Tauri 编译尚待获批安装后验证 |

兼容性检查使用已安装 npm 自带的 semver 模块，不下载 semver。完整 engines/peer/类型最低版本判定见 compatibility-matrix.json。未选择的 optional peer（如 Sass、React Compiler）标明 optional，不把“未选择”冒充已安装。

官方资料：

- [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/#nodejs)：Node LTS、Windows C++ 工具及 WebView2 要求。
- [Tauri 的 Vite 接入](https://v2.tauri.app/start/frontend/vite/)：明确适用于 Vite 8，使用 devUrl/frontendDist 和构建钩子接入。
- [Vite Node 要求](https://vite.dev/guide/)；[Node 发布状态](https://nodejs.org/en/about/previous-releases)。
- [React 官方版本](https://react.dev/versions)；精确补丁版以本轮 npm 官方注册表 GET 为准。
- ui-v2.3 本地依据：[UI 文档 §6.3](/E:/中达瑞和公司/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.html:2489)，React 19；§2.1 常驻对话条。

实际包元数据、dist integrity、Cargo checksum 与 features 保存在 registry-metadata-20261018-163332-870623.json；跨 crate 约束保存在 cargo-dependency-metadata.json。它们只是注册表元数据，不是安装完成的 lock 或构建通过证明。

## npm 精确依赖：3 个运行时，7 个开发依赖

| 类别 | 包 | 精确版本 | 本轮用途 |
|---|---|---|---|
| dependencies | react | 19.3.1 | 四态页面、对话条及本地组件状态 |
| dependencies | react-dom | 19.3.1 | DOM 挂载 |
| dependencies | @tauri-apps/api | 2.12.4 | 固定 invoke 与状态事件；前端不读 token |
| devDependencies | vite | 8.3.4 | 本机开发服务器和静态资源构建 |
| devDependencies | typescript | 5.9.3 | strict=true，tsc --noEmit |
| devDependencies | @vitejs/plugin-react | 6.1.2 | React JSX 与开发刷新 |
| devDependencies | @types/react | 19.3.0 | React 19 类型 |
| devDependencies | @types/react-dom | 19.3.0 | ReactDOM 19 类型 |
| devDependencies | @types/node | 24.10.1 | Vite 配置所用 Node API 类型 |
| devDependencies | @tauri-apps/cli | 2.12.3 | 项目本地 Tauri dev/build/插件接入命令 |

可审阅的完整前端 manifest 为同目录 package.proposed.json，尚未放到仓库根。所有直接版本用精确值，无 `^`/`~`。Tauri API/Rust 与 CLI 补丁号不同，采用各自实际发布版本；本轮只确认版本声明与约束，不能提前声称整套构建通过。

TanStack Query / Zustand / TanStack Table 按封版选型留在后续业务里程碑引入；本轮四态用 React 状态，不自研替代三件套。图表、UI 组件库、HTTP 封装库等均不在此次清单。

## Rust 新增精确依赖：4 个

现有五个直接依赖及其精确版本保持。现有 53 个 Python 包负责引擎，现有 Rust 五包负责监督器，均不提供桌面 WebView 宿主、Tauri 构建或官方单实例插件，因此新增下列包。

| 位置 | crate | 精确版本 | 功能 |
|---|---|---|---|
| dependencies | tauri | =2.12.4 | Tauri 2 窗口、事件、固定命令桥、Resource resolver |
| build-dependencies | tauri-build | =2.7.3 | 构建配置/能力生成、嵌入自定义 Windows manifest |
| dependencies | tauri-plugin-single-instance | =2.5.4 | 官方单实例，必须第一个注册；不手写第二把产品锁 |
| dependencies | tauri-plugin-opener | =2.7.2 | Rust 固定无参命令打开数据目录，前端不能指定任意路径或 URL |

拟采用的功能设置：

```toml
tauri = { version = "=2.12.4", default-features = false, features = ["wry", "compression", "common-controls-v6", "dynamic-acl"] }
tauri-plugin-single-instance = "=2.5.4"
tauri-plugin-opener = "=2.7.2"
# [build-dependencies]
tauri-build = { version = "=2.7.3", default-features = false, features = ["config-json"] }
```

已核对：tauri 要求 tauri-build ^2.7.3，两插件要求 tauri ^2.12，均包含本计划精确值。Windows 宿主需要 wry，保留 Common-Controls v6；不启用 Tauri 的 native-tls/rustls-tls 等可选功能。最终传递功能图以下载后的 cargo tree 为准，不把当前四个直接声明当作全部传递依赖已经验证。

Single Instance 官方没有 JS API，所以没有对应 npm 包。[官方插件说明](https://v2.tauri.app/plugin/single-instance/)。Opener 只在 Rust 内调用固定数据目录，不给前端开放通用 opener 命令，也不安装 JS guest 包。[Rust Opener 用法](https://v2.tauri.app/plugin/opener/)。

## 安装与下载命令（待批准，未执行）

批准后先把现有 Node/npm 复制到 `E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2\`：node.exe 来源为应用现有缓存，npm.cmd/npx.cmd/node_modules\npm 来源为 `D:\Install\nvm\nodejs\`。此目录仅用于开发，不进入交付资源或 Git。源 Node SHA256 已实测为 `3602f2bb1a10f2cbab4c36886218a33c1ab3db87290e73b033c46c77147d0237`；复制前后必须一致，并再次实跑两版号。若目标已存在，校验一致后复用，不覆盖未知内容。

运行各命令前显式设置以下进程环境；不会修改用户/系统 PATH：

```powershell
Set-Location -LiteralPath E:\AI_Agent
$toolchainDir = 'E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2'
$nodeExe = Join-Path $toolchainDir 'node.exe'
$npmCli = Join-Path $toolchainDir 'node_modules\npm\bin\npm-cli.js'
$env:PATH = "$toolchainDir;$env:PATH"
$env:npm_config_cache = 'E:\AI_Agent\.npm-cache'
$env:npm_config_prefix = $toolchainDir
$env:CARGO_HOME = 'E:\AI_Agent\.cargo-home'
$env:CARGO_TARGET_DIR = 'E:\AI_Agent\src-tauri\target'
$env:TEMP = 'E:\AI_Agent\artifacts\step3\checkpoint-3\temp'
$env:TMP = $env:TEMP
$env:PYTHONIOENCODING = 'utf-8'
& $nodeExe --version
& $nodeExe $npmCli --version
```

正式 package.json/Cargo.toml 按审批精确版本落盘后，拟执行：

```powershell
& $nodeExe $npmCli install --save-exact --engine-strict 'react@19.3.1' 'react-dom@19.3.1' '@tauri-apps/api@2.12.4'
& $nodeExe $npmCli install --save-dev --save-exact --engine-strict 'vite@8.3.4' 'typescript@5.9.3' '@vitejs/plugin-react@6.1.2' '@types/react@19.3.0' '@types/react-dom@19.3.0' '@types/node@24.10.1' '@tauri-apps/cli@2.12.3'
& $nodeExe $npmCli run tauri -- add single-instance
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' fetch --manifest-path E:\AI_Agent\src-tauri\Cargo.toml
```

单实例接入按任务卡使用官方 CLI。该 CLI 的精确插件版本参数尚未本地验证（CLI 尚未安装；对应源码读取超时）；先用获批 CLI 的 add --help 核对。上面的自动 add 只在官方稳定版本仍是已审批的 2.5.4 时执行；若其行为可能下载其他直接版本则停下报告，不接受浮动升级。自动接入结果需复核为本计划的 `=2.5.4` 后再进入正式构建。其余 crate 直接按精确 manifest 取包，不执行无差别 cargo update。

命令只安装项目依赖；传递依赖和 Windows 平台可选包由 package-lock.json/Cargo.lock 固定。安装后执行并保存：

```powershell
& $nodeExe $npmCli ls --all
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' tree --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --locked --offline
& $nodeExe $npmCli run build
```

首笔前端/Tauri 宿主实现提交必须同时归档 package-lock.json 和更新的 Cargo.lock；Python requirements-lock.txt 保持原样。现在两份既有 lock 都没有修改，也没有运行上述命令。

## 固定 run_smoke 的客户端范围：一并申请确认

之前负责人的授权把 reqwest 限定在 /health。本次 UI 的 run_smoke 需要固定冒烟请求，建议**仍用现有 reqwest 0.13.5**，将范围扩为：已校验本代 PID/创建时间/boot_id 后，仅访问该握手确认的 `127.0.0.1` 上固定 `/health` 与 `/smoke`。前端只调用无参 run_smoke，不传 URL、端口、HTTP 路径或 Authorization；token 留在 Rust 内部，禁代理/重定向，阻塞请求放工作线程。没有外网请求或新增 HTTP 包，也不改引擎接口契约。

这一范围扩展尚未实施，需与安装清单一起批准；批准前现有 reqwest 仍只请求 /health。

## 本轮已验证与后续检查点

已验证：Windows 路径显示修复的针对性回归 1 passed、clippy 无 warning；当前 Node/npm 版本与组合运行；所选直接版本存在、必需 peer/Node/type 约束；Rust 工具链；WebView2 注册表版本 155.0.4283.62 与已安装 C++ BuildTools 路径。实际 Tauri 链接、Vite/tsc 构建、WebView2 窗口运行仍未验证。

批准后按顺序接 Tauri host 与四态 UI：Starting 隐藏；Ready/Failed 才显示；Failed 中文原因、实际退出码/路径/重试和固定数据目录入口；对话条 Ready 支持真实冒烟，Failed/Stopping 禁用；Ctrl+K 聚焦、Ctrl+Enter 发送；未知输入明确告知本演示仅支持冒烟测试。完成该检查点自检后停下汇报，再进入最终 release 验收。

最终 release 的 FaultFixture/Canonical 双模式暂存、resource resolver/--no-bundle 实际布局、关窗/强杀矩阵仍按既定方案留到后续，未提前报通过。第 2 步继续“待实机验证”，旧 code=70 原因继续“未验证”。
