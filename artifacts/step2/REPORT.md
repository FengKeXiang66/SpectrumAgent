# 第 2 步修复回归报告

## 完成到哪一步

四项修复和重建后的完整回归通过，提交负责人复核。**第 2 步仍待验收关闭，第 3 步未开始。**
旧 8a“CTRL_C 优雅退出无残留已通过”的结论撤回，偶发 PASS 不证明稳定性。
历史报告、首次 FAIL、偶发 PASS、用户后续 dev/frozen 复现均保留在 revision-01/history 和根目录历史原始输出中。

## 命令与原始输出

```powershell
& 'E:\AI_Agent\.venv\Scripts\python.exe' -m pytest backend/tests -q -p no:cacheprovider --basetemp E:\AI_Agent\artifacts\step2\revision-01\pytest-tmp-transaction
& 'E:\AI_Agent\.venv\Scripts\python.exe' -m PyInstaller --noconfirm 'E:\AI_Agent\artifacts\step2\build.spec'
& 'E:\AI_Agent\artifacts\step2\selfcheck_step2.ps1'
& 'E:\AI_Agent\.venv\Scripts\python.exe' 'E:\AI_Agent\artifacts\step2\verify_frozen_sources.py'
```

- 自动测试：27 passed, 10 warnings；完整原始输出 revision-01/pytest-transaction-output.txt。
- 正式构建原始输出：revision-01/build-final-output.txt。
- 最终完整自检：revision-01/session-20261018-090023-946/selfcheck-output.txt。
- 逐轮事件：revision-01/session-20261018-090023-946/runtime/events.jsonl；每次启动另存完整非秘密握手、按 boot_id 筛选的原始日志与退出记录。
- 本次输入源码 SHA256 与工作区逐一一致；冻结 exe 的 11 个 backend 代码对象也与当前源码一致，见 verification-receipt.json / frozen-source-comparison.json。

### 两项独立生命周期验收

| 模式 | 信号 | 通过轮数 | 实际引擎退出码（逐轮） | engine_stopped（逐轮） | 退出后残留（逐轮） |
|---|---|---:|---|---|---|
| frozen | break | 5/5 | [3, 3, 3, 3, 3] | [1, 1, 1, 1, 1] | [False, False, False, False, False] |
| frozen | ctrl_c | 5/5 | [1, 1, 1, 1, 1] | [1, 1, 1, 1, 1] | [False, False, False, False, False] |
| frozen | taskkill | 5/5 | [1, 1, 1, 1, 1] | [0, 0, 0, 0, 0] | [True, True, True, True, True] |
| dev | break | 5/5 | [3, 3, 3, 3, 3] | [1, 1, 1, 1, 1] | [False, False, False, False, False] |
| dev | ctrl_c | 5/5 | [3221225786, 3221225786, 3221225786, 3221225786, 3221225786] | [1, 1, 1, 1, 1] | [False, False, False, False, False] |
| dev | taskkill | 5/5 | [1, 1, 1, 1, 1] | [0, 0, 0, 0, 0] | [True, True, True, True, True] |


CTRL_BREAK immediate cleanup 与 CTRL_C / hard-kill recovery 分开判定。
负责人的原始设计前提保留：CTRL_BREAK exit=3 且 lifespan 可达；CTRL_C exit=1、日志停在 engine_ready、无关闭序列/traceback/进程内钩子；TerminateProcess 同样无钩子。
本轮使用独立隐藏控制台注入，CTRL_C 的实际样本如表记录；不以不同注入拓扑下触达 lifespan 的样本改写基线或证明稳定优雅退出。
表中退出码来自握手实际 PID 的 Windows 进程句柄；dev venv 启动器退出码另存 launcher_exit_code，不混用。
所有 CTRL_C / hard-kill 都只按恢复路径判定，不将偶发的进程内清理写成优雅退出保证。
存在残留时必须由下一次引擎启动清扫，并按新 boot_id 验证 stale_handshake_removed 的全部旧所有者非秘密字段。
恢复后的新引擎一律用 CTRL_BREAK 关闭，并检查 lifespan 删除本代、恰好一次 engine_stopped 和最终无残留。
每轮从确认本次握手发布到退出判定之间不做测试清理；指定的外来握手注入场景单列并明确记录。

