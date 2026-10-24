"""R24: three existing targets x ten fresh pytest processes, no implementation edits."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TESTS = [
    ("draft-cas", "src-python/tests/annotation/test_draft.py::test_ten_concurrent_connections_have_one_winner_and_monotonic_revision"),
    ("confirm-cas", "src-python/tests/annotation/test_session.py::test_confirm_rechecks_revision_inside_publication_transaction"),
    ("overwrite-mat", "src-python/tests/annotation/test_confirm_routes.py::test_failed_confirm_overwrite_invalidates_old_mat_without_rolling_back_version"),
]


def run_target(node, filename):
    environment = dict(os.environ, PYTEST_DEBUG_TEMPROOT="E:/AI_Agent/.runtime/pytest-tmp", PYTHONIOENCODING="utf-8")
    command = [sys.executable, "-m", "pytest", node, "-q"]
    result = subprocess.run(command, cwd=ROOT, env=environment, encoding="utf-8",
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / filename).write_text(result.stdout, "utf-8")
    return {"exit_code": result.returncode, "output": filename,
            "passed": result.returncode == 0 and "1 passed" in result.stdout and "skipped" not in result.stdout}


def main():
    summary = {"started_at": datetime.now(timezone.utc).isoformat(), "rounds_per_test": 10,
        "mode": "fresh pytest process per exposure; harness exposures sequential; pytest default parameters, no serial-test override",
        "environment": {"PYTEST_DEBUG_TEMPROOT": "E:/AI_Agent/.runtime/pytest-tmp"},
        "per_test": {}, "exposures": [], "standalone_rechecks": [], "root_cause": "not inferred"}
    for key, node in TESTS:
        counts = {"exposures": 10, "passed": 0, "failed": 0}
        summary["per_test"][node] = counts
        for repetition in range(1, 11):
            result = run_target(node, f"flake-{key}-{repetition:02d}.txt")
            counts["passed" if result["passed"] else "failed"] += 1
            summary["exposures"].append({"test": key, "round": repetition, **result})
            print(f"{key} {repetition}/10: {'PASS' if result['passed'] else 'FAIL'}", flush=True)
    for key, node in TESTS:
        if summary["per_test"][node]["failed"]:
            result = run_target(node, f"flake-{key}-standalone.txt")
            result.update(test=key, classification="environmental single occurrence, root cause unconfirmed" if result["passed"] else "reproduced; stop for review")
            summary["standalone_rechecks"].append(result)
    summary["exposure_passed"] = sum(c["passed"] for c in summary["per_test"].values())
    summary["exposure_failed"] = sum(c["failed"] for c in summary["per_test"].values())
    summary["passed"] = summary["exposure_failed"] == 0
    (OUT / "flake-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"exposure_passed": summary["exposure_passed"], "exposure_failed": summary["exposure_failed"]}), flush=True)
    if any(not r["passed"] for r in summary["standalone_rechecks"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
