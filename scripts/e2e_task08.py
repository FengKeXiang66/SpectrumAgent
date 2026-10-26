"""TASK-08 13.1: real ASGI import -> confirmation -> preprocessing -> preflight.

Synthetic spectra only, no provider network or fitted modeling estimator.
All generated data/evidence stay in the ignored workspace runtime directory.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter
import tracemalloc
from unittest.mock import patch
from uuid import uuid4

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src-python/spectrumagent/app.py").is_file())
sys.path[:0] = [str(ROOT), str(ROOT / "src-python")]

import numpy as np
from fastapi.testclient import TestClient

from backend.database import connect_database
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app
from spectrumagent.data import SpectrumDataSet


def rect(first, left, last, right):
    return {"type": "polygon", "points": [[first, left], [first, right], [last, right], [last, left]]}


def main():
    runtime = ROOT / ".runtime/task08-13.1" / uuid4().hex
    runtime.mkdir(parents=True)
    evidence = {"base_commit": "19d09da", "source_level": "real ASGI/engines, four synthetic cubes, no provider network",
                "started_at": datetime.now(timezone.utc).isoformat(), "assertions": [], "success": False}

    def check(condition, name):
        evidence["assertions"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    identity = EngineIdentity()
    paths = AppPaths(runtime / "app")
    app = create_app(paths, identity)
    try:
        with TestClient(app) as client:
            client.headers["Authorization"] = "Bearer " + identity.token

            def call(method, url, body=None, status=200):
                response = client.request(method, url, **({"json": body} if body is not None else {}))
                check(response.status_code == status, f"{method} {url}: HTTP {status}")
                check("X-SpectrumAgent-Boot-Id" in response.headers, f"{method} {url}: identity")
                return response.json()

            recipe = call("POST", "/api/v1/preprocess/recipes", {"code": "model-preflight", "name": "preflight",
                          "pipeline": {"steps": [{"op": "standardize", "version": 1, "params": {"method": "standard"}}]}}, status=201)
            cubes, versions, runs = [], [], []
            for index in range(4):
                values = np.random.default_rng(131 + index).integers(1000, 30000, (40, 12, 8), dtype=np.uint16)
                header = runtime / f"cube-{index}.hdr"
                header.with_suffix(".img").write_bytes(values.tobytes())
                header.write_text("ENVI\nlines=40\nsamples=12\nbands=8\ndata type=12\ninterleave=bip\n"
                                  "byte order=0\nreflectance scale factor=65535\n", "utf-8")
                cube = call("POST", "/api/v1/datasets/import", {"path": str(header), "raw": True})["datasets"][0]["id"]
                segmentation = call("POST", f"/api/v1/datasets/{cube}/superpixels",
                                    {"n_segments": 24, "compactness": .5, "pca_components": 5})
                check(segmentation["superpixel_count"] > 0, "real segmentation")
                base = f"/api/v1/annotations/{cube}/draft"
                call("POST", base + "/regions", {"revision": 0, "class_code": "BG", "geometry": rect(0, 0, 40, 6)})
                call("POST", base + "/regions", {"revision": 1, "class_code": "PP", "geometry": rect(0, 6, 20, 12)})
                call("POST", base + "/regions", {"revision": 2, "op": "uncertain", "geometry": rect(20, 6, 40, 9)})
                version = call("POST", base + "/confirm", {"revision": 3})["version_id"]
                with connect_database(paths.database) as db:
                    relative = db.execute("SELECT snapshot_ref FROM annotation_version WHERE id=?", (version,)).fetchone()[0]
                with np.load(paths.snapshots/relative/"label_map.npz", allow_pickle=False) as archive:
                    check(archive.files == ["label_map"], "actual confirmation snapshot key label_map")
                    labels = archive["label_map"]
                    check(int((labels >= 0).sum()) == 360, "confirmed pixels per cube = 360")
                    check(int((labels == -1).sum()) == int((labels == -2).sum()) == 60, "both negative states present")
                run = call("POST", f"/api/v1/datasets/{cube}/preprocess/runs", {
                           "annotation_version_id": version, "recipe_version_id": recipe["versions"][0]["id"]})
                check(run["status"] == "succeeded", "real preprocess recipe succeeds")
                check({item["kind"] for item in run["artifacts"]} == {"report", "sample_spectra"}, "no processed cube artifact")
                cubes.append(cube); versions.append(version); runs.append(run["id"])

            request = {"cube_ids": cubes, "annotation_version_ids": versions, "preprocess_run_ids": runs,
                       "task": "classification", "target": "label", "cv_strategy": "group_kfold", "cv_folds": 2, "seed": 17}
            reads = []
            original_read = SpectrumDataSet.read_region

            def bounded(dataset, first, last, left, right):
                check(last-first <= 32, "model pixel read block <=32 rows")
                reads.append(last-first)
                return original_read(dataset, first, last, left, right)

            tracemalloc.start()
            started = perf_counter()
            try:
                with patch.object(SpectrumDataSet, "read_region", bounded), patch.object(SpectrumDataSet, "to_numpy", side_effect=AssertionError("no full cube")), \
                     patch("spectrumagent.agent.mat.MatStore.generate", side_effect=AssertionError("MAT is not modeling input")):
                    result = call("POST", "/api/v1/models/runs/preflight", request)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            check(result["status"] == "succeeded", "preflight succeeds")
            check(result["n_samples"] == 1440 and result["n_features"] == 8, "four labeled datasets shape")
            check(reads == [32, 8]*4, "two bounded blocks per cube")
            report = result["leak_report"]
            check(report["group_cross_fold"]["violation_count"] == 0, "zero group leakage")
            check(report["duplicate_content"]["duplicate_count"] == 0, "zero duplicate source content")
            check(report["preprocess_full_fit"]["acknowledged"] is True, "full-data fit acknowledged")
            check("standardize" in report["preprocess_full_fit"]["affected_steps"], "standardize visibly affected")
            for fold in result["folds"]:
                check(len(fold["train_groups"]) == len(fold["test_groups"]) == 2, "four cubes = four groups")
                check(not set(fold["train_groups"]) & set(fold["test_groups"]), "train/test groups disjoint")
                check(fold["train_count"] == fold["test_count"] == 720, "fold pixel counts")
            details = call("GET", "/api/v1/models/runs/"+result["run_id"])
            check(details["metrics"] == [], "metrics response stays empty")
            listing = call("GET", "/api/v1/models/runs?cube_id="+cubes[0])
            check(len(listing) == 1 and listing[0]["id"] == result["run_id"], "list filters on cube membership")
            with connect_database(paths.database) as db:
                check(db.execute("SELECT model_family,model_params FROM training_run").fetchone() == (None, None), "no model family or params")
                check(db.execute("SELECT COUNT(*) FROM metric").fetchone()[0] == 0, "metric table empty")
                check(db.execute("SELECT COUNT(*) FROM model_artifact").fetchone()[0] == 0, "model artifact table empty")
            serialized = json.dumps([result, details, listing])
            check(all(word not in serialized for word in ['"X"', '"y"', '"train_idx"', '"test_idx"', '"path"', '"relative_path"', '"predictions"']),
                  "no spectra, predictions or paths in modeling responses")
            check(str(runtime) not in serialized, "no local runtime path leaks")
            evidence.update(cube_ids=cubes, result=result, details=details, bounded_row_reads=reads,
                            mapped_folds=[{**fold, "train_cube_ids": [cubes[i] for i in fold["train_groups"]],
                                           "test_cube_ids": [cubes[i] for i in fold["test_groups"]]} for fold in result["folds"]],
                            measurement={"mode": "whole ASGI preflight request; synthetic 4x40x12x8; tracemalloc not RSS",
                                         "tracemalloc_peak_bytes": peak, "http_seconds": perf_counter()-started})
        evidence["success"] = True
    finally:
        evidence["assertion_count"] = len(evidence["assertions"])
        (runtime / "e2e-result.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False)+"\n", "utf-8")
    print(json.dumps({"success": evidence["success"], "assertions": evidence["assertion_count"],
                      "peak_bytes": peak, "evidence": str(runtime / "e2e-result.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
