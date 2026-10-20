# 里程碑 #03 · 打包里程碑（冻结尾像统一 + release 发布 + 成品冒烟）

状态：**已批准，待转 codex**。前置：#02 已过闸（HEAD=f4e5c90），#01 已封账（setup.exe 287,156,790 B / SHA256 d8492536…cc8107）。决策：D1=A（release 注册 datasets_forward）、D2=0.1.1。
产出目标：一个包含数据接入能力的 **release 安装包**（新 revision 的引擎冻结尾像 + NSIS 安装器），核心冒烟链在科祥本机单轮通过，证据链与 #01 同级。

---

## 一、探针实证的前置事实（2026-10-19 复核时实测，codex 不必重新探，但引用时以 file:line 自检）

1. **两棵 Python 树并存，且当前互不相通**：
   - `backend/`（#01 引擎，engine.py / handshake.py / identity.py / app.py 等）——**打包入口**，`artifacts/step2/build.spec` 的 Analysis 入口是 `backend/__main__.py`；
   - `src-python/spectrumagent/`（#02 新代码：data/ readers + api/datasets）——**dev 联调树**，`scripts/dev_sidecar.py:12` 把 src-python 插到 sys.path 最前，`:36` 调用 `spectrumagent.app.create_app`。
2. **release 引擎目前没有 datasets 路由**：`backend/engine.py:44` 调用 `backend.app.create_app`（foundation only）；而 `src-python/spectrumagent/app.py:5-13` 才是 foundation + datasets router 的组合。→ 直接打现在的包 = 发布一个**没有数据接入能力**的安装器。
3. **冻结尾像现状**：`src-tauri/resources/backend/` = #01 冻结树（app.exe 16,771,455 B / SHA256 3f62c189…，整树 544 文件 / 255,564,789 B，见 #01 `product-manifest.json`；git 未跟踪，属构建产物）。此为 **10-18 旧码**，不含 #02 任何代码。
4. **配置事实**（src-tauri/tauri.conf.json）：targets=["nsis"]、自定义模板 nsis/installer.nsi、webviewInstallMode=offlineInstaller、installMode=currentUser、resources 映射 `resources/backend/`、version 0.1.0。**禁止写绝对路径**（#01 prompt-final.md:403 已立）。
5. **依赖事实**：dialog/rfd 已成常驻依赖（Cargo.lock 445→458 +13 / package-lock 64→65 +1，已审计）；PyInstaller 6.22.3 + pyinstaller-hooks-contrib 2026.8 在 venv lock 内（#01 已在用，非新增）；venv = CPython 3.12.13、无 matplotlib，spectral 0.25 在其下工作正常（141 测试实证）；`src-python/spectrumagent/data/readers/envi.py:3` 顶层 `from spectral.io import envi` → **冻结尾像必须收录 spectral 包**。
6. **当前源码全量测试绿**（今日已由负责人独立复跑）：pytest 141 passed、cargo test 默认并行 22 passed（21+1 文档测试）、node --test 2/2、clippy -D warnings 通过、tsc exit0、vite build 通过（证据在各 evidence 文件）。

---

## 二、任务分解（按序执行）

### P0（先做，小）· #01 REPORT.md 三项补丁收尾
1. 记忆键归属：改为「Tauri 2 NSIS 安装器标准行为」（MANUPRODUCTKEY，installer.nsi:68-69/:698/:164-166/:889 已口径化，见 artifacts/step3/checkpoint-4/vm-runbooks/VM-BUILD-Win11Clean.md 对照表）；
2. 握手残留：追加负责人拍板 A（记已知问题、不进 0.1.1 热修、自愈已实测两次）；
3. smoke 计时 24.146ms：**在负责人指认轮次前不得粘用**；若不指认，换可采值：engine smoke 178.243 / 211.154 / 208.095 / 316.615 ms，desktop 1292 / 1060 / 1178 ms，并注明档位来源。

### P1 · 引擎入口统一（架构变更，最小改）
- `backend/engine.py:44` 改调 `spectrumagent.app.create_app(paths, identity)`（即 src-python 的组合 app），使 **release 引擎天然带 datasets 路由**；`scripts/dev_sidecar.py` 保持不变（dev 直启 src-python）。
- 摘要说明写入 REPORT：dev/release 从此共用同一 create_app，差异只剩解释器来源（venv vs onedir）。

