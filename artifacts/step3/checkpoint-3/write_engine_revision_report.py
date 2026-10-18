"""Generate append-only revision documentation from the new batch's original evidence."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BATCH = ROOT / "artifacts/step2/revision-20261018-smoke-headers"
SESSION = BATCH / "session-20261018-171326-708"
RUNTIME = SESSION / "runtime"
summary = json.loads((RUNTIME / "summary.json").read_text(encoding="utf-8"))
manifest = json.loads((BATCH / "product-manifest.json").read_text(encoding="utf-8"))
assert summary["passed"]
events = summary["records"]
first = next(x for x in events if x["event"] == "handshake_confirmed_published")
curl = [x for x in events if x["event"] == "curl_response"]
diagnostics = [x for x in events if x["event"] == "diagnostic_isolation_verified"]
missing = next(x for x in events if x["event"] == "missing_dll_verified")
inventory = next(x for x in events if x["event"] == "bundle_inventory")


def code(value):
    return "```text\n" + (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)) + "\n```\n"


text = """## 完成到哪一步

负责人批准的 /smoke 响应头修订及新批次重冻全量回归完成；本记录只覆盖引擎修订检查点。
第 2 步 VM 仍待实机验证，未正式关闭；旧 exit code=70 内部原因未验证。

## 命令与原始输出

本批次路径：artifacts/step2/revision-20261018-smoke-headers/。
原批次 source=d218262，旧 manifest/REPORT/全部旧证据及旧 dist 均保留。
新 artifact_source_commit 与 manifest_generator_commit 分开记录如下。
"""
text += code({k: v for k, v in manifest.items() if k != "files"})
text += r"""
### 实际命令

```powershell
& E:\AI_Agent\.venv\Scripts\python.exe artifacts\step2\revision-20261018-smoke-headers\batch_manifest.py inputs
& E:\AI_Agent\.venv\Scripts\python.exe -m PyInstaller --noconfirm E:\AI_Agent\artifacts\step2\revision-20261018-smoke-headers\build.spec
& E:\AI_Agent\.venv\Scripts\python.exe artifacts\step2\revision-20261018-smoke-headers\batch_manifest.py source
& E:\AI_Agent\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp E:\AI_Agent\artifacts\step2\revision-20261018-smoke-headers\temp\pytest-head
& E:\AI_Agent\.venv\Scripts\python.exe artifacts\step2\revision-20261018-smoke-headers\batch_manifest.py seal
& E:\AI_Agent\.venv\Scripts\python.exe artifacts\step2\revision-20261018-smoke-headers\batch_manifest.py stage
& E:\AI_Agent\artifacts\step2\revision-20261018-smoke-headers\selfcheck_step2.ps1
& E:\AI_Agent\.venv\Scripts\python.exe artifacts\step2\revision-20261018-smoke-headers\batch_manifest.py verify
```

全量 pytest 原文（既有 test_foundation.py SHA256 5a2415e1…09c014 不变）：
"""
text += code((BATCH / "pytest-source-head-output.txt").read_text(encoding="utf-8"))
text += "\n### 1. 直接 app.exe / PID：通过\n\n控制器以 shell=False、无解释器/命令 shell 启动 app.exe，PATH 仅 Windows/System32。\n"
text += code(next(x for x in events if x["event"] == "process_inventory"))
text += "\n### 2. curl：通过\n\n四个原请求加 422/精确路径排除；完整响应体与原始响应头：\n"
for row in curl:
    text += code(row)
text += "\n### 3. 握手：通过\n\n全文（仅 token 打码）：\n" + code(first["handshake"])
text += "\n### 4. JSON 日志：通过\n\n本代原始日志三行样本（带 boot_id，实际 token 扫描见原始 regression_passed）：\n"
sample = (RUNTIME / "001-frozen-break-1.boot.jsonl").read_text(encoding="utf-8").splitlines()
sample = [line for line in sample if json.loads(line).get("boot_id") == first["handshake"]["boot_id"]][:3]
text += code("\n".join(sample))
text += "\n### 5. GeoTIFF 与 worker 隔离：通过\n\n样本每次现造并删除；无业务数据接入模块。诊断原文：\n"
for row in diagnostics:
    text += code(row["diagnostic"])
text += "\n### 6. 缺 DLL：通过\n\n针对新批次暂时移除 python312.dll，finally 按原哈希恢复；旧批次未动。原文中的系统错误文本已经是问号，保留原文，不伪造中文；前面的英文明确指出 Python DLL 的完整缺失路径，无 traceback。\n"
text += code(missing)
text += "\n### 7. 体积与计时：通过\n\n本机本轮新 exe 首进程启动样本；不代替干净 VM 或外壳完整三段计时。\n"
text += code(inventory)
text += code({"first_frozen_launch_to_health_ms": summary["first_frozen_launch_ms"]})
text += "\n### 8. 进程与握手：通过\n\n8a CTRL_BREAK 每种模式 5 轮，均确认 PID/端口消失、lifespan 删除本代握手且只记一次 engine_stopped。8b taskkill 每种模式 5 轮，残留握手先归档，再不清洗直接重启，核对新 boot_id/端口和健康响应。CTRL_C 的恢复路径另测，未冒称优雅退出。\n"
text += code(json.loads((RUNTIME / "handshake-after-kill.json").read_text(encoding="utf-8")))
text += code(next(x for x in events if x["event"] == "regression_passed"))
text += """
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
"""
target = ROOT / "artifacts/step2/REVISION-20261018-smoke-headers.md"
with target.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(text)
print(str(target))
