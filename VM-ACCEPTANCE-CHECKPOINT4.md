# 检查点 4 · VM 实机验收操作单

> 对象：`artifacts/step4/setup.exe`（287,156,790 B，SHA256 `d8492536…`）
> 底座：pristine 检查点 `f7ea81cf-6c3a-4823-9a7b-5fe77f4c2300`（VM 名 `Win11`）
> 分工：**宿主机命令可交 codex；VM 内操作必须负责人亲手做、亲手签字。**

---

## 0. 为什么必须这么绕（一句话）

`Copy-VMFile` 是单向的（host→guest），微软没有反向接口，pristine 里也没有 WinRM/共享目录。
**证据只能靠「VM 关机 → 宿主机只读挂载 VHDX → 拷出来」**。这一步由 `fetch-vm-evidence.ps1` 完成。

---

## 1. 宿主机准备（管理员 PowerShell）

```powershell
cd E:\AI_Agent

# 1.1 回干净底座（会丢弃当前 VM 里的一切，包括 33 GB 差异盘）
.\vm-ops.ps1 -Action restore -Name pristine

# 1.2 等桌面出现后，立刻打临时检查点（测崩了不用重送文件）
.\vm-ops.ps1 -Action checkpoint -Name accept-4-20261019

# 1.3 送两个文件进 VM 的公共桌面
.\vm-ops.ps1 -Action send -SourcePath "E:\AI_Agent\artifacts\step4\setup.exe"
.\vm-ops.ps1 -Action send -SourcePath "E:\AI_Agent\collect-vm-evidence.ps1"
```

> 送完等约 30 秒让来宾服务就绪；`send` 会打印源 SHA256，记下来。
> 进 VM：`vmconnect.exe localhost Win11`（**VM 名是 `Win11`**）。

---

## 2. VM 内五轮采样（关键：每次都是新目录，不覆盖）

进 VM 后先**禁用网卡**（验收 3/4 要求断网）：
设置 → 网络和 Internet → 高级网络设置 → 禁用适配器。

