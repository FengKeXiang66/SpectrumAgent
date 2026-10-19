# Win11 干净 VM 建机与验收手册（阶段一验收 1/2/3/4 解锁）

**当前状态（负责人 2026-10-18 15:41 更新）：干净 Win11 装机完成，pristine 底座已就位；安装验收仍待 VM 实机。**

本轮实机已完成：
- Win11 专业版装成（经 WIM 直部部署，见第 3.5 步），OOBE 走 `oobe\bypassnro` → 本地账户 `test` → 桌面正常
- **当前 pristine 检查点**（`f7ea81cf-6c3a-4823-9a7b-5fe77f4c2300`，2026-10-18 15:41:03）；旧 `bb3d1cac` 已作废删除，不得恢复或引用为当前底座。
- Secure Boot 已开回 **On**（与客户机常见配置对齐）
- 来宾服务接口已启用；**Copy-VMFile 送文件验证通过**（探针 `artifacts\vm-probe.txt`，源 SHA256 `FBE533AF...9AED`，VM 内 `Get-FileHash` 回读一致；注意 VM 重启后需等来宾服务就绪约 30 秒再发，否则报 0x800710DF「设备未就绪」）。VM 内本地账户实际名 `fkx`（非 test，无碍）
- VM：Running，磁盘 15.88GB，8GB 内存

**仍未做（正式验收时才需要）**：restore pristine 的恢复验证、三段冷启动计时、断网安装验收 3/4。

两个脚本（管理员 PowerShell 跑）：
- `build-vm.ps1` —— 建 VM（Gen2 / 动态内存 4–10GB / 4 vCPU / 80GB VHDX 在 E 盘 / 开 TPM / 挂 ISO / 关自动检查点）
- `vm-ops.ps1` —— 日常操作：checkpoint / restore / send（送文件进 VM）/ status / deletecp

