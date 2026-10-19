"""Capture status, then re-run after its commit with byte-identical archival."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess

ROOT = Path(r"E:\AI_Agent")
OUT = Path(__file__).resolve().parent
EXPECTED = {
    "?? 光谱平台_阶段一_代码审查与进度分析_20261018.md",
    "?? 光谱数据AI-Agent处理平台_阶段一技术选型_定稿v1.1_1792327262075_csvb.md",
}

raw = subprocess.check_output(["git", "-c", "core.quotepath=false", "status", "--porcelain"], cwd=ROOT)
assert set(raw.decode("utf-8").splitlines()) == EXPECTED, "Unexpected working-tree changes; refuse a clean-status claim"
target = OUT / "git-status-after-final-commit.txt"
existed = target.exists()
if existed:
    assert target.read_bytes() == raw, "Never overwrite a different historical status"
# After committing this file, execute again. This publishes the real post-final-
# commit status with identical bytes, so recording it introduces no Git change.
target.write_bytes(raw)
after = subprocess.check_output(["git", "-c", "core.quotepath=false", "status", "--porcelain"], cwd=ROOT)
if existed:
    assert after == raw
print(raw.decode("utf-8"), end="")
print(json.dumps({"checked_utc": datetime.now(timezone.utc).isoformat(), "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "archive": str(target), "sha256": hashlib.sha256(raw).hexdigest(), "same_bytes_as_committed_archive": existed, "scope": "除两份负责人文档外，无未跟踪、无修改"}, ensure_ascii=False, indent=2))
