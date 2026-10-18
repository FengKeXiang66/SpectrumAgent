# 第 2 步验收报告

## 完成到哪一步

正式 PyInstaller onedir 构建完成。产物为 `dist/app/app.exe` + `_internal/`。
当前完整自检的 1–7、8a、8b 及单 worker 均通过；未开始第 3/4 步。

源码与工具：build.spec、selfcheck_step2.ps1、NativeConsole.cs；
引擎仅新增两个打包诊断命令行模式，HTTP 契约未改。

## 命令与原始输出

正式构建命令（产物路径由 spec 内锁定）：

```powershell
& 'E:\AI_Agent\.venv\Scripts\python.exe' -m PyInstaller --noconfirm 'E:\AI_Agent\artifacts\step2\build.spec'
```

构建输出完整保存在 build-output.log，后文附末 18 行。
完整自检命令：

```powershell
& 'E:\AI_Agent\artifacts\step2\selfcheck_step2.ps1'
```

八项检查和附加单 worker 的实际命令、响应体、进程/日志/握手/缺 DLL 输出见下方原始 transcript。
8a 在破坏 DLL 前执行，以先释放所有 DLL 文件锁；八项编号保持不变。

## 数据的含义

- 写正式 spec 前，真实 backend 临时 onedir 已测得单进程：spawn/handshake/health
  PID 均为 23072，ParentProcessId=5320。正式产物复跑亦是单进程，PID=23768，
  ParentProcessId=8512。因此本轮没有引入 bootloader_pid 字段，也未改 health 字段。
- GeoTIFF 全部在冻结 app.exe 中写入/读回：EPSG:32650、12×10、3 波段、
  transform [30,0,500000,0,-30,4000000]，数据值一致，临时文件已删除。
  GDAL_DATA / PROJ_DATA / PROJ_LIB 均为 null；proj.db、gdalvrt.xsd 和模块路径来自 _internal。
  PATH 仅保留 Windows 目录，运行不借用 venv；无 Python 的干净 Windows 机器仍未实测。
- _internal 总字节数 238793334（543 文件），app.exe 为 16763405 字节；
  rasterio.libs 中 36 个 DLL、rasterio 下 15 个 pyd，由二进制分析自动收集，没有手工重复收集。
- 首次正式产物进程启动至身份匹配 health 200 为 1712.879 ms（保存在首次失败轮记录中）；
  完整通过的复跑为 690.567 ms，强杀测试启动为 577.676 ms，残留握手重启为 612.545 ms。
  未清 OS 文件缓存、未重启、未在干净机器上测量；不以复跑值冒充干净机器冷启动。
- Ctrl+C 的 Windows 进程退出码本轮为 1；日志包含 engine_stopped，PID、端口、握手均已消失。
  此项按约定检查正常清理效果，不把退出码改写成 0。
- 强杀后 PID/端口消失，握手确实残留（handshake-after-kill.json，仅 token 遮盖）；
  不清洗直接重启，boot_id 872bbaac → 3a1b84b8、port 59655 → 59664，health 200。
  结束时再次 Ctrl+C，握手自行删除，未靠脚本收尾清理取得通过。
- worker 是一次性的 spawn 诊断，不是任务池；worker_exitcode=0，frozen=true，握手未改写。

## 遇到的问题

1. 首次完整自检 8a 未通过：正常退出后路径中出现测试前历史 boot_id=0cee22a2 的握手，
   文件修改时间也为历史时间。来源未定位，不声称修复了引擎缺陷。
   该失败完整保留于 selfcheck-attempt1-output.txt / selfcheck-attempt1-results.json。
   脚本现只在第一轮启动前归档并清除已死 PID 的历史握手，明确标为测试卫生；
   复跑的 8a 和 8b 判定前没有清理。8b 从本轮产生的残留握手直接重启通过。
2. 缺失 python312.dll 时原生首行清楚给出缺失 DLL 和完整路径，退出码 -1，没有 Python traceback；
   LoadLibrary 的本地化辅助文本在原始输出里是问号。未重写原文，DLL 已恢复且 SHA256 一致。
3. 现有 Starlette / spectral 的弃用警告仍在（4 passed, 10 warnings），没有新增依赖。
4. 干净 Windows（未安装 Python）及清空系统缓存后的冷启动、干净 venv 重建尚未验证。
   本轮未执行任何安装命令。

## 下一步打算

停在第 2 步检查点，等待负责人验收；不开展 Tauri/React/NSIS/Job Object。

---

## 正式自检完整原始输出

