# 第 1 步：地基引擎

只使用已冻结的 53 包，不安装新依赖。根目录执行：

```powershell
& 'E:\AI_Agent\.venv\Scripts\python.exe' -m backend
& 'E:\AI_Agent\.venv\Scripts\python.exe' -m pytest backend/tests -q -p no:cacheprovider --basetemp E:\AI_Agent\artifacts\step1\pytest-tmp
& 'E:\AI_Agent\backend\selfcheck_step1.ps1'
```

运行数据全部位于 `%LOCALAPPDATA%\SpectrumAgent\`：`run/handshake.json`、
`logs/engine-YYYYMMDD.jsonl`、`testdata/smoke-8x8x8.hdr` 与 `.dat`、
`db/spectrum-agent.sqlite3`（WAL 连接占位，不建业务表）。NAS 路径仅在 `paths.py` 预留常量。

`GET /health` 不鉴权；其他路径均要求 `Authorization: Bearer <本次 token>`。
健康响应与握手字段保持任务卡原样。token 不写入日志。
启动由 uvicorn 以 `127.0.0.1:0` 绑定，通过 `server.sockets` 获取内核分配端口，
实际 HTTP 自检通过后，`fsync` 临时文件并用 `os.replace` 发布握手。
`process_created_at` 来自 Windows `GetProcessTimes`，统一 UTC 毫秒精度。
握手启动事务由 `Local\SpectrumAgent.EngineHandshake.Startup.v1` 串行化：
清扫死 PID / PID 复用的旧握手，合法所有者与无法判断的元数据均拒绝启动。
删除前再次读文件比对原始字节，成功清扫记录 `stale_handshake_removed`。
ASGI lifespan shutdown 清理本代握手；main finally 仅 best-effort 兜底，
只有实际删除才记录一次 `engine_stopped`。CTRL_BREAK 验证即时清理；
CTRL_C / 强杀允许残留，验证下一次引擎启动恢复，不将其记为优雅退出。

`GET /smoke?blocks=1` 读取本地 ENVI，按像元分块执行一次演示 SNV。
`blocks` 范围为 1–64。默认返回任务卡规定的五个字段。
经鉴权的 `/smoke` 响应（包括 200/409/500/422）带
`X-SpectrumAgent-Boot-Id` 与 `X-SpectrumAgent-Pid`，取自 `/health` 同一个身份对象。
外壳须先与本代已核验握手核对这两个响应头；不符按身份不匹配处理。
401 不带身份头；`/health` 和其他路径不注入。JSON body 保持原契约。
`reflectance_range` 为 **SNV 之后**的有限值范围，因此出现负数正常；
每条光谱采用总体标准差（ddof=0），常量光谱归零。
elapsed_ms 包含 ENVI 读取和 SNV。样本是确定性的 8×8×8 float32。

本轮的取消接口是 `run_smoke(header, blocks, threading.Event)`：每块提交前检查标志，
完成的块参与部分指标，取消结果包含 `status="cancelled"`、`metrics_complete=false`。
HTTP 客户端断开会置位该标志；如在连接仍可写时得到取消结果，响应为 HTTP 409，
包含 `error`、`detail` 和部分指标。未增加正式任务管理或取消端点。
已断开的客户端无法收到响应；后续持久化任务功能不属于本轮。

自检脚本直接启动独立引擎，用真实 curl.exe 检查健康、鉴权和 SNV，核对 Windows
进程创建时间并逐行解析 JSON 日志；最终强制回收测试进程和核对端口，清理自己的握手。
此清理仅为测试收尾，不能替代第 3 步的 Job Object 正常关闭与强杀验证。
测试输出保存在 `artifacts/step1/`，不含握手 token。

第 2 步的正式 onedir spec、自检脚本和原始证据位于 `artifacts/step2/`，
见该目录 README.md。冻结态额外诊断只通过命令行参数运行，不增加 HTTP 接口。
本轮仍不包含 Tauri 外壳。