### 四项修复及附加场景

1. 启动清扫删除旧代；关闭清理下沉 lifespan 删除本代；main finally 保留 best-effort。删除前重新读取比对，失败结构化记录且不含 token；仅实际删除时记 engine_stopped。
2. Local\SpectrumAgent.EngineHandshake.Startup.v1：CreateMutexW(false)，WaitForSingleObject(30000)，仅 startup() 范围持锁；成功与异常均正确 ReleaseMutex / CloseHandle。真实超时和 abandoned 均有回归事件，单元测试覆盖四个等待结果。
3. dev/frozen × 三类终止 × 五轮 = 30 轮全部通过；两种模式都覆盖外来陈旧握手、合法所有者拒绝、真实活 PID + 错时间的 PID 复用。合法所有者挑战者在绑定前拒绝，文件字节不变。
4. 诊断参数在 engine_boot 前分派，仅 diagnostic_started；主握手前后 SHA256 相同，PID/boot_id 不变；诊断与 worker 均未导入引擎/Uvicorn，也没有 engine_boot / engine_ready / Uvicorn 日志。

### 打包态既有项目回归

四个 curl 响应体与完整诊断 JSON 均来自原始 events.jsonl，未手工拼装返回体。
GeoTIFF 每次现造并读回 EPSG:32650、12×10、3 波段、transform 与像元值，临时样本删除。
GDAL_DATA / PROJ_DATA / PROJ_LIB 均为 null，模块与数据路径来自 _internal。
_internal：543 文件、238793334 字节；rasterio.libs 36 DLL、rasterio 15 pyd。
缺 DLL 测试保留原生报错，恢复后 SHA256 一致；Windows 退出码按 DWORD 原值记录（4294967295 即有符号 -1）。
锁文件仍 53 包、无缺失/额外包、SHA256 未变。当前构建的回归启动耗时是复跑数据，不冒充冷启动。
干净无 Python 的 Windows、OS 缓存清空后的冷启动、干净 venv 重建仍未验证。

## 遇到的问题

- 旧实现 frozen/dev 都可在 Uvicorn 完成关闭后跳过 main finally；旧的稳定通过结论已撤回，不再归因于 PyInstaller。
- revision-01/run-001 的回归控制器把 ANSI stderr 误按 UTF-8 解码而中断；原始失败保留，已改为在原始字节上检查错误码。
- 中间轮次的 dev 退出码来自启动器，最终版已单独持有实际引擎 PID 的句柄并重跑；中间记录不冒充最终证据。
- 本地化 LoadLibrary 辅助文本仍为问号；英文首行准确说明缺失 DLL 与完整路径，未改写原文。
- 原有 Starlette / spectral 弃用警告未消除，未新增依赖。

## 下一步打算

保持第 2 步未关闭，等待负责人复核本轮提交与原始证据；不开始第 3 步。

## 原始事件摘录（逐行选自 events.jsonl）