```text
**********************
PowerShell transcript start
Start time: 20261018075433
Username: WIN-RTKE72PB5BE\Administrator
RunAs User: WIN-RTKE72PB5BE\Administrator
Configuration Name: 
Machine: WIN-RTKE72PB5BE (Microsoft Windows NT 10.0.26100.0)
Host Application: C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.dll -Command try { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}
& 'E:\AI_Agent\artifacts\step2\selfcheck_step2.ps1'
Process ID: 8512
PSVersion: 7.6.5
PSEdition: Core
GitCommitId: 7.6.5
OS: Microsoft Windows 10.0.26100
Platform: Win32NT
PSCompatibleVersions: 1.0, 2.0, 3.0, 4.0, 5.0, 5.1, 6.0, 7.0
PSRemotingProtocolVersion: 2.4
SerializationVersion: 1.1.0.1
WSManStackVersion: 3.0
**********************
GDAL_DATA=
PROJ_DATA=
PROJ_LIB=
PREFLIGHT TEST HYGIENE ONLY: archive and remove a pre-existing dead-process handshake before the first launch.
{
  "boot_id": "0cee22a2",
  "pid": 17588,
  "process_created_at": "2026-10-17T23:33:04.606Z",
  "port": 64385,
  "token": "<redacted>",
  "protocol": 1,
  "version": "0.1.0",
  "started_at": "2026-10-17T23:33:05.770Z"
}
child_PATH=C:\Windows\System32;C:\Windows
=== 1. Direct frozen engine launch / process identity ===
> CreateProcessW("E:\AI_Agent\artifacts\step2\dist\app\app.exe") [CREATE_NEW_CONSOLE, SW_HIDE; no Python/command shell]
spawn_pid=23768 handshake_pid=23768 health_pid=23768
first_launch_process_start_to_health_200_ms=690.567
> tasklist.exe /FI "IMAGENAME eq app.exe"

> Get-CimInstance Win32_Process -Filter "Name = 'app.exe'"

ProcessId       : 23768
ParentProcessId : 8512
ExecutablePath  : E:\AI_Agent\artifacts\step2\dist\app\app.exe
CommandLine     : "E:\AI_Agent\artifacts\step2\dist\app\app.exe"
app_process_count=1
=== 2. Four real curl requests ===
> curl.exe --noproxy "*" http://127.0.0.1:50289/health
HTTP 200
{"status":"ok","boot_id":"1d6ca94e","pid":23768,"version":"0.1.0","uptime_s":0.531}
> curl.exe --noproxy "*" http://127.0.0.1:50289/smoke
HTTP 401
{"error":"UNAUTHORIZED","detail":"需要本次引擎握手中的 Bearer token。"}
> curl.exe --noproxy "*" -H "Authorization: Bearer $($identity.token)" http://127.0.0.1:50289/smoke
HTTP 200
{"nan_ratio":0.0,"reflectance_range":[-1.5275289241381491,1.5275289241381491],"bands":8,"shape":[8,8,8],"elapsed_ms":136.459}
> curl.exe --noproxy "*" -H "Authorization: Bearer $($identity.token)" http://127.0.0.1:50289/smoke?blocks=8
HTTP 200
{"nan_ratio":0.0,"reflectance_range":[-1.5275289241381491,1.5275289241381491],"bands":8,"shape":[8,8,8],"elapsed_ms":197.514}
=== 3. Complete handshake (token redacted only) ===
{
  "boot_id": "1d6ca94e",
  "pid": 23768,
  "process_created_at": "2026-10-17T23:54:33.550Z",
  "port": 50289,
  "token": "<redacted>",
  "protocol": 1,
  "version": "0.1.0",
  "started_at": "2026-10-17T23:54:34.140Z"
}
=== 4. JSONL logs ===
valid_json_lines=71 current_boot_lines=15 token_occurrences=0
{"event": "Started server process [23768]", "pid": 23768, "boot_id": "1d6ca94e", "logger": "uvicorn.error", "level": "info", "timestamp": "2026-10-17T23:54:34.088647Z"}
{"event": "Waiting for application startup.", "pid": 23768, "boot_id": "1d6ca94e", "logger": "uvicorn.error", "level": "info", "timestamp": "2026-10-17T23:54:34.089655Z"}
{"event": "Application startup complete.", "pid": 23768, "boot_id": "1d6ca94e", "logger": "uvicorn.error", "level": "info", "timestamp": "2026-10-17T23:54:34.107873Z"}
=== 5. Frozen GeoTIFF generation / readback (no external interpreter) ===
> & "E:\AI_Agent\artifacts\step2\dist\app\app.exe" --selfcheck-geotiff
exit_code=0
{"check": "geotiff", "result": "PASS", "frozen": true, "executable": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\app.exe", "crs": "EPSG:32650", "shape": [10, 12], "width": 12, "height": 10, "count": 3, "transform": [30.0, 0.0, 500000.0, 0.0, -30.0, 4000000.0], "dtype": "float32", "pixel_values_equal": true, "GDAL_DATA": null, "PROJ_DATA": null, "PROJ_LIB": null, "proj_db": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\rasterio\\proj_data\\proj.db", "gdalvrt_xsd": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\rasterio\\gdal_data\\gdalvrt.xsd", "rasterio_module": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\rasterio\\__init__.py", "numpy_module": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\numpy\\__init__.py", "python_search_paths": ["E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\base_library.zip", "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\python3.12\\lib-dynload", "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal", "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\setuptools\\_vendor"], "sample": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\testdata\\geotiff-check-q2w3rk92\\generated.tif", "sample_removed": true}
=== Additional: freeze_support / one temporary spawn worker (no pool) ===
> & "E:\AI_Agent\artifacts\step2\dist\app\app.exe" --selfcheck-worker
exit_code=0
{"check": "multiprocessing", "result": "PASS", "diagnostic_pid": 14980, "worker_pid": 28592, "parent_pid": 14980, "frozen": true, "worker_exitcode": 0, "handshake_unchanged": true}
=== 7. Size / first-launch health latency ===
internal_files=543 internal_total_bytes=238793334 exe_bytes=16763405
rasterio_libs_dll_count=36 rasterio_pyd_count=15
first_launch_process_start_to_health_200_ms=690.567
Timing scope: first launch of this build in this selfcheck; no OS cache flush or clean-machine cold boot was performed.
=== 8a. Normal Ctrl+C shutdown ===
> GenerateConsoleCtrlEvent(CTRL_C_EVENT) to PID 23768 [separate helper attaches to engine console]
engine_exit_code=1
process_absent=True pid=23768 listener_absent=True port=50289
handshake_exists=False (checked before any test hygiene)
=== 6. Required DLL removal / native readable failure ===
> Removed E:\AI_Agent\artifacts\step2\dist\app\_internal\python312.dll (backup retained outside _internal)
exit_code=-1
[PYI-25244:ERROR] Failed to load Python DLL 'E:\AI_Agent\artifacts\step2\dist\app\_internal\python312.dll'.
LoadLibrary: ?????????
Required DLL restored; SHA256 matches original.
=== 8b. taskkill /F / stale-handshake overwrite without pre-clean ===
> CreateProcessW("E:\AI_Agent\artifacts\step2\dist\app\app.exe") [CREATE_NEW_CONSOLE, SW_HIDE; no Python/command shell]
spawn_pid=4280 handshake_pid=4280 health_pid=4280
kill_test_launch_process_start_to_health_200_ms=577.676
> taskkill.exe /F /PID 4280

process_absent=True pid=4280 listener_absent=True port=59655
> tasklist.exe /FI "PID eq 4280"

handshake_exists_after_taskkill=True; residue before any hygiene:
{
  "boot_id": "872bbaac",
  "pid": 4280,
  "process_created_at": "2026-10-17T23:54:38.945Z",
  "port": 59655,
  "token": "<redacted>",
  "protocol": 1,
  "version": "0.1.0",
  "started_at": "2026-10-17T23:54:39.503Z"
}
Restarting directly; no handshake deletion or rewrite by harness.
> CreateProcessW("E:\AI_Agent\artifacts\step2\dist\app\app.exe") [CREATE_NEW_CONSOLE, SW_HIDE; no Python/command shell]
spawn_pid=22396 handshake_pid=22396 health_pid=22396
stale_restart_process_start_to_health_200_ms=612.545
old_boot_id=872bbaac new_boot_id=3a1b84b8
old_port=59655 new_port=59664
> curl.exe --noproxy "*" http://127.0.0.1:59664/health
HTTP 200
{"status":"ok","boot_id":"3a1b84b8","pid":22396,"version":"0.1.0","uptime_s":0.125}
=== Final normal exit / test hygiene ===
> GenerateConsoleCtrlEvent(CTRL_C_EVENT) to PID 22396 [separate helper attaches to engine console]
engine_exit_code=1
process_absent=True pid=22396 listener_absent=True port=59664
handshake_exists=False (checked before any test hygiene)
No hygiene deletion was needed; any fallback cleanup below is test hygiene, never a pass criterion.
> tasklist.exe /FI "IMAGENAME eq app.exe"

CHECK_1=PASS
CHECK_2=PASS
CHECK_3=PASS
CHECK_4=PASS
CHECK_5=PASS
CHECK_6=PASS
CHECK_7=PASS
CHECK_8a=PASS
CHECK_8b=PASS
CHECK_multiprocessing=PASS
**********************
PowerShell transcript end
End time: 20261018075443
**********************

```

