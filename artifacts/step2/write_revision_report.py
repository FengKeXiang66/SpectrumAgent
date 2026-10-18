"""Render the current report from saved raw evidence; never synthesize responses."""
import hashlib
import importlib.metadata
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[2]
step = root / "artifacts/step2"
revision = step / "revision-01"
session = Path((revision / "latest-session.txt").read_text(encoding="utf-8").strip())
runtime = session / "runtime"
summary = json.loads((runtime / "summary.json").read_text(encoding="utf-8"))
assert summary["passed"], "Latest regression has not passed"
rows = summary["records"]
starts = {row["label"]: row for row in rows if row["event"] == "handshake_confirmed_published"}
exits = {row["boot_id"]: row for row in rows if row["event"] == "exit_verified"}
passed = [row["case"] for row in rows if row["event"] == "round_passed"]
assert len(passed) == 30
matrix = []
for mode in ("frozen", "dev"):
    for kind in ("break", "ctrl_c", "taskkill"):
        cases = [f"{mode}-{kind}-{number}" for number in range(1, 6)]
        results = [exits[starts[case]["handshake"]["boot_id"]] for case in cases]
        assert all(case in passed for case in cases)
        matrix.append({
            "mode": mode, "signal": kind, "passed": len(results),
            "exit_codes_actual_engine": [row["exit_code"] for row in results],
            "exit_codes_launcher": [row["launcher_exit_code"] for row in results],
            "engine_stopped_counts": [row["engine_stopped_count"] for row in results],
            "residue_after_exit": [row["handshake_exists"] for row in results],
        })
(revision / "matrix-summary.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
inputs = json.loads((runtime / "input-sha256.json").read_text(encoding="utf-8"))
assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in inputs.items())
frozen = json.loads((revision / "frozen-source-comparison.json").read_text(encoding="utf-8"))
assert all(frozen["code_matches"].values())
assert frozen["exe_sha256"] == hashlib.sha256((step / "dist/app/app.exe").read_bytes()).hexdigest()
events = Counter(row["event"] for row in rows)
inventory = next(row for row in rows if row["event"] == "bundle_inventory")
diagnostics = [row for row in rows if row["event"] == "diagnostic_isolation_verified"]
assert len(diagnostics) == 2
pytest_output = (revision / "pytest-transaction-output.txt").read_text(encoding="utf-8")
pytest_result = re.search(r"(\d+) passed, (\d+) warnings", pytest_output)
assert pytest_result
test_count, warning_count = pytest_result.groups()
receipts = {"session": str(session.relative_to(step)), "matrix": matrix, "event_counts": events,
            "input_hashes_match": True, "frozen_code_matches": frozen, "inventory": inventory}
(revision / "verification-receipt.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")

# Preserve selected complete raw event lines, including their original line endings.
selected = []
seen = Counter()
for line in (runtime / "events.jsonl").read_bytes().splitlines(keepends=True):
    row = json.loads(line)
    event = row["event"]
    if event == "curl_response" or event == "diagnostic_isolation_verified":
        selected.append(line)
    elif event in ("process_inventory", "legitimate_owner_protected", "mutex_timeout_verified", "mutex_abandoned_verified", "missing_dll_verified", "bundle_inventory", "regression_passed"):
        selected.append(line)
    elif event == "exit_verified" and row["signal"] not in seen:
        selected.append(line)
        seen[row["signal"]] += 1
    elif event == "stale_sweep_verified" and row["stale_handshake_removed_count"] == 1 and not seen["stale"]:
        selected.append(line)
        seen["stale"] += 1
(revision / "raw-excerpts.jsonl").write_bytes(b"".join(selected))

table = "| 模式 | 信号 | 通过轮数 | 实际引擎退出码（逐轮） | engine_stopped（逐轮） | 退出后残留（逐轮） |\n|---|---|---:|---|---|---|\n"
for row in matrix:
    table += f"| {row['mode']} | {row['signal']} | {row['passed']}/5 | {row['exit_codes_actual_engine']} | {row['engine_stopped_counts']} | {row['residue_after_exit']} |\n"
