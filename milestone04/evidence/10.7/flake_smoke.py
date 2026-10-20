"""Step-1: two tests, ten fresh pytest processes each; keep 10.7 evidence intact."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TESTS = [
    ("rollback", "src-python/tests/annotation/test_session.py::test_db_failure_rolls_back_rows_and_snapshot_publication", "2 passed"),
    ("validate", "src-python/tests/annotation/test_routes.py::test_validation_has_no_body_and_uuid_only_version_errors", "1 passed"),
]


def main():
    environment = dict(os.environ, PYTEST_DEBUG_TEMPROOT=str(ROOT / ".runtime/pytest-tmp"),
                       PYTHONIOENCODING="utf-8")
    Path(environment["PYTEST_DEBUG_TEMPROOT"]).mkdir(parents=True, exist_ok=True)
    results = []
    per_test = {nodeid: {"passed": 0, "failed": 0} for _, nodeid, _ in TESTS}
    for key, nodeid, expected in TESTS:
        for repetition in range(1, 11):
            command = [sys.executable, "-m", "pytest", nodeid, "-q"]
            run = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                                 encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            filename = f"flake-{key}-{repetition:02d}.txt"
            (OUT / filename).write_text(run.stdout, "utf-8")
            passed = run.returncode == 0 and expected in run.stdout and "skipped" not in run.stdout
            per_test[nodeid]["passed" if passed else "failed"] += 1
            results.append({"test": key, "repetition": repetition,
                            "exit_code": run.returncode, "output": filename})
            print(f"{key} repetition {repetition}/10: {expected if passed else 'FAILED'}", flush=True)
    summary = {"mode": "repository-root python -m pytest; two tests x 10 repetitions, fresh process per repetition, default params, sequential; PYTEST_DEBUG_TEMPROOT set",
               "tests": [{"key": key, "nodeid": nodeid, "expected": expected} for key, nodeid, expected in TESTS],
               "per_test": per_test, "results": results,
               "passed": len(results) == 20 and all(item["failed"] == 0 for item in per_test.values())}
    (OUT / "flake-summary-step1.json").write_text(json.dumps(summary, indent=2)+"\n", "utf-8")
    assert summary["passed"], "flake reproduced: inspect individual outputs; do not silently retry"
    print("环境性单发、已留证", flush=True)


if __name__ == "__main__":
    main()
