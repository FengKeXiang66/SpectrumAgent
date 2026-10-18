# 阶段一开工任务卡 #01：地基演示（Week 1）

## 路径约定（先读这条）

- **代码根目录：`E:\AI_Agent\`** —— 所有代码、构建产物、lock 文件只落在这里
- **文档目录：`E:\中达瑞和公司\`** —— 三份必读文档在那边，**不要复制进代码根**，按绝对路径阅读
- **数据根目录：`%LOCALAPPDATA%\SpectrumAgent\`** —— DB / 日志 / 缓存 / 握手文件，安装目录视为只读

## 背景

光谱数据 AI-Agent 处理平台（阶段一 · 单机版）。最终形态：**Windows 安装包（setup.exe）**，单人单机，内网离线可用。本任务产出一个「能装、能开、能关干净」的外壳 + 引擎骨架，后续所有功能长在骨架上。

## 开工前必读（按顺序读完再动手）

1. `E:\中达瑞和公司\光谱数据AI-Agent处理平台_需求分析与设计.html`（v2.6，132 条需求；**阶段一交付 100 条，其中 P0 63 条**）
2. `E:\中达瑞和公司\光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.html`（ui-v2.2，11 屏原型）
3. `E:\中达瑞和公司\光谱数据AI-Agent处理平台_阶段一技术选型_定稿v1.1.md`（**已封版 v1.1，选型以它为准**；v1.0 已被取代，仅作历史留存，不要读）

冲突处理：三份文档凡与定稿冲突处，以定稿 v1.1 为准。定稿第三节列有 9 条须同步的文档升版（需求 v2.7 / ui-v2.3），由项目负责人另行处理，本轮编码按定稿执行。

## 目标目录结构（本轮建成）

```
E:\AI_Agent\
├── backend\                          Python 3.12 引擎（FastAPI）
├── src-tauri\                        Tauri 2 外壳（Rust）
├── src\ + index.html + package.json  React 19 + TS + Vite 前端（本轮只放占位页）
├── requirements-lock.txt             引擎依赖锁（构建归档）
├── package-lock.json                 前端依赖锁（自动生成）
└── src-tauri\Cargo.lock              Rust 依赖锁（自动生成）
```

## 环境已就位（2026-10-18 实测，不必再验）

| 组件 | 实测结果 |
|---|---|
| Python 引擎环境 | `E:\AI_Agent\.venv`，CPython **3.12.13**，53 包，`requirements-lock.txt` 已冻结（946 B / 53 行） |
| 依赖冒烟 | `import pysptools, spectral, rasterio, sklearn, pywt` 全绿；PCA（64×4）通过；`CRS.from_epsg(4326)` 通过（PROJ 数据库可用） |
| Rust | 1.99.1，host **x86_64-pc-windows-msvc**，`rustc main.rs` 编译+链接+运行实测通过 |
| MSVC | BuildTools 2022 17.14.42，MSVC 14.44.35207，`link.exe` 在位 |
| Windows SDK | 10.0.26100.0 |
| Node / npm | 22.22.2 / 10.9.7 |
| WebView2 运行时 | 155.0.4283.60 |

**已知环境坑（会踩，提前知道）**

1. **`pysptools` 算法子包在 import 期会顺带拉起 matplotlib**（2026-10-18 实测，链条已钉死）：`noise/inval.py`、`noise/dnoise.py` 里都写着 `import pysptools.util` → `util/__init__.py` 无条件 `from .display import ...` → `display.py` 顶层 `import matplotlib.pyplot`。因此 `pysptools.noise` / `eea` / `abundance_maps` / `classification` 等 **10 个子包 import 全失败**；例外是 `distance` / `sigproc` / `tests` 可以裸 import。注意算法文件本身（`dnoise_int.py`、`amaps.py`）顶层是干净的 numpy/scipy，matplotlib 只出现在 display 方法或函数体里——**卡点在传递链，不在算法本体**。顶层 `import pysptools` 是空包，会假性通过——**不要用顶层 import 当作依赖可用的证据**。
2. **本轮不装 matplotlib**（无头引擎不背 GUI 绘图库，且 PyInstaller 打包 matplotlib 是已知雷区）。MNF 走待决项 D-01。
3. `spectral==0.25`、`pysptools==0.15.0` 均无 wheel，安装时现场源码构建；lock 必须归档，否则干净机器重建慢且可能失败。
4. `uv` 安装时提示 `Failed to hardlink files` 是缓存跨文件系统的警告，不影响结果，可忽略。

## 技术栈（封版，不许替换）

- 外壳：Tauri 2.x（Rust）+ React 19 + TypeScript + Vite
- 引擎：Python 3.12（锁死）+ FastAPI + uvicorn（127.0.0.1）+ Pydantic v2
- 打包：PyInstaller **onedir** → 产出放进 `src-tauri/resources/backend/` → `tauri.conf.json` 的 `bundle.resources` 声明 → Tauri 内置 bundler（NSIS，`installMode=currentUser`，`webviewInstallMode=offlineInstaller`）
- **不走 externalBin**（它只接受带 target triple 后缀的单文件，onedir 目录不适用）

## 接口契约（实现前先按这个定，不许自行改形状）

> 这一节是**决策**，不是建议。改动任何一条须先问负责人。所有路径、字段名、状态码按此实现。

### 1. 握手文件 `%LOCALAPPDATA%\SpectrumAgent\run\handshake.json`

引擎在**真正可服务之后**原子发布（先写 `.tmp` → `os.replace`，禁止读到半份 JSON）：

```json
{
  "boot_id": "8f3c1a2e",          // 本次启动随机标识，每次启动都不同
  "pid": 12345,
  "process_created_at": "2026-10-18T09:12:33.412Z",  // 进程创建时间，用于区分 PID 复用
  "port": 51789,
  "token": "32位hex",
  "protocol": 1,
  "version": "0.1.0",
  "started_at": "2026-10-18T09:12:34.007Z"
}
```

端口用 **`port=0`** 交给内核分配，绑定成功后再读实际端口写入握手（不要"探测空闲端口→释放→重绑"，那有竞态）。

### 2. 外壳启动流程（顺序不许调换）

1. 取单实例锁；已存在实例则激活其窗口后退出；
2. 读旧握手文件 → 若存在，核验 `boot_id` / `pid` / `process_created_at`：进程已死或不匹配 → 删除旧文件；**任何情况下都不复用旧握手**；
3. **以挂起方式创建引擎进程**（`CREATE_SUSPENDED`）；
4. 创建 Job Object 并设 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`，把引擎加入；**加入失败 → 终止引擎并报启动失败**（不许继续跑）；
5. 恢复引擎主线程；
6. **同时等待两件事**：`/health` 就绪、子进程退出；
   - 先拿到健康 → 显示窗口；
   - 子进程先退出 → **立即**进入失败界面（显示退出码、日志路径、重试按钮），不许继续转圈；
   - 两者都没发生 → 30 秒超时，进入同一失败界面。

