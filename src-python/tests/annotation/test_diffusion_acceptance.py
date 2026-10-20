"""Real pe cube, default parameters, immutable external 20-seed manifest.

Standalone reproduction writes evidence only to an explicit E: output path.
The missing manifest is skipped, never generated or replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src-python"))

import numpy as np
import pytest

from backend.paths import AppPaths
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.annotation.engines.diffusion import DiffusionEngine, adjacency_edges
from spectrumagent.annotation.engines.superpixels import SuperpixelEngine
from spectrumagent.annotation.session import SessionStore


def run_fixed_seeds(workspace):
    manifest = ROOT / "milestone04/evidence/seeds_20.json"
    if not manifest.is_file():
        pytest.skip("固定 seeds_20.json 未入库且本机缺失；按开工令 skip，禁止重生成")
    before = manifest.read_bytes()
    points = json.loads(before)
    assert len(points) == 20
    header = Path((ROOT / "milestone04/evidence/calibration/cubes_11.txt").read_text("utf-8").splitlines()[0])
    if not header.is_file():
        pytest.skip("真实 pe 基线 cube 不可用，无法执行固定种子验收")
    paths = AppPaths(workspace / "app")
    registry = DatasetRegistry(paths.database)
    cube_id = str(registry.import_path(str(header)).datasets[0].id)
    superpixels = SuperpixelEngine(registry)
    segmentation = superpixels.generate(cube_id)  # §5.2 defaults, no special tuning.
    assert segmentation.segments.shape == (231, 640)
    assert segmentation.mean_spectra.shape[1] == 200
    # Independently enumerate original-grid boundary pairs; the 766/~2075
    # historical anchor is not an exact assertion for this 765/830 segmentation.
    reference_edges = set()
    initial = segmentation.initial_segments
    for row in range(initial.shape[0]):
        for col in range(initial.shape[1]):
            here = int(initial[row, col])
            if row+1 < initial.shape[0] and here != initial[row+1, col]:
                reference_edges.add(tuple(sorted((here, int(initial[row+1, col])))))
            if col+1 < initial.shape[1] and here != initial[row, col+1]:
                reference_edges.add(tuple(sorted((here, int(initial[row, col+1])))))
    assert {tuple(edge) for edge in adjacency_edges(initial).tolist()} == reference_edges
    store = SessionStore(registry, paths)
    engine = DiffusionEngine(superpixels, store)
    observations = []
    start = perf_counter()
    for point in points:
        result = engine.generate(cube_id, {"point": [point["row"], point["col"]]})
        candidate = result["candidate"]
        observations.append({"row": point["row"], "col": point["col"],
                             "seed_superpixel": candidate["seed_superpixels"][0],
                             "n_superpixels": len(candidate["superpixels"]),
                             "pixel_count": candidate["pixel_count"],
                             "min_similarity": candidate["min_similarity"],
                             "avg_similarity": candidate["avg_similarity"],
                             "enqueued": result["enqueued"],
                             "blocked": result["not_queued_reasons"]["below_queue_min_similarity"],
                             "elapsed_seconds": result["elapsed_seconds"]})
    duration = perf_counter() - start
    admitted = [item for item in observations if item["enqueued"]]
    blocked = sum(item["blocked"] for item in observations)
    below_growth = sum(item["min_similarity"] < .92 for item in observations)
    assert len(admitted) >= 1 and blocked >= 1
    assert below_growth >= 1
    assert all(item["min_similarity"] >= .80 for item in admitted)
    # Explicit defaults reproduce the same result; threshold changes the result
    # on these same fixed seeds, without switching coordinates to manufacture it.
    first = observations[0]
    repeat = engine.generate(cube_id, {"point": [first["row"], first["col"]]}, threshold=.92, queue_min_similarity=.80)
    assert repeat["candidate"]["min_similarity"] == first["min_similarity"]
    assert len(repeat["candidate"]["superpixels"]) == first["n_superpixels"]
    changed = 0
    for point, original in zip(points, observations):
        lower = engine.generate(cube_id, {"point": [point["row"], point["col"]]}, threshold=.80)
        changed += len(lower["candidate"]["superpixels"]) != original["n_superpixels"]
    assert changed >= 1
    assert np.all(store.working(cube_id)["label_map"] == -1)  # Candidates never assign labels.
    assert manifest.read_bytes() == before
    return {"source_level": "implementation measurement; TASK-04 §6.1, R18 user ruling",
            "header": str(header), "seed_file": "milestone04/evidence/seeds_20.json",
            "seed_sha256": hashlib.sha256(before).hexdigest(),
            "params": repeat["params"], "superpixel_params": segmentation.report["params"],
            "n_before": segmentation.report["n_before"], "n_after": segmentation.report["n_after"],
            "initial_adjacency_edges": len(adjacency_edges(segmentation.initial_segments)),
            "final_adjacency_edges": len(adjacency_edges(segmentation.segments)),
            "enqueued": len(admitted), "blocked": blocked, "below_growth_threshold": below_growth,
            "admitted_min_similarity": min(item["min_similarity"] for item in admitted),
            "changed_at_growth_080": changed, "observations": observations,
            "twenty_default_calls_seconds": duration, "feature_bytes": repeat["feature_bytes"],
            "mean_spectra_bytes": repeat["mean_spectra_bytes"], "peak_rss_bytes": repeat["peak_rss_bytes"]}


def test_real_cube_fixed_twenty_default_queue_three_assertions(tmp_path):
    report = run_fixed_seeds(tmp_path)
    (tmp_path / "queue_20.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output
    workspace = ROOT / ".runtime/m04-diffusion-acceptance" / uuid4().hex
    workspace.mkdir(parents=True)
    report = run_fixed_seeds(workspace)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", "utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
