# 第 2 步关账准备记录（2026-10-18）

## 完成到哪一步

关账前置项 1、3、4、5、7 已完成并提交；第 6 项脚本已修复并首次提交为“待实机验证”，实机验证尚未执行。第 8 项关账条件不满足，STATUS.md / REPORT.md 未更新为关闭，第 3 步尚未开始。

| 前置项 | 结果与提交 |
|---|---|
| HEAD pytest 与旧输出说明 | `73421c8`；HEAD d218262 新跑 27 passed，四份旧输出与 d218262 Git blob 逐字节相同 |
| TASK-01 契约修订 | `2abb004`；原有修订单独提交，外壳只读、引擎独占生命周期、资源用 resolve |
| 七份历史人工探针 | `4b7d3be`；五份 tracked 原件 git mv、删除等哈希根副本，两份未跟踪原件移动后 add；SHA256/来源与危险操作警示已存档 |
| VM 三件 | `879064e`；Key Protector、Guest Service Interface、Copy-VMFile 参数及 DVD 引导修复；语法可解析，实机未验证 |
| 清单生成器 | `f44e683`；先提交后生成，核验来源、旧证据数值及残留，拒绝覆盖既有清单 |
| 全量产物清单 | `bc50c3e`；544 文件、255,564,460 字节，路径/长度/SHA256 全量独立核验 |

`verify_frozen_sources.py` 仍在原位置且未修改。backend、requirements-lock.txt、build.spec 相对 d218262 无差异；未修改冻结产物。没有执行安装类命令。

## 命令与原始输出

正式 HEAD 测试命令与 REPORT 记录一致，先创建 --basetemp 父目录；输出新存 pytest-head-output.txt，未覆盖旧文件：

```powershell
& 'E:\AI_Agent\.venv\Scripts\python.exe' -m pytest backend/tests -q -p no:cacheprovider --basetemp E:\AI_Agent\artifacts\step2\revision-01\pytest-tmp-transaction
```

完整原始输出：[pytest-head-output.txt](pytest-head-output.txt)；测试 HEAD、命令及旧输出哈希：[pytest-head-receipt.json](pytest-head-receipt.json)。结果原文：

```text
27 passed, 10 warnings in 1.85s
```

VM 只读命令（未执行安装、重启、建机）：

```powershell
Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V
Get-CimInstance Win32_ComputerSystem
Get-Command Get-VM,Set-VMKeyProtector,Enable-VMIntegrationService
Get-Service vmms
Get-Module -ListAvailable Hyper-V
Get-Item -LiteralPath 'E:\ISO\Windows11_Client_x64_zh-cn_26300_9457.iso'
```

完整命令与原始输出：[vm/host-probe-output.txt](vm/host-probe-output.txt)。其中原始字段和错误文本如下：

```text
FeatureName : Microsoft-Hyper-V
State       : Disabled

HypervisorPresent   : True
TotalPhysicalMemory : 16962281472

The term 'Get-VM' is not recognized as a name of a cmdlet, function, script file, or executable program.
The term 'Set-VMKeyProtector' is not recognized as a name of a cmdlet, function, script file, or executable program.
The term 'Enable-VMIntegrationService' is not recognized as a name of a cmdlet, function, script file, or executable program.
Cannot find any service with service name 'vmms'.

FullName : E:\ISO\Windows11_Client_x64_zh-cn_26300_9457.iso
Length   : 9112440832

Script      : build-vm.ps1
ParseErrors : 0
Script      : vm-ops.ps1
ParseErrors : 0

VM_REAL_MACHINE_VERIFICATION: NOT RUN (Hyper-V Disabled; module and vmms unavailable)
```

产物清单生成命令：

```powershell
& 'E:\AI_Agent\artifacts\step2\generate_product_manifest.ps1'
```

生成与独立核验完整原始输出：[product-manifest-output.txt](product-manifest-output.txt)。清单顶层来源区分：

```json
{
  "artifact_source_commit": "d218262",
  "manifest_generator_commit": "f44e68320b00cfaddcb40be377df339129204daa",
  "artifact_root": "artifacts/step2/dist/app"
}
```

该段是固定字段的摘录，完整六字段与全部文件条目在 [product-manifest.json](../product-manifest.json)。文件 SHA256：`f2249ed595ae3a584ddc17d150024fa2e77d34159ee50bb01faed779217b17e7`。

独立核验原始 JSON：

```json
{"event": "independent_manifest_verification", "files_verified": 544, "bytes_verified": 255564460, "path_size_sha256_mismatches": 0, "empty_directories": [], "old_pytest_outputs_unchanged_from_d218262": 4, "backend_lock_spec_diff_from_d218262": false}
```

首次宽松名称探针把 `default.rsc` 中的 fault 子串误列为可疑；该文件与 venv 中 rasterio/gdal_data/default.rsc 的只读 SHA256 均为 `9e1c9d7081d52775e750d4155d49255252b04ca81fef27cb2997675d3cd9626b`。正式检查按文件名边界识别实验标记，未把包内正常数据文件认作故障夹具。未删除任何产物文件；最终实验残留 0、空目录 0。

## 遇到的问题

宿主机 Hyper-V 功能 Disabled，模块命令与 vmms 服务不可用，因此不能进行 VM 创建/启动、TPM/Secure Boot 状态、Copy-VMFile、pristine 创建和恢复的实机验收。现象及错误原文已落盘；已做只读探针、API 官方文档核对和脚本语法解析，未把这些替代实机验收。

依据用户“安装类命令执行前先列清单，等我确认”的纪律，尚未启用系统功能。待确认的命令清单：

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All -NoRestart
```

该命令只启用功能，不自动重启。若系统要求重启，另行确认后执行 `Restart-Computer`。VM 脚本的 Hyper-V API 调用在本机仍未验证；当前“待实机验证”状态禁止第 2 步关闭。

## 下一步打算

获安装确认后启用 Hyper-V，安排重启，再完成 VM 实机证据；全部满足后才作两份状态文档的最终关账提交并复核 Git 干净，再按顺序进入第 3 步。