## 写正式 spec 前的真实 backend 进程探测

```text
> Start-Process -FilePath E:\AI_Agent\artifacts\step2\backend-probe\dist\app\app.exe -WindowStyle Hidden -PassThru
spawn_pid=23072
handshake_pid=23072
boot_id=4bbcd6be
process_created_at=2026-10-17T23:49:54.4730000Z
> tasklist.exe /FI "IMAGENAME eq app.exe"

Image Name                     PID Session Name        Session#    Mem Usage
========================= ======== ================ =========== ============
app.exe                      23072 Console                    1     76,976 K
> Get-CimInstance Win32_Process -Filter "Name = 'app.exe'"

ProcessId       : 23072
ParentProcessId : 5320
ExecutablePath  : E:\AI_Agent\artifacts\step2\backend-probe\dist\app\app.exe
CommandLine     : "E:\AI_Agent\artifacts\step2\backend-probe\dist\app\app.exe"


app_process_count=1
> curl.exe --noproxy "*" http://127.0.0.1:61065/health
{"status":"ok","boot_id":"4bbcd6be","pid":23072,"version":"0.1.0","uptime_s":0.672}
PASS: real backend onedir process_count=1; spawn_pid=handshake.pid=health.pid.
Probe cleanup: test hygiene only; not evidence of engine automatic handshake cleanup.

```

