## 完成到哪一步

负责人批准的 /smoke 响应头修订及新批次重冻全量回归完成；本记录只覆盖引擎修订检查点。
第 2 步 VM 仍待实机验证，未正式关闭；旧 exit code=70 内部原因未验证。

## 命令与原始输出

本批次路径：artifacts/step2/revision-20261018-smoke-headers/。
原批次 source=d218262，旧 manifest/REPORT/全部旧证据及旧 dist 均保留。
新 artifact_source_commit 与 manifest_generator_commit 分开记录如下。
```text
{
  "schema_version": 1,
  "artifact_source_commit": "3acd979f3b5a94ad32283eb1608c95f0b8721696",
  "manifest_generated_at": "2026-10-18T09:12:59.962Z",
  "manifest_generator_commit": "e7c3c9d90f83d23639a4ee54832c8b4bc75bf706",
  "artifact_root": "artifacts/step2/revision-20261018-smoke-headers/dist/app"
}
```

### 实际命令

```powershell
& E:\AI_Agent\.venv\Scripts\python.exe artifacts\step2evision-20261018-smoke-headersatch_manifest.py inputs
& E:\AI_Agent\.venv\Scripts\python.exe -m PyInstaller --noconfirm E:\AI_Agentrtifacts\step2evision-20261018-smoke-headersuild.spec
& E:\AI_Agent\.venv\Scripts\python.exe artifacts\step2evision-20261018-smoke-headersatch_manifest.py source
& E:\AI_Agent\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp E:\AI_Agentrtifacts\step2evision-20261018-smoke-headers	emp\pytest-head
& E:\AI_Agent\.venv\Scripts\python.exe artifacts\step2evision-20261018-smoke-headersatch_manifest.py seal
& E:\AI_Agent\.venv\Scripts\python.exe artifacts\step2evision-20261018-smoke-headersatch_manifest.py stage
& E:\AI_Agentrtifacts\step2evision-20261018-smoke-headers\selfcheck_step2.ps1
& E:\AI_Agent\.venv\Scripts\python.exe artifacts\step2evision-20261018-smoke-headersatch_manifest.py verify
```

全量 pytest 原文（既有 test_foundation.py SHA256 5a2415e1…09c014 不变）：
```text
.......................................                                  [100%]
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
39 passed, 10 warnings in 1.78s

```

### 1. 直接 app.exe / PID：通过

控制器以 shell=False、无解释器/命令 shell 启动 app.exe，PATH 仅 Windows/System32。
```text
{
  "event": "process_inventory",
  "process_count": 1,
  "cim": [
    {
      "ProcessId": 25392,
      "ParentProcessId": 19896,
      "ExecutablePath": "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\app.exe",
      "CommandLine": "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\app.exe"
    }
  ],
  "tasklist_stdout": "\r\nImage Name                     PID Session Name        Session#    Mem Usage\r\n========================= ======== ================ =========== ============\r\napp.exe                      25392 Console                    1     77,444 K\r\n"
}
```

### 2. curl：通过