```jsonl
{"event": "process_inventory", "process_count": 1, "cim": [{"ProcessId": 13788, "ParentProcessId": 16408, "ExecutablePath": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\app.exe", "CommandLine": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\app.exe"}], "tasklist_stdout": "\r\nImage Name                     PID Session Name        Session#    Mem Usage\r\n========================= ======== ================ =========== ============\r\napp.exe                      13788 Console                    1     77,352 K\r\n"}
{"event": "curl_response", "path": "/health", "http_status": 200, "body": {"status": "ok", "boot_id": "e784c547", "pid": 13788, "version": "0.1.0", "uptime_s": 0.672}}
{"event": "curl_response", "path": "/smoke", "http_status": 401, "body": {"error": "UNAUTHORIZED", "detail": "需要本次引擎握手中的 Bearer token。"}}
{"event": "curl_response", "path": "/smoke", "http_status": 200, "body": {"nan_ratio": 0.0, "reflectance_range": [-1.5275289241381491, 1.5275289241381491], "bands": 8, "shape": [8, 8, 8], "elapsed_ms": 128.435}}
{"event": "curl_response", "path": "/smoke?blocks=8", "http_status": 200, "body": {"nan_ratio": 0.0, "reflectance_range": [-1.5275289241381491, 1.5275289241381491], "bands": 8, "shape": [8, 8, 8], "elapsed_ms": 155.324}}
{"event": "diagnostic_isolation_verified", "argument": "--selfcheck-geotiff", "main_pid": 13788, "main_boot_id": "e784c547", "before_sha256": "fc45a6c2191db313414b67acdabeabc4958c6a02009ed7f642f7a50e246ca66d", "after_sha256": "fc45a6c2191db313414b67acdabeabc4958c6a02009ed7f642f7a50e246ca66d", "forbidden_engine_events": 0, "diagnostic": {"check": "geotiff", "result": "PASS", "diagnostic_pid": 26348, "engine_module_loaded": false, "uvicorn_module_loaded": false, "frozen": true, "executable": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\app.exe", "crs": "EPSG:32650", "shape": [10, 12], "width": 12, "height": 10, "count": 3, "transform": [30.0, 0.0, 500000.0, 0.0, -30.0, 4000000.0], "dtype": "float32", "pixel_values_equal": true, "GDAL_DATA": null, "PROJ_DATA": null, "PROJ_LIB": null, "proj_db": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\rasterio\\proj_data\\proj.db", "gdalvrt_xsd": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\rasterio\\gdal_data\\gdalvrt.xsd", "rasterio_module": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\rasterio\\__init__.py", "numpy_module": "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\numpy\\__init__.py", "python_search_paths": ["E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\base_library.zip", "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\python3.12\\lib-dynload", "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal", "E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\setuptools\\_vendor"], "sample": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\testdata\\geotiff-check-lmzaz5it\\generated.tif", "sample_removed": true}, "diagnostic_logs": [{"diagnostic": "geotiff", "pid": 26348, "event": "diagnostic_started", "logger": "engine", "level": "info", "timestamp": "2026-10-18T01:00:27.096203Z"}]}
{"event": "diagnostic_isolation_verified", "argument": "--selfcheck-worker", "main_pid": 13788, "main_boot_id": "e784c547", "before_sha256": "fc45a6c2191db313414b67acdabeabc4958c6a02009ed7f642f7a50e246ca66d", "after_sha256": "fc45a6c2191db313414b67acdabeabc4958c6a02009ed7f642f7a50e246ca66d", "forbidden_engine_events": 0, "diagnostic": {"check": "multiprocessing", "result": "PASS", "diagnostic_pid": 15472, "worker_pid": 21624, "parent_pid": 15472, "frozen": true, "worker_engine_module_loaded": false, "worker_uvicorn_module_loaded": false, "worker_exitcode": 0, "handshake_unchanged": true, "engine_module_loaded": false, "uvicorn_module_loaded": false}, "diagnostic_logs": [{"diagnostic": "worker", "pid": 15472, "event": "diagnostic_started", "logger": "engine", "level": "info", "timestamp": "2026-10-18T01:00:27.974563Z"}]}
{"event": "exit_verified", "mode": "frozen", "signal": "break", "boot_id": "e784c547", "pid": 13788, "process_created_at": "2026-10-18T01:00:24.311Z", "port": 53060, "exit_code": 3, "launcher_exit_code": 3, "pid_absent": true, "port_absent": true, "engine_stopped_count": 1, "handshake_exists": false, "residual_handshake": null, "classification": "immediate_cleanup"}
{"event": "exit_verified", "mode": "frozen", "signal": "ctrl_c", "boot_id": "9d8b7f53", "pid": 27304, "process_created_at": "2026-10-18T01:00:34.479Z", "port": 53117, "exit_code": 1, "launcher_exit_code": 1, "pid_absent": true, "port_absent": true, "engine_stopped_count": 1, "handshake_exists": false, "residual_handshake": null, "classification": "recovery_path_not_graceful_exit_claim"}
{"event": "exit_verified", "mode": "frozen", "signal": "taskkill", "boot_id": "a7216bb5", "pid": 27508, "process_created_at": "2026-10-18T01:00:48.546Z", "port": 53243, "exit_code": 1, "launcher_exit_code": 1, "pid_absent": true, "port_absent": true, "engine_stopped_count": 0, "handshake_exists": true, "residual_handshake": {"boot_id": "a7216bb5", "pid": 27508, "process_created_at": "2026-10-18T01:00:48.546Z", "port": 53243, "token": "<redacted>", "protocol": 1, "version": "0.1.0", "started_at": "2026-10-18T01:00:49.148Z"}, "classification": "recovery_path_not_graceful_exit_claim"}
{"event": "stale_sweep_verified", "mode": "frozen", "boot_id": "d750027e", "stale_handshake_removed_count": 1, "records": [{"reason": "dead_pid", "old_boot_id": "a7216bb5", "old_pid": 27508, "old_process_created_at": "2026-10-18T01:00:48.546Z", "old_port": 53243, "event": "stale_handshake_removed", "boot_id": "d750027e", "pid": 13304, "logger": "engine.handshake", "level": "info", "timestamp": "2026-10-18T01:00:50.223035Z"}]}
{"event": "legitimate_owner_protected", "mode": "frozen", "owner": {"boot_id": "81d9cb9c", "pid": 22024, "process_created_at": "2026-10-18T01:01:03.927Z", "port": 53346, "token": "<redacted>", "protocol": 1, "version": "0.1.0", "started_at": "2026-10-18T01:01:04.552Z"}, "challenger_spawn_pid": 24284, "challenger_exit_code": 1, "handshake_bytes_unchanged": true, "explicit_error": "HANDSHAKE_OWNER_ALIVE", "bound_service": false}
{"event": "legitimate_owner_protected", "mode": "dev", "owner": {"boot_id": "7b5cc6bf", "pid": 22260, "process_created_at": "2026-10-18T01:01:55.219Z", "port": 53842, "token": "<redacted>", "protocol": 1, "version": "0.1.0", "started_at": "2026-10-18T01:01:56.212Z"}, "challenger_spawn_pid": 14340, "challenger_exit_code": 1, "handshake_bytes_unchanged": true, "explicit_error": "HANDSHAKE_OWNER_ALIVE", "bound_service": false}
{"event": "mutex_timeout_verified", "timeout_ms": 30000, "elapsed_ms": 30607.392, "exit_code": 1, "bound_service": false, "handshake_exists": false}
{"event": "mutex_abandoned_verified", "boot_id": "8f4c4dd3", "records": [{"action": "reread_handshake_under_lock", "event": "startup_mutex_abandoned", "pid": 2180, "boot_id": "8f4c4dd3", "logger": "engine.startup_mutex", "level": "warning", "timestamp": "2026-10-18T01:02:31.243884Z"}]}
{"event": "missing_dll_verified", "exit_code": 4294967295, "native_stderr": "[PYI-25616:ERROR] Failed to load Python DLL 'E:\\AI_Agent\\artifacts\\step2\\dist\\app\\_internal\\python312.dll'.\r\nLoadLibrary: ?????????\r\r\n"}
{"event": "bundle_inventory", "internal_file_count": 543, "internal_bytes": 238793334, "exe_bytes": 16771126, "rasterio_dll_count": 36, "rasterio_pyd_count": 15}
{"event": "regression_passed", "matrix_rounds": 30, "rounds_per_signal_per_mode": 5, "token_leaks": 0, "handshake_absent": true, "first_frozen_launch_ms": 1604.0}
```