本次脚本修复：创建本地 Key Protector 后才 Enable-VMTPM；显式打开 Secure Boot；
建机与 send 路径均启用 Guest Service Interface；送文件使用 `-FileSource Host`，
而非不存在的 `-FileSourceHost` 参数。新 VM 显式添加 DVD 并设为首启动设备。
这些 API 的文档依据如下；负责人已启用 Hyper-V 并重启，现为 Enabled、vmms 运行、模块可用，不再使用旧“缺模块”探针作当前结论。建机/送文件已有负责人实测，restore 恢复验证仍待后续正式验收：
[Set-VMKeyProtector](https://learn.microsoft.com/en-us/powershell/module/hyper-v/set-vmkeyprotector)、
[Integration Services](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/manage/manage-hyper-v-integration-services)、
[Copy-VMFile](https://learn.microsoft.com/en-us/powershell/module/hyper-v/copy-vmfile)、
[Add-VMDvdDrive](https://learn.microsoft.com/en-us/powershell/module/hyper-v/add-vmdvddrive)、
[Set-VMFirmware](https://learn.microsoft.com/en-us/powershell/module/hyper-v/set-vmfirmware)。

---

## 第 1 步：启用 Hyper-V（管理员 PowerShell，跑完重启）

以下为历史建机说明。负责人已手动执行并重启，当前不需要再次执行：

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All -NoRestart
Restart-Computer
```

## 第 2 步：建 VM（重启后，管理员 PowerShell）

```powershell
cd E:\AI_Agent
Set-ExecutionPolicy -Scope Process Bypass -Force   # 仅当前窗口，允许跑脚本
.\build-vm.ps1
```

- 脚本默认读你的 ISO，VM 全落 `E:\HyperV\Win11Clean\`
- 网络交换机：优先 `Default Switch`（NAT，VM 能直接上网补驱动）；没有就自动建 `VMNet`（Internal，VM 不能上网但断网验收照样做）
- 脚本启动 VM 后，手动执行 `vmconnect.exe localhost Win11Clean` 进入装系统；脚本不自动弹窗。

## 第 3 步：装系统（VMConnect 窗口内）

1. 产品密钥界面 → **我没有产品密钥**
2. 版本选 **专业版**（与宿主机一致；multi-edition ISO 可选）
3. 自定义安装，磁盘直接下一步（默认未分配）
4. 按实际 ISO 的 OOBE 流程建测试账户（本地账户，如 `test`）：网络界面先试 **Shift+F10 → `oobe\bypassnro`** 回车，VM 重启后走“我没有 Internet”；若该 build 已封掉 bypassnro，改试 Shift+F10 → `start ms-cxh:localonly`。**具体走哪条路径要记录实际结果**——这正是本 build（26300）的未验证项。
5. 装完只做一件事：设置 → 系统 → 关于，确认 Win11 专业版。**先别装任何软件、先别开 Windows Update**

## 第 3.5 步（实际采用）：ISO 引导失败 → WIM 直部部署

**实测结论（2026-10-18）**：本 ISO 在 VM 固件下无法引导——Secure Boot 开/关都报 `SCSI DVD (0,1) The boot loader failed`，退网卡、退磁盘、无系统。
- ISO 本身可读：宿主持载成功；`dism /Get-WimInfo` 完整读出 6 个版本（专业版=索引 4）；`bootmgfw.efi` 与 `bootx64.efi` SHA256 一致（启动文件完好）。
- 但 ISO 带非官方痕迹（根目录 `__chunk_data`，内容是构建机目录清单 `F:\wd\out\zh-cn_CMI_CLIENTSKU\...`），判定为拼装 ISO，其 El Torito 引导目录固件不认。
- **决策：绕过 ISO 引导链**，用 `deploy-win11-vhdx.ps1` 把 `install.wim` 索引 4 直接 dism 部署到 VM 磁盘（dism 是系统安装的规范化路径）。

```powershell
# 管理员 PowerShell，约 5-10 分钟
.\deploy-win11-vhdx.ps1
```

脚本自动：停 VM → 挂载 ISO/VHDX → 建 GPT 分区（ESP/ MSR/ Windows）→ `dism /Apply-Image /Index:4` → `bcdboot /f UEFI` → 卸载 → 设磁盘为首启动 → 开机。之后 OOBE 流程与第 3 步相同（本地账户 test）。
**注意**：部署期间 Secure Boot 是 Off 的；OOBE 完成后按脚本末尾提示开回 On，再打 pristine 检查点（与客户机 SB=On 的常见配置对齐）。若你对拼装 ISO 的 WIM 来源不放心，可在正式验收前用官方 ISO 重做一次 pristine——脚本同样适用（改 `-IsoPath` 即可）。

## 第 4 步：打 pristine 检查点（这台 VM 的核心资产）

```powershell
.\vm-ops.ps1 -Action checkpoint -Name pristine
```

以后每轮验收：**restore pristine → 装/测一遍**，永远有干净底。升 v2 时装完 v1 再打 `v1` 检查点测回滚。

## 第 5 步：给 VM 送 setup.exe + 断网测试

```powershell
# 宿主机执行
.\vm-ops.ps1 -Action send -SourcePath "E:\AI_Agent\artifacts\step4\setup.exe"
```

断网（验收 3）不用动交换机：VM 内右下角网络图标 → 右键 → 网络和 Internet 设置 → 高级网络设置 → **禁用适配器**，效果等同拔网线；测完再启用。

## 验收对照表（VM 就位后才解锁的项）

| 验收条目 | 在 VM 里怎么做 |
|---|---|
| 验收 1 三段计时 | restore pristine → 冷启动，秒表/任务管理器记三段：进程启动→`/health` 就绪；双击→窗口可操作；首次 `/smoke` 调用 |
| 验收 3 断网安装 | 禁网卡 → 桌面双击 setup.exe → 看 WebView2 是否随包离线装上 |
| 验收 2 无残留 | VM 内任务管理器：正常关窗 + 强杀外壳各看进程组 |
| 验收 4 断网 `/smoke` | 保持禁网卡启动应用走一遍冒烟 |
| 默认安装目录（待 VM 实机） | 恢复当前 pristine，首次安装时不传 `/D=`；从 NSIS 界面/日志及 HKCU 卸载项 InstallLocation 取证，必须为 `%LOCALAPPDATA%\Programs\SpectrumAgent`，不得与数据根重叠。 |
| 卸载保留用户数据（待 VM 实机） | 卸载前记录 `%LOCALAPPDATA%\SpectrumAgent` 下 run/logs/testdata 的文件名、大小与 SHA256，并放置本轮测试标记；卸载后确认 Programs 下程序目录已移除、数据根与这些内容逐项完好。程序运行阶段自身的握手生命周期不混入卸载比较。 |

安装配置固定 currentUser（无需管理员）、WebView2 offlineInstaller；仅 NSIS 模板 currentUser 默认目录一行变更，保留 `/D=` 优先守卫、不改卸载逻辑、不用 installerHooks。模板来源与单行字节差异见 `artifacts/step3/checkpoint-4/release-custom-protocol-20261018/`。这两项未实测前，安装/卸载验收保持“待 VM 实机”，不得用宿主机测试替代。

本次已打包微软离线安装器外层版本1.3.287.9，已签名载荷XML中WebView2 Runtime版本155.0.4283.62；依据见该批次WEBVIEW2-RUNTIME.md。VM安装前后读EdgeUpdate Clients中appid `{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}` 的pv并核对。若底座预存Runtime、NSIS跳过安装，不冒称已验证首次缺Runtime的离线安装。

## 空间与卫生纪律

- **80GB VHDX + ISO 8.5GB 全在 E 盘；C 盘 15.4GB 不动**
- 检查点是差异磁盘会膨胀：每轮验收完 `.\vm-ops.ps1 -Action deletecp -Name <本轮临时名>`，平时只留 `pristine`
- C 盘还需盯 rustup/cargo/npm/uv 缓存和 Tauri target 的增长
- 预期耗时：启用+重启 ~10 分钟；建机+装系统 ~25 分钟

## 建机完成后

原始输出追加保存到 `artifacts/step2/revision-01/vm/`，每轮用新时间戳文件名，禁止覆盖失败记录：

1. 管理员终端用 Start-Transcript 记录 `build-vm.ps1` 与 `vm-ops.ps1 -Action status`，保存创建与 Running 状态、TPM=True、SecureBoot=On 和 Guest Service Interface=True。
2. 装完干净 Win11 后送入一个无敏感内容的文本探针：`vm-ops.ps1 -Action send -SourcePath <探针文件>`；记录 Copy-VMFile 输出及来宾端读回内容和 SHA256，证明实际复制成功。
3. 执行 `vm-ops.ps1 -Action checkpoint -Name pristine`，记录 Get-VMCheckpoint 的名称、Id 与 CreationTime。
4. 在来宾创建一个检查点后标记，再执行 `vm-ops.ps1 -Action restore -Name pristine`；记录同一检查点被恢复、VM 再次 Running、来宾标记消失及干净系统状态。

以上四项均有原始输出后，另一次提交才能把本文状态改为“实机验证通过”，并逐项引用实际证据文件。
目前没有上述证据，不允许改状态。之后第 4/5 步继续使用该 pristine 底座进行安装和冷启动验收。