## 正式构建末 18 行

```text
31294 INFO: Building PKG (CArchive) app.pkg
31332 INFO: Building PKG (CArchive) app.pkg completed successfully.
31334 INFO: Bootloader E:\AI_Agent\.venv\Lib\site-packages\PyInstaller\bootloader\Windows-64bit-intel\run.exe
31334 INFO: checking EXE
31334 INFO: Building EXE because EXE-00.toc is non existent
31334 INFO: Building EXE from EXE-00.toc
31334 INFO: Copying bootloader EXE to E:\AI_Agent\artifacts\step2\build\app.exe
31338 INFO: Copying icon to EXE
31340 INFO: Copying 0 resources to EXE
31340 INFO: Embedding manifest in EXE
31342 INFO: Appending PKG archive to EXE
31452 INFO: Fixing EXE headers
31565 INFO: Building EXE from EXE-00.toc completed successfully.
31569 INFO: checking COLLECT
31569 INFO: Building COLLECT because COLLECT-00.toc is non existent
31569 INFO: Building COLLECT COLLECT-00.toc
31947 INFO: Building COLLECT COLLECT-00.toc completed successfully.
31954 INFO: Build complete! The results are available in: E:\AI_Agent\artifacts\step2\dist
```

## 环境与锁文件只读核验

```text
executable=E:\AI_Agent\.venv\Scripts\python.exe
python=3.12.13 (main, May 10 2026, 19:35:37) [MSC v.1944 64 bit (AMD64)]
pyinstaller=6.22.3
pyinstaller-hooks-contrib=2026.8
rasterio=1.5.2
locked_count=53
installed_count=53
missing_or_mismatch=[]
extra=[]
requirements_lock_sha256=58e24b59da34461a17fd942b4047071e42b5120b3d474ba976a7e28535d40bcc
source_manifest=artifacts/step2/source-manifest.json

```

## 源码测试原始输出

```text
....                                                                     [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\AI_Agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_cancel_after_first_running_block_keeps_partial_metrics
  E:\AI_Agent\.venv\Lib\site-packages\spectral\io\spyfile.py:217: DeprecationWarning: Setting the shape on a NumPy array has been deprecated in NumPy 2.5.
  As an alternative, you can create a new view using np.reshape (with copy=False if needed).
    npArray.shape = (self.nrows, self.ncols, self.nbands)

backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_http_contract_and_real_envi_snv
backend/tests/test_foundation.py::test_cancel_after_first_running_block_keeps_partial_metrics
backend/tests/test_foundation.py::test_cancel_after_first_running_block_keeps_partial_metrics
  E:\AI_Agent\.venv\Lib\site-packages\spectral\image.py:24: DeprecationWarning: Setting the dtype on a NumPy array has been deprecated in NumPy 2.5.
  Instead of changing the dtype on an array x, create a new array with x.view(new_dtype)
    self.dtype = params.dtype

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
4 passed, 10 warnings in 0.84s

```