text = f"""# 第 2 步修复回归报告

## 完成到哪一步

四项修复和重建后的完整回归通过，提交负责人复核。**第 2 步仍待验收关闭，第 3 步未开始。**
旧 8a“CTRL_C 优雅退出无残留已通过”的结论撤回，偶发 PASS 不证明稳定性。
历史报告、首次 FAIL、偶发 PASS、用户后续 dev/frozen 复现均保留在 revision-01/history 和根目录历史原始输出中。

## 命令与原始输出

```powershell
& 'E:\\AI_Agent\\.venv\\Scripts\\python.exe' -m pytest backend/tests -q -p no:cacheprovider --basetemp E:\\AI_Agent\\artifacts\\step2\\revision-01\\pytest-tmp-transaction
& 'E:\\AI_Agent\\.venv\\Scripts\\python.exe' -m PyInstaller --noconfirm 'E:\\AI_Agent\\artifacts\\step2\\build.spec'
& 'E:\\AI_Agent\\artifacts\\step2\\selfcheck_step2.ps1'
& 'E:\\AI_Agent\\.venv\\Scripts\\python.exe' 'E:\\AI_Agent\\artifacts\\step2\\verify_frozen_sources.py'
```

- 自动测试：{test_count} passed, {warning_count} warnings；完整原始输出 revision-01/pytest-transaction-output.txt。
- 正式构建原始输出：revision-01/build-final-output.txt。
- 最终完整自检：{session.relative_to(step).as_posix()}/selfcheck-output.txt。
- 逐轮事件：{runtime.relative_to(step).as_posix()}/events.jsonl；每次启动另存完整非秘密握手、按 boot_id 筛选的原始日志与退出记录。
- 本次输入源码 SHA256 与工作区逐一一致；冻结 exe 的 11 个 backend 代码对象也与当前源码一致，见 verification-receipt.json / frozen-source-comparison.json。

### 两项独立生命周期验收

{table}

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
2. Local\\SpectrumAgent.EngineHandshake.Startup.v1：CreateMutexW(false)，WaitForSingleObject(30000)，仅 startup() 范围持锁；成功与异常均正确 ReleaseMutex / CloseHandle。真实超时和 abandoned 均有回归事件，单元测试覆盖四个等待结果。
3. dev/frozen × 三类终止 × 五轮 = 30 轮全部通过；两种模式都覆盖外来陈旧握手、合法所有者拒绝、真实活 PID + 错时间的 PID 复用。合法所有者挑战者在绑定前拒绝，文件字节不变。
4. 诊断参数在 engine_boot 前分派，仅 diagnostic_started；主握手前后 SHA256 相同，PID/boot_id 不变；诊断与 worker 均未导入引擎/Uvicorn，也没有 engine_boot / engine_ready / Uvicorn 日志。

### 打包态既有项目回归

四个 curl 响应体与完整诊断 JSON 均来自原始 events.jsonl，未手工拼装返回体。
GeoTIFF 每次现造并读回 EPSG:32650、12×10、3 波段、transform 与像元值，临时样本删除。
GDAL_DATA / PROJ_DATA / PROJ_LIB 均为 null，模块与数据路径来自 _internal。
_internal：{inventory['internal_file_count']} 文件、{inventory['internal_bytes']} 字节；rasterio.libs {inventory['rasterio_dll_count']} DLL、rasterio {inventory['rasterio_pyd_count']} pyd。
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
"""
text += b"".join(selected).decode("utf-8").replace("\r\n", "\n") + "```\n"
(step / "REPORT.md").write_text(text, encoding="utf-8")
print(json.dumps({"passed": True, "session": str(session), "matrix": matrix, "event_counts": events}, ensure_ascii=False))