### 3. `/health`（不鉴权，仅探活）

`200 {"status":"ok","boot_id":"8f3c1a2e","pid":12345,"version":"0.1.0","uptime_s":12.3}`

外壳必须核对返回的 `boot_id` 与本次握手一致——**端口上跑着别的服务也返回 200 时，靠这一条拦住**。

### 4. `/smoke`（需鉴权）

成功 `200 {"nan_ratio":0.0,"reflectance_range":[0.0,1.0],"bands":8,"shape":[8,8,8],"elapsed_ms":12.4}`
失败 → 非 2xx + `{"error":"<短码>","detail":"<人读信息>"}`

### 5. 鉴权

除 `/health` 外，所有请求带 `Authorization: Bearer <token>`（token 来自本次握手）。随机端口不等于别人扫不到，一行校验能挡掉本机其他程序的误调用。

### 6. 安装后路径

`<install>\resources\backend\app.exe`；Rust 侧用 `resource_dir()` 拼接，**禁止依赖当前工作目录或开发机路径**。

### 7. 日志

- 引擎：`%LOCALAPPDATA%\SpectrumAgent\logs\engine-YYYYMMDD.jsonl`（structlog JSON 行）
- 外壳：`%LOCALAPPDATA%\SpectrumAgent\logs\shell-YYYYMMDD.log`
- `/smoke` 用的假数据写到 `%LOCALAPPDATA%\SpectrumAgent\testdata\`，**不许写输出根，更不许写源目录**

### 8. 取消语义（本轮只需在 `/smoke` 上留接口，不必做完整实现）

`Future.cancel()` 停不下正在运行的计算。长任务必须切成块、每块前检查取消标志；取消后不再提交新块，已完成结果保留并标 `status="cancelled"`、`metrics_complete=false`。**禁止把被取消的 run 标成成功。**

## 本轮必须实现的机制

1. 引擎监听**随机端口**（`port=0` 由内核分配，不硬编码），端口经握手文件 `%LOCALAPPDATA%\SpectrumAgent\run\handshake.json` 交给外壳（格式见「接口契约」第 1 条）
2. 外壳拉起引擎（挂起创建 → 入 Job → 恢复）→ **同时**等 `/health` 与子进程退出 → 就绪才显示窗口（首屏一个「hello 对话条」占位，对应 UI 一级入口：每屏底部常驻对话条）；子进程提前退出立即显示失败界面，不许永久转圈
3. **Windows Job Object（KILL_ON_JOB_CLOSE）**：关窗时由内核回收整个进程组，不留孤儿引擎进程；加入 Job 失败必须终止启动，不许放行
4. **单实例锁**：重复双击只激活已有窗口
5. 可写数据全部落 `%LOCALAPPDATA%\SpectrumAgent\`；安装目录只读；**DB 绝不落 NAS 共享目录**
6. structlog 结构化日志从第一行代码启用
7. 临时冒烟端点 `GET /smoke`：读一份 ENVI（无样本时先用脚本造 8×8×8 float32 假立方体 + .hdr）→ SNV → 返回 `{nan_ratio, reflectance_range}`

## 本轮明确不做（越界即回退）

- 不写正式光谱业务算子（SNV 仅在 `/smoke` 演示一次）
- 不引 PyTorch / CUDA、Docker、PostgreSQL、Redis、MinIO、Celery、Faiss、LangGraph
- 不做 UI 美化、登录 / 账号、完整数据库表设计（SQLite 连接占位即可）
- 不碰 NAS 挂载与只读守卫（那是导入里程碑的事，但预留好路径常量的位置）

## 验收标准（全部满足才算完成）

1. 干净 Win10/11 上双击图标到可交互——**记录实测值（分三段：引擎就绪 / 双击到可操作 / 首次算法调用），不预设 ≤3 秒为通过线**；超时如实报告，不许用暖启动或开发机替代
2. 任务管理器只有一个外壳进程组；**正常关窗、任务管理器强杀外壳、启动过程中强杀**三种情况，关后均无任何残留引擎进程（每轮核验 PID 与端口，至少重复 10 轮）
3. 拔网线 / 禁网卡后运行 `setup.exe` 可正常安装（WebView2 随包离线安装，不静默失败）
4. 断网状态下启动应用，`/smoke` 返回正常指标
5. 数值栈最小调用通过：**PCA**（sklearn，64×4 假数据）与 **SNV**（numpy，8×8×8 假立方体）各跑一次并输出可读指标。**本轮不实现 MNF**（见 D-01）
6. `requirements-lock.txt` + `package-lock.json` + `Cargo.lock` 三套 lock 随代码归档
7. **rasterio 打包验证（2026-10-18 实测修订）**：PyInstaller onedir 产物在不借用外部 Python / 系统 GDAL 的测试环境下能写入并读回 GeoTIFF。spec 使用 `collect_submodules('rasterio')`（包含 Cython 层动态导入的子模块）与 `collect_data_files('rasterio')`（`proj.db`、`gdalvrt.xsd` 等数据）。**明确允许 PyInstaller 二进制依赖分析自动收集**扩展与依赖库，不再要求显式调用 `collect_dynamic_libs`，不要盲目重复收集 DLL。验收依据为冻结产物实际包含 **36 个 rasterio.libs DLL、15 个 rasterio pyd**，以及冻结态 GeoTIFF 的 CRS / shape / 波段数 / transform / 数据读回断言。**本产物 `GDAL_DATA` / `PROJ_DATA` / `PROJ_LIB` 三变量均为 null，rasterio 从包内相对路径成功解析数据**，不再要求运行时设置变量；其他版本及显式设置变量时的兼容性不由这一结果泛化。GeoTIFF **已实测通过，作为验收依据保留**，原“验不过就从 `/smoke` 摘掉”的降级条款关闭。hook 自动收集、包内相对数据路径和三个变量的兼容性均列入 v1.2 澄清候选，本轮不改定稿 v1.1 正文。
8. **握手失效路径**：① 陈旧握手（旧 PID 已死，或旧 PID 存活但 Windows 实际创建时间与旧握手不同，即 PID 复用）→ 删除前重新读取并确认仍与刚才判定的记录一致，清扫后重建并发布新握手；合法所有者（旧 PID 存活且其实际创建时间与旧握手匹配）→ 不得删除或覆盖，必须在绑定服务和发布握手前拒绝启动并明确报错；非法 JSON / 缺字段 / 非法时间 / 无法查询所有权一律 fail closed，不自动删除。判定查询的是**旧 PID 的实际创建时间**，禁止与当前新进程的创建时间比较。② 让另一个服务占住旧端口并返回 200，外壳必须靠 `boot_id` 校验识破；③ 移走一个必需 DLL 让引擎启动即退出，外壳须在约 2 秒内显示失败界面（含退出码与日志路径）
9. **取消语义**：`/smoke` 支持传入块数并在块间检查取消标志；取消后不得提交新块，返回 `status="cancelled"` 与 `metrics_complete=false`

## 待决项 D-01（MNF / VCA / FCLS 实现路线）

- **背景**：pysptools 算法子包在无 matplotlib 环境下 import 被 util/display 链堵死（见环境坑 1）；且实测 **pysptools 0.15.0 没有 VCA**（`eea/__init__.py` 仅导出 PPI / NFINDR / ATGP / FIPPI），**FCLS** 函数体 lazy 依赖 `cvxopt`（`abundance_maps/amaps.py:132`，C 扩展，又一个 PyInstaller 雷）。定稿"pysptools 提供 MNF/VCA/FCLS"在该版本部分失效，本条目即修订留痕。
- **已实测可用（2026-10-18）**：`spectral.algorithms.mnf` 全程 numpy，**就用验收同款的 8×8×4 假立方体跑通**（入口：`from spectral.algorithms.algorithms import mnf, calc_stats, noise_from_diffs`；`mnf(signal, noise)` 返回 `MNFResult`，`.reduce(data, num=)` / `.denoise(data, snr=)`）。
- **候选 A（推荐）**：MNF 走 `spectral.algorithms.mnf`——零新增依赖、已实测、装机即用。
- **候选 B**：MNF 用 numpy/scipy 自实现（噪声协方差差分估计 + 白化 + PCA，约 40–60 行），定稿 5.4 备选列已预留，仅作 A 不可用时的 fallback。
- **候选 C**：安装 matplotlib 恢复 pysptools 常规 import。代价约 +60MB 且 PyInstaller 要背 backend hidden imports；**且解决不了 VCA 缺失与 FCLS 的 cvxopt 依赖**，暂不建议。
- **FCLS / VCA**：阶段一后段功能，临近实现时再定——FCLS：引 cvxopt vs scipy NNLS + 和约束自研（约 20 行）；VCA：自研（约 40 行）vs 换源调研。现在只记触发条件，不预埋代码。
- **定夺时点**：MNF 算子开发前（阶段一第 2–3 周）。若最终选自研，用**临时 venv**（装 matplotlib + pysptools）生成 golden 对照，主环境保持干净。
- **本轮动作**：不实现 MNF 算子、不引入依赖、不做任何桩代码（禁止用假 matplotlib 模块骗过 import，那会给未来埋雷）。

## 完成后提交

### 第 2 步生命周期补充验收（2026-10-18）

- 引擎握手启动事务由 `Local\SpectrumAgent.EngineHandshake.Startup.v1` 命名互斥锁串行化。`CreateMutexW(bInitialOwner=false)` 后统一 `WaitForSingleObject(30000)`；锁仅在 `HandshakeServer.startup()` 内持有，从旧握手判定/清扫覆盖到 HTTP 启动、自身健康检查和原子发布，最后准确释放并关闭句柄。不替代第 3 步产品级单实例锁。
- **启动清扫**删除旧代握手，成功记录含旧所有者非秘密字段的 `stale_handshake_removed`；**关闭清理**在 ASGI lifespan shutdown 删除本代握手。`main()` finally 只保留 best-effort 兜底；只有实际删除本代握手的路径记录 `engine_stopped`，每个 boot_id 最多一次。
- CTRL_BREAK 即时清理与 CTRL_C / taskkill 恢复是两项独立验收。dev 与 frozen 各信号组合至少 5 轮；确认握手已发布后到退出判定前，脚本不得删改握手。每轮按 boot_id 保存退出码、PID、端口、握手状态与日志计数。
- CTRL_BREAK 验证 lifespan 到达、恰好一次 `engine_stopped`、PID/端口/握手消失。CTRL_C 与强杀允许残留，禁止称其“优雅退出无残留”；下一次启动必须由引擎清扫残留并记录事件，随后用 CTRL_BREAK 验证最终清理。不为 Ctrl+C 劫持或屏蔽引擎信号处理。
- 额外覆盖外来陈旧握手存留后恢复、合法所有者保护和 PID 复用。诊断模式在 engine_boot 前分派，不启动 Uvicorn、不绑定服务、不发布握手；用 diagnostic_started 记录诊断，并验证主握手前后字节不变及 worker 未进入引擎路径。
- 第 2 步旧 8a 偶发 PASS 不证明稳定性，相关通过结论撤回；保留首次 FAIL、偶发 PASS 和后续复现原始记录。新回归全部通过且证据可复核后才可提交验收，未经负责人确认不开始第 3 步。

- `setup.exe` 及构建说明（如何在干净 venv 中复现 onedir 构建：dev venv 开发 → freeze → 干净 venv 内 PyInstaller 构建）
- 一段 30 秒操作录屏或分步截图：安装 → 启动 → `/smoke` → 关窗 → 任务管理器确认无残留

## 动手前纪律

- 先复述一遍上面的验收标准，再开始写代码
- 任何对技术栈 / 目录约定 / 机制的改动，先停下来问负责人，不许自行替换