### P2 · release 注册 datasets_forward（D1=A 已裁定：开放）
- `src-tauri/src/main.rs`：`#[cfg(not(debug_assertions))]` 分支的 invoke_handler 加入 `datasets_forward`；dev 分支不变。此为经批准正式越过 #02 期"release 四命令不动"临时红线的唯一变更点。
- **`datasets_dev` 模块（转发器本体）必须一并转为无条件**：release 分支的 `datasets_forward` 命令直接引用 `spectrum_agent::datasets_dev::{DatasetRequest, ForwardError, forward}`（见 4.6-release-boundary.diff），而 `lib.rs` 现将其 `#[cfg(debug_assertions)]` 门控——只注册命令不转模块 = release 编译失败。仅 `dev_engine.rs`/`dev_supervision.rs`/process.rs+win32.rs 的 venv 收养逻辑保持 debug-only。
- `supervisor.dataset_identity()` 当前是 `#[cfg(debug_assertions)]`，需改为无条件（引擎代次查询是通用能力，与 venv 无关）。
- `capabilities/main.json` 描述文本同步（去掉"release不注册该handler"措辞）；重新生成 ACL/schema 并入库；更新 release 边界 audit JSON（新字面量 = 五命令）。模块名是否随转正改名由 codex 定（保持 `datasets_dev` 亦可接受，最小 diff 优先）。
- 转发器约束不变：仅 127.0.0.1 握手端口、白名单 /api/v1/datasets/*、GET/POST、8MiB、代次校验。

### P3 · 重新冻结 onedir（PyInstaller）
- 改 `artifacts/step2/build.spec`：Analysis **pathex 增加 `ROOT/src-python`**（使 spectrumagent 可被分析跟随）；hiddenimports 增加 `collect_submodules("spectrumagent")` 与 `collect_submodules("spectral")`；其余（rasterio/uvicorn 收集、distpath/workpath、onedir 布局）保持。
- **禁止手工改 GDAL/PROJ 环境注入**（#01 既有结论保持）；确认 spectral 不拖 matplotlib（venv 无 matplotlib 已实证，冻结同理，PyInstaller 分析跟随验证）。
- **版本号口径（重要，含禁区）**：产品版本 `src-tauri/tauri.conf.json` version → **0.1.1**（安装器/产品身份）。`package.json`、`src-tauri/Cargo.toml`、`backend/app.py:62` 的 OpenAPI title version 可随之升 0.1.1（ cosmetic，不强制）。**禁区：`backend/__init__.py:3 __version__` 必须保持 "0.1.0"**——它是握手协议常量：`backend/identity.py:11/74/83` 把它写进握手 payload，`backend/handshake.py:69` 与 `src-tauri/src/handshake.rs:128-129` 两侧硬编码校验 `== "0.1.0"`；一旦改 0.1.1，release 引擎写的握手会被 Rust 监督器当场拒绝 → 引擎永不 Ready → 安装包装完即坏。要动它就是双边协议变更，本里程碑明确不做。
- 用 #01 既有 manifest 生成器重新生成 `product-manifest.json`，写入**新的 revision 目录**（如 `artifacts/step2/revision-20261019-m02/`），**不得改动 #01 既有 revision 树**。
- 冻结后复制到 `src-tauri/resources/backend/`（替换旧树），记录整树文件数/字节/app.exe SHA256。

### P4 · release 打包
- 按 #01 既有链路：PyInstaller spec → resources/backend → `npm run tauri build`（beforeBuildCommand 自动跑 tsc+vite）→ NSIS bundle；**逐字记录实际命令与退出码**（不凭记忆复述命令）。
- 记录 setup.exe 的 SHA256 与字节数，与 #01 的 287,156,790 B 对比，实测 dialog/rfd 常驻带来的体积增量（记录实际值，不预估）。
- 打包全程使用 E 盘 TEMP/TMP（沿用 #01 环境约定，见 4.6-build-environment.json 的做法）。

### P5 · 最终源码全量测试复跑（默认参数）
- pytest 141 / cargo test（**默认并行，禁 --test-threads**）/ node --test / tsc / clippy -D warnings / vite build，逐项贴原始输出。
- 验收口径：**各项计数不得低于今日复核值（141 / 22 / 2）**；如因 P2 合理新增用例而增加，须在报告中列明增量与用途；任何一项变少或红即停。

### P6 · venv(dev) vs onedir(release) 行为差异复验
- 参数化 `scripts/selfcheck_milestone02.py`（或等价最小改动）：以环境变量指定引擎启动方式（venv dev_sidecar / 冻结尾像 app.exe + --data-root），不要新造第二套脚本；
- 对冻结尾像跑与 venv 同一组关键用例：health 200、无 token 401、import 结构性数据集 200、幂等 existing:1、preview PNG、raw 覆盖、三种错误（FILE_NOT_FOUND / HEADER_INVALID / SIZE_MISMATCH）；
- 结论要求：两侧结果一致；不一致即缺陷，记账修复，不放过。

### P7 · 成品冒烟（科祥本机执行，单轮核心链；不起云电脑/VM）
2026-10-19 裁定：保核心、保速度。#01 安装/卸载/首跑/数据保留链路已由两台干净云电脑实测通过（见 #01 封账记录），本里程碑增量=datasets 路由进 release + 安装包体积变化，**本机单轮冒烟即可覆盖**，不再起云电脑/VM，干净机基线项记缓测。
核心链（科祥在自己电脑上执行，约 10 分钟）：
1. 安装前确认本机无旧版 SpectrumAgent 安装（有则先卸载，避免串味）；
2. 安装 setup.exe → 成功、目录红线（%LOCALAPPDATA%\Programs\SpectrumAgent）；
3. 首跑非白窗、引擎 Ready、版本显示 0.1.1；
4. **数据接入闭环**：选 `E:\高光谱数据集\plastic`（或子目录）→ 导入 11 项 → 单波段预览 → 重复选择幂等（新增 0）；
5. 关窗 → 外壳 exit 0、无进程残留（release 为 onedir 单进程形态，按实际验）；
6. 卸载 → 程序目录与卸载键删除、数据根保留（db/logs/run/testdata）；
7. 证据从简：关键步骤截图 + 目录/注册键 Test-Path 结果即可，不必跑全套采集脚本。

---

## 三、红线（违反任一条即打回）

1. **不得新增依赖**（Cargo/npm/Python lock 零变化；dialog/rfd 已在位）。如确需新增，先出版本提案走批准流程。
2. NAS 只读/写白名单语义不变；import 依旧**只登记引用、不复制/不移动/不改源文件**（有 mtime 实证口径）。
3. #01 冻结产物目录只读；新 revision 新目录。
4. tauri.conf.json 禁绝对路径；安装目录 ASCII、offlineInstaller、currentUser 不变。
5. release handler 集合的任何扩充都必须显式经科祥批准（本卡 D1 即为该批准点）；dev-only 模块不得泄漏进 release。
6. 测试数字必须带执行模式（默认并行优先）；缓测项记"缓测"不记"通过"。
7. 读不到的命令/文件不编造；所有构建命令以当次原始输出为准。

---

## 四、验收清单（过闸条件，负责人独立复核）

- [ ] P0 三项补丁落档；24.146ms 未被擅自采用。
- [ ] P1 引擎统一：release 冻结尾像含 datasets 路由（P6 实证）。
- [ ] P2 release 五命令注册 + capability 同步 + audit JSON 更新（diff 范围仅预期文件）。
- [ ] P3 新 manifest 生成、#01 revision 树零改动、resources 树哈希记录。
- [ ] P4 setup.exe 产出；命令逐字记录；SHA256/字节/体积增量记录。
- [ ] P5 全量测试默认参数全绿（141 / 22 / 2 / clippy / tsc / vite）。
- [ ] P6 venv vs onedir 关键用例结果一致。
- [ ] P7 本机核心冒烟链 7 步通过（安装前无旧版→安装→首跑 0.1.1→导入 11 项→预览→幂等→关窗无残留→卸载数据保留）；证据从简（截图+关键检查）。
- [ ] REPORT.md 如实；已知问题（握手残留、1412、exit70）延续记账未追认。
- [ ] 负责人独立复跑：git diff 范围审计 + setup.exe 哈希复算 + 关键测试抽跑。

## 五、缓测清单（记"缓测"不记"通过"）

签名/SmartScreen 详录；干净机/云电脑基线（WebView2 离线引导、全新 runtimes 环境）；timings.txt 精确值；exit code 70；长路径 >260；reboot 独立轮；记忆键值细节（已口径化为安装器标准行为）。本机冒烟发现任何异常即升级为必查项。

---

## 六、决策点裁定记录（2026-10-19 科祥批准）

- **D1 = A**：release 注册 `datasets_forward`。依据：ingestion UI 随包发布而 IPC 不注册 = 半成品，#02 无法交付；转发器约束已实现且实测（仅本机握手端口/路径白名单/GET-POST/8MiB/代次校验），风险低。本卡即为对 #02 期"release 四命令不动"临时红线的正式批准，范围仅此一项，不扩散。
- **D2 = 0.1.1**：标记打包 revision，与遗留"0.1.1 修复单"语义衔接；identifier 与安装注册键不变；避免两个不同内容的 0.1.0 安装包并存。

---

## 六、决策点（已批准，2026-10-19 23:24）

- **D1 · release 注册 datasets_forward**：**A 批准**——发布形态必须带数据接入，本卡即为正式批准点。
- **D2 · 版本号**：**0.1.1**——标记打包 revision，与遗留的"0.1.1 修复单"语义衔接；identifier/安装键不变。
