# 历史证据索引（2026-10-18 关账准备）

本目录下方保留的旧版说明属于历史记录，不是当前验收入口。正式回归入口只有受版本控制的
`artifacts/step2/lifecycle_regression.py` 与 `artifacts/step2/selfcheck_step2.ps1`。

`revision-01/` 中四份既有 pytest 原始输出均保持原字节，不回改测试数量：

| 本机时间 | 文件 | 原始结果 | 定位 |
|---|---|---|---|
| 08:42 | `pytest-output.txt` | 25 passed | 开发期中间态 |
| 08:50 | `pytest-final-output.txt` | 26 passed | 开发期中间态 |
| 08:53 | `pytest-release-output.txt` | 26 passed | 开发期中间态 |
| 08:59 | `pytest-transaction-output.txt` | 27 passed | 提交前最后一次全量 |

前三份圆点数和用例数递增源于开发期逐加用例；文件名中的 final/release 不表示最终依据。
最终依据是从 HEAD `d218262` 使用 REPORT 原命令新跑的 `revision-01/pytest-head-output.txt`：
`27 passed, 10 warnings in 1.85s`。命令、HEAD 与四份旧输出的 SHA256 见
`revision-01/pytest-head-receipt.json`；原始输出一份未改。

以下旧版说明原文作为历史保留，其中 Ctrl+C、握手清理和旧验收通过的口径已被当前
`artifacts/step2/REPORT.md` 与 `STATUS.md` 撤回或澄清，不得用它代替当前规范。

---

# 第 2 步：PyInstaller onedir（旧版原文）

正式源文件：本目录 `build.spec`、`selfcheck_step2.ps1`、`NativeConsole.cs`，
以及代码根 `backend/diagnostics.py` 和 `backend/__main__.py`。
这些源文件与选定的文本验收证据允许进入 Git；构建缓存、EXE、DLL、临时 GeoTIFF 不入库。

## 构建与复跑

仅使用项目已冻结的 53 包和指定解释器，不安装依赖：

```powershell
& 'E:\AI_Agent\.venv\Scripts\python.exe' -m PyInstaller --noconfirm 'E:\AI_Agent\artifacts\step2\build.spec'
& 'E:\AI_Agent\artifacts\step2\selfcheck_step2.ps1'
```

自检脚本使用本机已验证的 PowerShell 7（本轮为 7.6.5）/ .NET API，
仅作为开发验收工具；运行 `app.exe` 不依赖 PowerShell 或外部 Python。
所有进程由原生 CreateProcessW 直接启动，自己的控制台隐藏，工作目录为本证据目录，
子进程 PATH 限定到 Windows/System32 与 Windows，未借用源码目录或 venv。
Ctrl+C 通过短生命周期的 PowerShell 辅助进程发送给引擎自己的控制台。
`NativeConsole.cs` 不包含 Job Object；未实现外壳。

spec 锁定产物位置：`artifacts/step2/dist/app/app.exe` + `_internal/`。
移动/分发必须复制整个 `app/` 目录。数据与日志仍在 `%LOCALAPPDATA%/SpectrumAgent/`。
直接运行命令：

```powershell
& 'E:\AI_Agent\artifacts\step2\dist\app\app.exe'
```

`collect_submodules('rasterio')` 处理 Cython 层的动态导入；
`collect_data_files('rasterio')` 处理 proj.db、gdalvrt.xsd 等数据。
另外收集 uvicorn 的动态加载模块。不手动复制 rasterio DLL，也不调用额外的 DLL 收集。
本机产物中二进制分析自动生成 `rasterio.libs/`，实测 36 个 DLL 和 15 个 rasterio pyd。
不设置 GDAL_DATA、PROJ_DATA 或 PROJ_LIB；自检遇到已有变量会明确失败，不会悄悄清除。
本轮结论仅覆盖实测 wheel/锁文件/Windows 环境，不推广到其他版本的 rasterio。

## 诊断与生命周期

```powershell
& 'E:\AI_Agent\artifacts\step2\dist\app\app.exe' --selfcheck-geotiff
& 'E:\AI_Agent\artifacts\step2\dist\app\app.exe' --selfcheck-worker
```

GeoTIFF 模式在 LocalAppData 的 testdata 下每次新造样本、按指定 profile 写入并读回，
断言 CRS / 宽高 / 波段数 / transform / 数据值，然后清除样本。没有数据接入模块。
worker 模式只起一个短暂 spawn 子进程，不建任务池。入口先执行 freeze_support()，
子进程只回报自己的 PID/父 PID 并退出，断言握手未被改写。

8a 在实际 Ctrl+C 后、任何测试卫生清理前检查 PID、监听端口和握手均不存在。
8b 使用 taskkill /F，确认 PID/端口消失、握手残留，保存完整字段（只遮盖 token）到
`handshake-after-kill.json`；随后绝不删除旧握手，直接重启并验证 boot_id、端口改变，
health 200 且身份一致。最后再次正常退出。
第一轮启动前允许归档并移除已死 PID 的历史握手，仅作测试卫生；
这不能替代 8a 或 8b。失败收尾也会精确清理本次测试进程，报告会明确标注。

## 证据与限制

`selfcheck-output.txt` 是完整命令与原始输出；`selfcheck-results.json` 是机器可读状态。
`selfcheck-attempt1-*` 保留首次 8a 未通过的原始记录；未删改该失败。
首次正常退出后曾观察到测试前历史 boot_id 的握手重新出现，其来源未定位，
不能声称已修复引擎缺陷；脚本现于首次启动前归档清理死 PID 历史握手，
随后 8a 与 8b 均在判定前无清理情况下通过。未改握手契约或新增清理进程。

`startup-measurements.json` 区分正式产物首次启动 1712.879 ms 与复跑 690.567 ms。
它们是进程启动到身份匹配的 /health 200 的实测，包含轮询开销。
没有清空 OS 文件缓存或重启电脑，没有在无 Python 的干净 Windows 机器上复跑；
不能把复跑值当干净机器冷启动，也不以此声明安装包启动验收通过。
新建干净 venv 并安装锁依赖的构建尚未执行（本轮不执行安装）。

缺失 python312.dll 时 PyInstaller 原生报错包含缺失 DLL 的完整路径，退出码 -1，
无 Python traceback；系统辅助行在本机原始输出中为问号，完整保留在 missing-dll-output.txt。
DLL 在 finally 中恢复，恢复后的 SHA256 与原值一致。

原始数据解释与逐项报告见 REPORT.md。尚未开始第 3/4 步。
