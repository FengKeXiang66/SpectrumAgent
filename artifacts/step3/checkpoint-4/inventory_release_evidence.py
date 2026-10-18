"""Byte inventory of tracked acceptance artifacts. No product files or secrets are included."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(r"E:\AI_Agent")
MANIFEST = ROOT / "artifacts/step3/checkpoint-4/evidence-manifest.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"create", "verify"}:
        raise SystemExit("Use create once after staging, or verify to check archived bytes")
    if sys.argv[1] == "create":
        assert not MANIFEST.exists(), "Never overwrite a previous evidence inventory"
        raw = subprocess.check_output(["git", "ls-files", "-z", "--", "artifacts/step3/checkpoint-4", "artifacts/step3/staging-reports"], cwd=ROOT)
        paths = [p.decode("utf-8") for p in raw.split(b"\0") if p]
        rows = []
        for relative in sorted(paths):
            path = ROOT / relative
            assert "/temp/" not in relative and path.suffix.lower() not in {".exe", ".dll", ".pyd", ".zip"}
            if path != MANIFEST:
                rows.append({"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)})
        data = {"schema_version": 1, "scope": "checkpoint-4 and staging-reports acceptance evidence; excludes this inventory and later receipts",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "shell_source_commit": "83e8c37", "acceptance_verifier_commit": "171f162",
                "shell_sha256": "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f", "files": rows}
        with MANIFEST.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    else:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        rows = data["files"]
        for row in rows:
            path = ROOT / row["path"]
            assert path.stat().st_size == row["bytes"] and digest(path) == row["sha256"], row["path"]
    print(json.dumps({"action": sys.argv[1], "files": len(rows), "bytes": sum(x["bytes"] for x in rows),
                      "inventory_sha256": digest(MANIFEST), "all_match": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