四个原请求加 422/精确路径排除；完整响应体与原始响应头：
```text
{
  "event": "curl_response",
  "path": "/health",
  "http_status": 200,
  "headers": {
    "date": "Sun, 18 Oct 2026 09:13:27 GMT",
    "server": "uvicorn",
    "content-length": "83",
    "content-type": "application/json"
  },
  "body": {
    "status": "ok",
    "boot_id": "0f67aa47",
    "pid": 25392,
    "version": "0.1.0",
    "uptime_s": 0.656
  }
}
```
```text
{
  "event": "curl_response",
  "path": "/smoke",
  "http_status": 401,
  "headers": {
    "date": "Sun, 18 Oct 2026 09:13:27 GMT",
    "server": "uvicorn",
    "www-authenticate": "Bearer",
    "content-length": "82",
    "content-type": "application/json"
  },
  "body": {
    "error": "UNAUTHORIZED",
    "detail": "需要本次引擎握手中的 Bearer token。"
  }
}
```
```text
{
  "event": "curl_response",
  "path": "/smoke",
  "http_status": 200,
  "headers": {
    "date": "Sun, 18 Oct 2026 09:13:27 GMT",
    "server": "uvicorn",
    "content-length": "124",
    "content-type": "application/json",
    "x-spectrumagent-boot-id": "0f67aa47",
    "x-spectrumagent-pid": "25392"
  },
  "body": {
    "nan_ratio": 0.0,
    "reflectance_range": [
      -1.5275289241381491,
      1.5275289241381491
    ],
    "bands": 8,
    "shape": [
      8,
      8,
      8
    ],
    "elapsed_ms": 273.35
  }
}
```
```text
{
  "event": "curl_response",
  "path": "/smoke?blocks=8",
  "http_status": 200,
  "headers": {
    "date": "Sun, 18 Oct 2026 09:13:28 GMT",
    "server": "uvicorn",
    "content-length": "125",
    "content-type": "application/json",
    "x-spectrumagent-boot-id": "0f67aa47",
    "x-spectrumagent-pid": "25392"
  },
  "body": {
    "nan_ratio": 0.0,
    "reflectance_range": [
      -1.5275289241381491,
      1.5275289241381491
    ],
    "bands": 8,
    "shape": [
      8,
      8,
      8
    ],
    "elapsed_ms": 195.011
  }
}
```
```text
{
  "event": "curl_response",
  "path": "/smoke?blocks=0",
  "http_status": 422,
  "headers": {
    "date": "Sun, 18 Oct 2026 09:13:28 GMT",
    "server": "uvicorn",
    "content-length": "231",
    "content-type": "application/json",
    "x-spectrumagent-boot-id": "0f67aa47",
    "x-spectrumagent-pid": "25392"
  },
  "body": {
    "error": "INVALID_REQUEST",
    "detail": "1 validation error:\n  {'type': 'greater_than_equal', 'loc': ('query', 'blocks'), 'msg': 'Input should be greater than or equal to 1', 'input': '0', 'ctx': {'ge': 1}}\n\n  Endpoint: GET /smoke"
  }
}
```
```text
{
  "event": "curl_response",
  "path": "/smokeX",
  "http_status": 404,
  "headers": {
    "date": "Sun, 18 Oct 2026 09:13:28 GMT",
    "server": "uvicorn",
    "content-length": "43",
    "content-type": "application/json"
  },
  "body": {
    "error": "HTTP_ERROR",
    "detail": "Not Found"
  }
}
```

### 3. 握手：通过

全文（仅 token 打码）：
```text
{
  "boot_id": "0f67aa47",
  "pid": 25392,
  "process_created_at": "2026-10-18T09:13:27.076Z",
  "port": 56520,
  "token": "<redacted>",
  "protocol": 1,
  "version": "0.1.0",
  "started_at": "2026-10-18T09:13:27.758Z"
}
```

### 4. JSON 日志：通过

本代原始日志三行样本（带 boot_id，实际 token 扫描见原始 regression_passed）：
```text
{"event": "Started server process [25392]", "pid": 25392, "boot_id": "0f67aa47", "logger": "uvicorn.error", "level": "info", "timestamp": "2026-10-18T09:13:27.710635Z"}
{"event": "Waiting for application startup.", "pid": 25392, "boot_id": "0f67aa47", "logger": "uvicorn.error", "level": "info", "timestamp": "2026-10-18T09:13:27.711188Z"}
{"event": "Application startup complete.", "pid": 25392, "boot_id": "0f67aa47", "logger": "uvicorn.error", "level": "info", "timestamp": "2026-10-18T09:13:27.723842Z"}
```

### 5. GeoTIFF 与 worker 隔离：通过

样本每次现造并删除；无业务数据接入模块。诊断原文：
```text
{
  "check": "geotiff",
  "result": "PASS",
  "diagnostic_pid": 19856,
  "engine_module_loaded": false,
  "uvicorn_module_loaded": false,
  "frozen": true,
  "executable": "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\app.exe",
  "crs": "EPSG:32650",
  "shape": [
    10,
    12
  ],
  "width": 12,
  "height": 10,
  "count": 3,
  "transform": [
    30.0,
    0.0,
    500000.0,
    0.0,
    -30.0,
    4000000.0
  ],
  "dtype": "float32",
  "pixel_values_equal": true,
  "GDAL_DATA": null,
  "PROJ_DATA": null,
  "PROJ_LIB": null,
  "proj_db": "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\_internal\\rasterio\\proj_data\\proj.db",
  "gdalvrt_xsd": "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\_internal\\rasterio\\gdal_data\\gdalvrt.xsd",
  "rasterio_module": "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\_internal\\rasterio\\__init__.py",
  "numpy_module": "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\_internal\\numpy\\__init__.py",
  "python_search_paths": [
    "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\_internal\\base_library.zip",
    "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\_internal\\python3.12\\lib-dynload",
    "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\_internal",
    "E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\_internal\\setuptools\\_vendor"
  ],
  "sample": "C:\\Users\\Administrator\\AppData\\Local\\SpectrumAgent\\testdata\\geotiff-check-zqbwmtd6\\generated.tif",
  "sample_removed": true
}
```
```text
{
  "check": "multiprocessing",
  "result": "PASS",
  "diagnostic_pid": 24248,
  "worker_pid": 24140,
  "parent_pid": 24248,
  "frozen": true,
  "worker_engine_module_loaded": false,
  "worker_uvicorn_module_loaded": false,
  "worker_exitcode": 0,
  "handshake_unchanged": true,
  "engine_module_loaded": false,
  "uvicorn_module_loaded": false
}
```

