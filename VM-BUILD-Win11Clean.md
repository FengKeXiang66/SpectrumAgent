# Win11 干净 VM 建机与验收手册（阶段一验收 1/2/3/4 解锁）

**状态：待实机验证。第 2 步不得关闭，第 3 步不得开始。**

2026-10-18 关账只读探针见 `artifacts/step2/revision-01/vm/host-probe-output.txt`：
Hyper-V 功能 `Disabled`；HypervisorPresent=True；Hyper-V 模块命令和 vmms 服务不存在。
ISO 文件长度为 9,112,440,832 字节。HypervisorPresent 不等于 Hyper-V 管理功能已安装。
尚未创建/启动 VM，TPM、Secure Boot、Copy-VMFile、pristine 创建/恢复全部**未验证**。
PowerShell 语法解析结果只证明脚本可解析，不能替代这些实机结果。

原状态快照（2026-10-18 09:19，容量信息未在本轮重测）：
- ISO 已就位：`E:\ISO\Windows11_Client_x64_zh-cn_26300_9457.iso`（8.49 GB ✅）
- E 盘空闲 893.3 GB（足够）；**C 盘仅剩 15.4 GB，凡 VM 产物一律落 E 盘**
- Hyper-V 功能当前 **Disabled**，需管理员启用 + 重启
- 当时记录 `HypervisorPresent=True`；不能据此宣称建机或来宾功能已经验证。

两个脚本（管理员 PowerShell 跑）：
- `build-vm.ps1` —— 建 VM（Gen2 / 动态内存 4–10GB / 4 vCPU / 80GB VHDX 在 E 盘 / 开 TPM / 挂 ISO / 关自动检查点）
- `vm-ops.ps1` —— 日常操作：checkpoint / restore / send（送文件进 VM）/ status / deletecp

本次脚本修复：创建本地 Key Protector 后才 Enable-VMTPM；显式打开 Secure Boot；
建机与 send 路径均启用 Guest Service Interface；送文件使用 `-FileSource Host`，
而非不存在的 `-FileSourceHost` 参数。新 VM 显式添加 DVD 并设为首启动设备。
这些 API 已核对微软文档，宿主机缺模块，**本机实际调用仍未验证**：
[Set-VMKeyProtector](https://learn.microsoft.com/en-us/powershell/module/hyper-v/set-vmkeyprotector)、
[Integration Services](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/manage/manage-hyper-v-integration-services)、
[Copy-VMFile](https://learn.microsoft.com/en-us/powershell/module/hyper-v/copy-vmfile)、
[Add-VMDvdDrive](https://learn.microsoft.com/en-us/powershell/module/hyper-v/add-vmdvddrive)、
[Set-VMFirmware](https://learn.microsoft.com/en-us/powershell/module/hyper-v/set-vmfirmware)。

---

## 第 1 步：启用 Hyper-V（管理员 PowerShell，跑完重启）

以下是待确认的系统功能安装与重启命令；本轮尚未执行。按项目纪律先获负责人确认。

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
4. 按实际 ISO 的 OOBE 流程建测试账户；此 ISO 下离线账户入口、`oobe\bypassnro` 可用性**未验证**，不可保证旧版绕过命令有效。
5. 装完只做一件事：设置 → 系统 → 关于，确认 Win11 专业版。**先别装任何软件、先别开 Windows Update**

## 第 4 步：打 pristine 检查点（这台 VM 的核心资产）

```powershell
.\vm-ops.ps1 -Action checkpoint -Name pristine
```

以后每轮验收：**restore pristine → 装/测一遍**，永远有干净底。升 v2 时装完 v1 再打 `v1` 检查点测回滚。

## 第 5 步：给 VM 送 setup.exe + 断网测试

```powershell
# 宿主机执行
.\vm-ops.ps1 -Action send -SourcePath "E:\AI_Agent\dist\setup.exe"
```

断网（验收 3）不用动交换机：VM 内右下角网络图标 → 右键 → 网络和 Internet 设置 → 高级网络设置 → **禁用适配器**，效果等同拔网线；测完再启用。

## 验收对照表（VM 就位后才解锁的项）

| 验收条目 | 在 VM 里怎么做 |
|---|---|
| 验收 1 三段计时 | restore pristine → 冷启动，秒表/任务管理器记三段：进程启动→`/health` 就绪；双击→窗口可操作；首次 `/smoke` 调用 |
| 验收 3 断网安装 | 禁网卡 → 桌面双击 setup.exe → 看 WebView2 是否随包离线装上 |
| 验收 2 无残留 | VM 内任务管理器：正常关窗 + 强杀外壳各看进程组 |
| 验收 4 断网 `/smoke` | 保持禁网卡启动应用走一遍冒烟 |

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
