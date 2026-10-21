"""Reproduce receipt samples on an explicit synthetic 24x5x8 raw-DN fixture.

Run from repository root with .venv/Scripts/python.exe. No source dataset writes,
no source cube materialization; all mutable runtime files stay under .runtime/.
This is implementation evidence, not human-label quality or real-cube performance.
"""
from hashlib import sha256
import json
from pathlib import Path
import sys
from uuid import uuid4

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/"src-python"))

from tests.preprocess.run_fixtures import run_case, step
from spectrumagent.preprocess.compare import CompareEngine


def main():
    directory = ROOT/".runtime"/"m05-11.3"/str(uuid4())
    directory.mkdir(parents=True)
    case = run_case.__wrapped__(directory)
    recipe = case.recipe([step("standardize", method="standard")])
    standard = case.runner.run(case.cube, case.version, recipe, block_size=3)
    ica_recipe = case.recipe([step("ica", n_components=3)])
    first = case.runner.run(case.cube, case.version, ica_recipe, block_size=1)
    second = case.runner.run(case.cube, case.version, ica_recipe, block_size=7)
    assert standard["status"] == first["status"] == second["status"] == "succeeded"
    reports = [case.report(first), case.report(second)]
    x = case.values[case.label_map >= 0].astype(float)/65535
    scores = [(x-np.asarray(report["steps"][0]["meta"]["mean"])) @ np.asarray(report["steps"][0]["meta"]["loadings"])
              for report in reports]
    diff = float(np.max(np.abs(scores[0]-scores[1])))
    np.testing.assert_array_equal(scores[0], scores[1])
    comparison = CompareEngine(case.runner).compare(case.cube, case.version, [recipe, ica_recipe])
    failed = case.runner.run(case.cube, case.version, case.recipe([step("pca", n_components=9)]))
    assert failed["status"] == "failed" and failed["artifacts"] == []
    evidence = {
        "source": "TASK-05 §5/§2.6 R12；固定合成像素夹具，非人工标注质量、非真实 cube 性能",
        "mode": "repository-root .venv python capture.py; synchronous, default operator params; ICA block_size=1/7",
        "fixture": {"shape": [24, 5, 8], "raw_dtype": "uint16", "scale_factor": 65535,
                    "annotation_pixels": 110, "provenance": "tests/preprocess/run_fixtures.py"},
        "run_rows": [standard, first, second, failed],
        "ica_max_abs_score_diff": diff,
        "ica_temporary_bytes": reports[0]["temporary_bytes"],
        "ica_peak_rss_bytes": reports[0]["peak_rss_bytes"],
        "no_temporary_files_remaining": not list(case.paths.preprocessed.rglob(".tmp")),
        "comparison_ranking": comparison["ranking"],
        "artifact_bytes": [{"run_id": row["id"], "kind": artifact["kind"],
                            "bytes": (case.paths.preprocessed/artifact["relative_path"]).stat().st_size}
                           for row in (standard, first) for artifact in row["artifacts"]],
        "task_card_sha256": sha256((ROOT/"TASK-05-预处理.md").read_bytes()).hexdigest(),
    }
    output = Path(__file__).parent
    (output/"run-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), "utf-8")
    (output/"ica-report.json").write_text(json.dumps(reports[0], ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"ica_max_abs_score_diff": diff, "temporary_bytes": reports[0]["temporary_bytes"],
                      "peak_rss_bytes": reports[0]["peak_rss_bytes"], "rows": len(evidence["run_rows"])}, indent=2))


if __name__ == "__main__":
    main()
