"""Validate staged raw evidence without repeating product acceptance runs."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess

ROOT = Path(r"E:\AI_Agent")
OUT = Path(__file__).resolve().parent


def run(*args):
    return subprocess.check_output(["git", "-c", "core.quotepath=false", *args], cwd=ROOT)


def read(name):
    raw = (OUT / name).read_bytes()
    return json.loads(raw.decode("utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"))


def main():
    p = read("installed-delivery-result.json")
    assert p["status"] == "passed_process_dom_checks" and p["shell_exit_code"] == 0
    assert not p["remaining_processes"] and p["remaining_port_listeners"] == 0
    assert p["handshake_exists_after_close"] and not p["handshake_cleanup_passed"]
    assert p["single_instance"]["secondary_exit"] == 0 and len(p["single_instance"]["remaining_shells"]) == 1
    for action in ("CaptureComplete", "RecoverRepro", "InstallDelivery", "ProbeDelivery", "UninstallDelivery"):
        r = read("real-task-" + action + "-result.json")
        assert r["status"] == "passed" and r["sid"].endswith("-500")
        assert r["lineage"]["first_timestamp"] == "2026-10-19T01:47:35.930Z"
        scheduler = read("real-task-" + action + "-scheduler-receipt.json")
        assert scheduler["deleted_exit"] == 0
    before, after = read("data-before-uninstall.json"), read("data-after-uninstall.json")
    assert before == after and len(before) == 17
    for folder in ("db/", "logs/", "run/", "testdata/"):
        assert any(row["path"].startswith(folder) for row in before)
    markers = read("uninstall-markers.json")
    assert len(markers) == 3
    data_root = "C:/Users/Administrator/AppData/Local/SpectrumAgent/"
    mapping = {r["path"]: r["sha256"] for r in before}
    for marker in markers:
        relative = marker["path"].replace("\\", "/").removeprefix(data_root)
        assert mapping[relative] == marker["sha256"]
    for log in p["logs"]:
        snapshot, segment = Path(log["source_snapshot"]), Path(log["archive"])
        raw = snapshot.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == log["source_sha256"]
        assert raw[log["byte_start"]:log["byte_end_exclusive"]] == segment.read_bytes()
        assert hashlib.sha256(segment.read_bytes()).hexdigest() == log["archive_sha256"]
    assert hashlib.sha256(Path(p["dom"]["archive"]).read_bytes()).hexdigest() == p["dom"]["sha256"]
    assert not (OUT / "host-install-state.json").exists()
    locks = read("final-locks-and-product-source.json")["locks"]
    for name, expected in locks.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert run("check-ignore", ".runtime/owned-test-file").strip()
    # Git raw-blob IDs, not text-normalized status, establish byte preservation.
    staged = run("ls-files", "-s", "-z").split(b"\0")
    raw_records, text_records = [], []
    attr_cache = {}
    for row in staged:
        if not row:
            continue
        meta, path_raw = row.split(b"\t", 1)
        path = path_raw.decode("utf-8")
        if not path.startswith("artifacts/step3/"):
            continue
        mode, oid, stage = meta.split()
        actual = (ROOT / path).read_bytes()
        raw_oid = hashlib.sha1(b"blob " + str(len(actual)).encode() + b"\0" + actual).hexdigest()
        attr = run("check-attr", "text", "--", path).decode().strip().rsplit(": ", 1)[-1]
        record = {"path": path, "bytes": len(actual), "worktree_sha256": hashlib.sha256(actual).hexdigest(), "git_blob_oid": oid.decode(), "text_attribute": attr, "raw_bytes_equal_git_blob": raw_oid == oid.decode()}
        if attr == "unset" or b"\0" in actual:
            assert raw_oid == oid.decode(), "Raw evidence changed by Git filters: " + path
            raw_records.append(record)
        else:
            text_records.append(record)
    changed = run("diff", "--name-only", "HEAD", "--").decode().splitlines()
    assert not any(p.startswith("backend/") or p.startswith("src-tauri/src/") or p.startswith("artifacts/step2/") for p in changed)
    result = {"checked_utc": datetime.now(timezone.utc).isoformat(), "status": "passed_archive_checks", "product_acceptance_not_rerun": True, "real_data_rows": len(before), "real_dom_pid": p["shell_pid"] if isinstance(p, dict) else 18680, "known_failed_handshake_cleanup_preserved": True, "locks_unchanged": True, "raw_blob_files": len(raw_records), "source_text_files": len(text_records), "raw_records": raw_records, "text_records": text_records}
    with (OUT / "final-archive-verification.json").open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("raw_records", "text_records")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
