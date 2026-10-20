"""Fresh pytest process per repetition; both overwrite parameters, ten times."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TEST = "src-python/tests/annotation/test_session.py::test_db_failure_rolls_back_rows_and_snapshot_publication"


def main():
    environment = dict(os.environ, PYTEST_DEBUG_TEMPROOT=str(ROOT / ".runtime/pytest-tmp"),
                       PYTHONIOENCODING="utf-8")
    Path(environment["PYTEST_DEBUG_TEMPROOT"]).mkdir(parents=True, exist_ok=True)
    results = []
    for repetition in range(1, 11):
        command = [sys.executable, "-m", "pytest", TEST, "-q"]
        run = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                             encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        filename = f"flake-{repetition:02d}.txt"
        (OUT / filename).write_text(run.stdout, "utf-8")
        passed = run.returncode == 0 and "2 passed" in run.stdout and "skipped" not in run.stdout
        results.append({"repetition": repetition, "exit_code": run.returncode,
                        "both_parameters_passed": passed, "output": filename})
        print(f"repetition {repetition}/10: {'2 passed' if passed else 'FAILED'}", flush=True)
    summary = {"mode": "repository-root python -m pytest; selected test, default parametrization, sequential; fresh process per repetition",
               "command": command, "PYTEST_DEBUG_TEMPROOT": environment["PYTEST_DEBUG_TEMPROOT"],
               "parameters": [False, True], "repetitions_per_parameter": 10, "results": results,
               "passed_cases": sum(2 for run in results if run["both_parameters_passed"]),
               "passed": all(run["both_parameters_passed"] for run in results)}
    (OUT / "flake-summary.json").write_text(json.dumps(summary, indent=2)+"\n", "utf-8")
    assert summary["passed"], "flake reproduced: inspect individual outputs; do not silently retry"


if __name__ == "__main__":
    main()