### 6. 缺 DLL：通过

针对新批次暂时移除 python312.dll，finally 按原哈希恢复；旧批次未动。原文中的系统错误文本已经是问号，保留原文，不伪造中文；前面的英文明确指出 Python DLL 的完整缺失路径，无 traceback。
```text
{
  "event": "missing_dll_verified",
  "exit_code": 4294967295,
  "native_stderr": "[PYI-27004:ERROR] Failed to load Python DLL 'E:\\AI_Agent\\artifacts\\step2\\revision-20261018-smoke-headers\\dist\\app\\_internal\\python312.dll'.\r\nLoadLibrary: ?????????\r\r\n"
}
```

### 7. 体积与计时：通过

本机本轮新 exe 首进程启动样本；不代替干净 VM 或外壳完整三段计时。
```text
{
  "event": "bundle_inventory",
  "internal_file_count": 543,
  "internal_bytes": 238793334,
  "exe_bytes": 16771455,
  "rasterio_dll_count": 36,
  "rasterio_pyd_count": 15
}
```
```text
{
  "first_frozen_launch_to_health_ms": 705.066
}
```

### 8. 进程与握手：通过

8a CTRL_BREAK 每种模式 5 轮，均确认 PID/端口消失、lifespan 删除本代握手且只记一次 engine_stopped。8b taskkill 每种模式 5 轮，残留握手先归档，再不清洗直接重启，核对新 boot_id/端口和健康响应。CTRL_C 的恢复路径另测，未冒称优雅退出。
```text
{
  "boot_id": "912723b4",
  "pid": 25884,
  "process_created_at": "2026-10-18T09:13:50.408Z",
  "port": 56680,
  "token": "<redacted>",
  "protocol": 1,
  "version": "0.1.0",
  "started_at": "2026-10-18T09:13:51.005Z"
}
```
```text
{
  "event": "regression_passed",
  "matrix_rounds": 30,
  "rounds_per_signal_per_mode": 5,
  "token_leaks": 0,
  "handshake_absent": true,
  "first_frozen_launch_ms": 705.066
}
```

完整逐轮原始输出：session-20261018-171326-708/selfcheck-output.txt；runtime/events.jsonl、
summary.json 及每次信号/握手/退出/日志文件可独立复核。测试卫生仅指失败时收尾及开始前
的合法陈旧状态清理，不作为通过依据；本次 matrix 的判定均在任何卫生清理之前。

## 遇到的问题

1. 清单首次读取 Git 中文文件名失败 OSError 22；改用 git ls-files -z。原文 build-inputs-output.txt。
2. 额外的旧新 internal 逐字节断言失败：仅 base_library.zip SHA 不同。只读探针确认 155 个
   成员内容、CRC、大小、日期及其他元数据全部相同，仅 ZIP 顺序与 header_offset 不同。
   其余 542 个文件完全相同。旧新体积均为 543 文件/238793334 字节，七项硬检查全部通过后
   才颁发新 manifest；未替换任何 ZIP，也未改写旧 manifest。差异调查与首轮失败原文保留。
3. 清单生成器在源码冻结后独立修订：冻结来源 3acd979 不变，生成器 e7c3c9d；生成器核验
   源码来源提交中的原始脚本哈希及当前 HEAD 脚本字节，实际 backend/lock/spec 仍要求与
   构建前哈希一致。没有用生成器修订冒充引擎源码重新冻结。
4. pytest 的 10 条依赖弃用 warning 原文保留；未新增/升级 Python 包。

## 下一步打算

新批次可用于 Rust /smoke 响应头联调；联调必须引用本批 product-manifest.json。
Tauri 资源布局、窗口、前端 invoke 与最终 release 验收尚未验证，不由本回归倒推。