脚本调用统一格式（**不需要装任何东西**）：

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\Public\Desktop\collect-vm-evidence.ps1" -Phase <阶段>
```

| # | 阶段 | 什么时候跑 | 采集重点 |
|---|---|---|---|
| 1 | `install` | 装完、**还没启动过** | 卸载键是否存在、安装目录布局、WebView2 pv、记忆键是否**不存在** |
| 2 | `firstrun` | 启动应用 → 正常关窗之后 | 握手文件是否残留、进程是否清干净、日志 |
| 3 | `reboot` | VM 重启后 | 卸载键是否仍在、重启是否影响 |
| 4 | `manual` | **卸载之前**（跑完在纸上标注 `pre-uninstall`） | 数据根逐文件 SHA256（这是"卸载保留数据"的基准） |
| 5 | `uninstall` | 卸载完成之后 | 程序目录是否移除、数据根是否逐项完好 |

第 4 轮单独说明：脚本只认 `manual` 这个值，输出目录形如 `manual-20261019T…Z`；
**在纸上标注它是 `pre-uninstall` 基准快照**，第 5 轮比对时以它为准。

---

## 3. 每一步人眼要记的东西（脚本不判，你判）

### 3.1 安装（验收 3：断网离线安装）
- [ ] 双击 `setup.exe`，NSIS 界面能起来（断网状态下）
- [ ] 安装目录显示为 `%LOCALAPPDATA%\Programs\SpectrumAgent`（不是 `C:\Program Files\…`）
- [ ] 全程无联网报错；WebView2 随包离线装上
- [ ] 记下界面上的实际路径文字（截图或抄下来）

### 3.2 首次运行（验收 1 三段计时 + 验收 4 断网 smoke）
三段分别记：
- [ ] **双击 → 窗口可操作**：手机秒表，人眼判
- [ ] **进程启动 → `/health` 就绪**：从数据根日志取时间戳（脚本已采 logs）
- [ ] **首次 `/smoke` 调用**：点界面按钮，记耗时
- [ ] 断网状态下 smoke 能走完（验收 4）
- [ ] 正常关窗后，任务管理器里没有残留的 `SpectrumAgent.exe` / `app.exe` / `msedgewebview2.exe`（验收 2）

### 3.3 握手残留（本轮预期复现，不是新缺陷）
- [ ] 正常关窗后 `run\handshake.json` **仍然存在** → 这是已知问题，本轮记录，不判失败
- [ ] 下次启动后：旧文件被删除，日志里出现 `stale_handshake_removed`
- [ ] 无孤儿进程、端口无占用

### 3.4 卸载（验收 2 的卸载面）
- [ ] 应用列表（设置 → 应用）里能看到 SpectrumAgent（三时点都要看）
- [ ] 卸载勾选"删除应用数据"
- [ ] 卸载后：`%LOCALAPPDATA%\Programs\SpectrumAgent` 已移除
- [ ] 卸载后：数据根 `%LOCALAPPDATA%\SpectrumAgent` 逐项完好（对比第 4 轮基准快照）
- [ ] 卸载后：`HKCU\Software\spectrumagent` **仍存在属正常**（harness 写的，不是安装器）
- [ ] 卸载后：`HKCU\…\Uninstall\SpectrumAgent` 应消失

---

## 4. 取证据（宿主机，管理员）

**先正常关机**（VM 内 `Stop-Computer`，**不要 `-Force`**，要刷盘），然后：

```powershell
cd E:\AI_Agent
.\fetch-vm-evidence.ps1
```

它会：
1. 拒绝在 VM 非 Off 状态下运行
2. 只读挂载当前磁盘（有检查点时是 `.avhdx`）
3. 找到 `\vm-evidence`，整目录拷到 `run-<UTC>\guest\`
4. 生成 `manifest.json`（每个文件的 SHA256）
5. 卸载，打印 `FETCH_DIR=…`

**顺序硬约束**：先取证据，**再**删检查点。`deletecp` 要合并差异盘，合并期间挂载会失败。

---

## 5. 收尾

```powershell
cd E:\AI_Agent
.\vm-ops.ps1 -Action deletecp -Name accept-4-20261019
.\vm-ops.ps1 -Action status
```

只留 `pristine`，磁盘别涨。

---

## 6. 判读表（填完由负责人签字）

| 条目 | 期望 | 实测 | 证据文件 |
|---|---|---|---|
| 默认安装目录 | `%LOCALAPPDATA%\Programs\SpectrumAgent` | | `install-layout.json` |
| 断网离线装 WebView2 | pv 与 155.0.4283.62 一致或更新 | | `webview2.json` |
| 卸载键 · 装完未启动 | 存在 | | `registry-uninstall.json` |
| 卸载键 · 首运行关窗后 | 存在 | | `registry-uninstall.json` |
| 卸载键 · 重启后 | 存在 | | `registry-uninstall.json` |
| 记忆键 · 纯安装后 | **不存在** | | `registry-memory-key.json` |
| 握手残留 · 关窗后 | **预期存在**（已知问题） | | `handshake.json` |
| 握手自愈 · 下次启动 | 删除 + `stale_handshake_removed` | | `data-root.json` + 日志 |
| 三段计时 | 三段分别记录 | | 人工 + 日志 |
| 进程无残留 | 关窗后无 SpectrumAgent/app/webview2 | | `processes.json` |
| 卸载 · 程序目录 | 已移除 | | `install-layout.json` |
| 卸载 · 数据根 | 逐项完好（对比 pre-uninstall） | | `data-root.json` ×2 |
| LongPaths | 记录原值 | | `longpaths.json` |
| 断网 smoke | 走完、无联网依赖 | | 人工 |

签字：____________　日期：____________

---

## 7. 已知问题（本轮不阻塞，0.1.1 修）

| 问题 | 影响 | 处置 |
|---|---|---|
| 优雅关闭不删 `handshake.json` | 功能零影响（下次启动自愈） | 0.1.1 外壳侧清理；本轮 VM 预期复现并记录 |
| `exit code 70` 未验证 | 未知 | 继续观测，本轮不判 |
