"""10.7: real source sidecar + authenticated HTTP; no TestClient or engine stubs.

Run from the repository root with .venv/Scripts/python.exe and no arguments.
All generated runtime data stays under .runtime on E:, never in the source cube.
The scripted regions are integration fixtures, not human annotation ground truth.
"""
import base64
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import platform
import signal
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

import httpx
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "src-python")]
from backend.database import connect_database
from backend.paths import AppPaths
from backend.identity import process_created_at_for_pid
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.annotation.engines.superpixels import SuperpixelEngine

SEED_HASH = "388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def png(view):
    with Image.open(BytesIO(base64.b64decode(view["png_base64"], validate=True))) as image:
        image.load()
        assert image.format == "PNG" and max(image.size) <= 512
        assert list(image.size) == [view["width"], view["height"]]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    seeds_path = ROOT / "milestone04/evidence/seeds_20.json"
    assert digest(seeds_path) == SEED_HASH
    seeds = json.loads(seeds_path.read_text("utf-8"))
    assert len(seeds) == 20
    header = Path((ROOT / "milestone04/evidence/calibration/cubes_11.txt").read_text("utf-8").splitlines()[0])
    assert header.is_file(), "real pe cube required; this standalone acceptance does not skip"
    runtime = ROOT / ".runtime" / "m04-e2e" / uuid4().hex
    runtime.mkdir(parents=True)
    os.environ.update(TEMP=str(runtime), TMP=str(runtime), PYTHONIOENCODING="utf-8")
    paths = AppPaths(runtime)
    report = {"source_level": "implementation measurement; real source sidecar process / HTTP, CPU",
              "started_at": datetime.now(timezone.utc).isoformat(), "header": str(header),
              "seed_sha256": SEED_HASH, "runtime": str(runtime),
              "environment": {"python": sys.version, "platform": platform.platform(),
                              "processor": platform.processor(), "logical_cpus": os.cpu_count()},
              "annotation_purpose": "scripted synthetic integration regions; no human-label quality claim",
              "events": []}
    transcript = runtime / "sidecar-stdio.txt"
    token = None
    with transcript.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "backend", "--data-root", str(runtime)],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        try:
            deadline = time.monotonic() + 40  # Harness startup deadline, not a product default.
            while not paths.handshake.is_file():
                assert process.poll() is None, "sidecar exited before handshake; inspect runtime logs"
                assert time.monotonic() < deadline, "sidecar handshake timeout"
                time.sleep(.05)
            handshake = json.loads(paths.handshake.read_text("utf-8"))
            # Windows venv python.exe can be a launcher with a different child PID.
            assert process_created_at_for_pid(handshake["pid"]) == handshake["process_created_at"]
            assert 0 < handshake["port"] < 65536
            token = handshake["token"]
            report["sidecar"] = {k: handshake[k] for k in ("pid", "boot_id", "port", "version", "protocol")}
            report["sidecar"]["launcher_pid"] = process.pid
            with httpx.Client(base_url=f"http://127.0.0.1:{handshake['port']}",
                              headers={"Authorization": "Bearer " + token}, trust_env=False, timeout=120) as client:
                def call(method, route, body=None, status=200):
                    started = time.perf_counter()
                    response = client.request(method, route, **({"json": body} if body is not None else {}))
                    elapsed = time.perf_counter() - started
                    assert token not in response.text, "token leaked in response"
                    assert response.status_code == status, (route, response.status_code, response.text[:1000])
                    if route == "/health":
                        assert response.json()["boot_id"] == handshake["boot_id"]
                        assert response.json()["pid"] == handshake["pid"]
                    else:
                        assert response.headers["X-SpectrumAgent-Boot-Id"] == handshake["boot_id"]
                        assert int(response.headers["X-SpectrumAgent-Pid"]) == handshake["pid"]
                    assert len(response.content) <= 8 * 1024 * 1024
                    report["events"].append({"method": method, "path": route, "status": status,
                                             "http_seconds": elapsed, "response_bytes": len(response.content)})
                    return response.json()

                assert call("GET", "/health")["version"] == "0.1.0"
                imported = call("POST", "/api/v1/datasets/import", {"path": str(header)})
                item = imported["datasets"][0]
                identifier = item["id"]
                base = "/api/v1/datasets/" + identifier
                source_files = [Path(item["dataset"][key]) for key in ("header_path", "data_path")]
                before = {str(p): {"bytes": p.stat().st_size, "sha256": digest(p)} for p in source_files}
                report["source_files"] = before
                empty = call("GET", base + "/annotations/working")
                assert empty["statistics"] == {} and empty["overlay"] is None and empty["queue"] == []
                missing = call("POST", base + "/diffuse", {"seed": {"point": [29, 64]}}, status=400)
                assert missing["error"] == "SUPERPIXELS_REQUIRED"
                divided = call("POST", base + "/superpixels", {})
                png(divided["overlay"])
                assert divided["params"]["n_segments"] == 800 and divided["params"]["compactness"] == .5
                assert divided["params"]["pca_components"] == 5 and divided["params"]["k"] == 3
                report["superpixels"] = divided
                shape = tuple(divided["shape"][:2])
                assert shape == (231, 640) and divided["shape"][2] == 200
                working = call("GET", base + "/annotations/working")
                project = working["project_id"]
                tree = call("GET", "/api/v1/labels?project_id=" + project)
                with connect_database(paths.database) as db:
                    label_rows = db.execute("SELECT id,code FROM label WHERE project_id=? ORDER BY sort_order,code", (project,)).fetchall()
                labels = {code: label_id for label_id, code in label_rows}
                mapping = {str(i): row[0] for i, row in enumerate(label_rows)}
                assert tree  # The HTTP label-management route is exercised, not a frontend color table.
                indices = {code: int(index) for index, label_id in mapping.items() for code, lid in labels.items() if label_id == lid}
                observations = []
                admitted_seed = None
                for point in seeds:
                    result = call("POST", base + "/diffuse", {"seed": {"point": [point["row"], point["col"]]}})
                    candidate = result["candidate"]
                    assert result["params"] == {"threshold": .92, "queue_min_similarity": .80}
                    assert len(candidate["cos_s"]) == divided["n_after"]
                    assert candidate["min_similarity"] == min(candidate["cos_s"][i] for i in candidate["superpixels"])
                    png(candidate["overlay"])
                    observations.append({**point, "enqueued": result["enqueued"],
                                         "min_similarity": candidate["min_similarity"],
                                         "avg_similarity": candidate["avg_similarity"],
                                         "engine_seconds": result["elapsed_seconds"],
                                         "http_seconds": report["events"][-1]["http_seconds"],
                                         "not_queued_reasons": result["not_queued_reasons"]})
                    if result["enqueued"] and admitted_seed is None:
                        admitted_seed = {"point": [point["row"], point["col"]]}
                admitted = [o for o in observations if o["enqueued"]]
                assert admitted and len(admitted) < 20
                assert all(o["min_similarity"] >= .80 for o in admitted)
                assert any(o["min_similarity"] < .92 for o in observations)
                queue_view = call("GET", base + "/annotations/working")
                assert queue_view["queue"] == result["queue"] and len(queue_view["queue"]) == len(admitted)
                assert queue_view["statistics"]["labeled_pixels"] == 0
                report["fixed_twenty"] = {"enqueued": len(admitted), "blocked": 20-len(admitted),
                                          "below_growth_threshold": sum(o["min_similarity"] < .92 for o in observations),
                                          "pending_pixels": queue_view["statistics"]["pending_pixels"],
                                          "observations": observations}
                for seed in ({"box": [29, 30, 64, 65]}, {"doodle": [[29, 64], [30, 65]]}):
                    prompted = call("POST", base + "/diffuse", {"seed": seed})
                    assert prompted["candidate"]["superpixels"]
                    png(prompted["candidate"]["overlay"])
                for action in ("confirm", "uncertain", "erase"):
                    generated = call("POST", base + "/diffuse", {"seed": admitted_seed})
                    assert generated["enqueued"]
                    candidate = generated["candidate"]
                    body = {"geometry": {"superpixels": candidate["superpixels"]}, "action": action}
                    if action == "confirm":
                        body["label_id"] = labels["PE"]
                    edited = call("POST", base + "/annotations/regions", body)
                    if action == "erase":
                        assert edited["queue"] == generated["queue"]
                    else:
                        assert len(edited["queue"]) < len(generated["queue"])
                    png(edited["overlay"])
                    restored = call("POST", base + "/annotations/undo")
                    assert restored["statistics"]["labeled_pixels"] == 0
                    assert restored["statistics"]["uncertain_pixels"] == 0
                expected = np.full(shape, -1, np.int32)
                def rectangle(bounds, action, code=None):
                    l0, l1, s0, s1 = bounds
                    body = {"geometry": {"polygon": [[l0,s0],[l0,s1],[l1,s1],[l1,s0]]}, "action": action}
                    if code is not None:
                        body["label_id"] = labels[code]
                    view = call("POST", base + "/annotations/regions", body)
                    expected[l0:l1, s0:s1] = indices[code] if action == "confirm" else (-2 if action == "uncertain" else -1)
                    assert view["statistics"]["labeled_pixels"] == int((expected >= 0).sum())
                    assert view["statistics"]["uncertain_pixels"] == int((expected == -2).sum())
                    return view
                rectangle((0,231,0,640), "erase")
                for bounds, code in (((0,90,0,200),"PE"), ((90,180,200,400),"PET"), ((0,90,400,640),"PP")):
                    rectangle(bounds, "confirm", code)
                rectangle((180,220,0,150), "uncertain")
                quality = call("POST", base + "/annotations/validate")
                report["validate"] = {"http_seconds": report["events"][-1]["http_seconds"],
                                      "comparison_count": len(quality["comparisons"]),
                                      "suspicious_count": len(quality["suspicious"]),
                                      "threshold": quality["threshold"], "threshold_level": quality["threshold_level"],
                                      "not_applicable": quality["not_applicable"]}
                assert set(quality["not_applicable"].values()) == {"无模型阶段不适用"}
                assert quality["completeness"]["labeled_pixels"] == int((expected >= 0).sum())
                first = call("POST", base + "/annotations/save", {})
                assert first["note"] is None
                snapshots = [(first, expected.copy())]
                first_hashes = {p.name: digest(p) for p in (paths.snapshots / identifier / "v1").iterdir()}
                rectangle((1,3,1,3), "confirm", "PET")
                second = call("POST", base + "/annotations/save", {"note": "10.7 HTTP integration save"})
                assert json.loads(second["note"])["event"] == "save"
                rectangle((0,90,400,640), "erase")
                conflict = call("POST", base + "/annotations/save", {"overwrite": True}, status=409)
                assert conflict["error"] == "ANNOTATION_CONFLICT"
                overwritten = call("POST", base + "/annotations/save", {"overwrite": True, "confirm": True, "note": "10.7 HTTP integration overwrite"})
                assert overwritten["id"] == second["id"] and overwritten["created_at"] == second["created_at"]
                assert json.loads(overwritten["note"])["event"] == "overwrite"
                assert json.loads(overwritten["note"])["text"] == "10.7 HTTP integration overwrite"
                snapshots.append((overwritten, expected.copy()))
                versions = call("GET", base + "/annotations")
                assert [v["version_no"] for v in versions["versions"]] == [2, 1]
                for saved, _ in snapshots:
                    png(call("GET", base + "/annotations/" + saved["id"] + "/overlay"))
                assert first_hashes == {p.name: digest(p) for p in (paths.snapshots / identifier / "v1").iterdir()}
                recovered = call("GET", base + "/annotations/working")
                assert recovered == versions["working"] and recovered["queue"]
                png(recovered["overlay"])
                report["saves"] = [{k: save[k] for k in ("id", "snapshot_ref", "elapsed_seconds", "transaction_seconds", "note")}
                                   for save in (first, second, overwritten)]
                report["working_queue_recovered"] = len(recovered["queue"])
                # Obtain the sidecar OS peak after save without adding a debug endpoint.
                report["final_sidecar_peak_rss_bytes"] = call("POST", base + "/diffuse", {"seed": admitted_seed})["peak_rss_bytes"]
            print("HTTP chain completed; checking bounded independent snapshot oracle", flush=True)
            registry = DatasetRegistry(paths.database)
            # Separate harness process, after timings: reuse the shipped engine for geometry oracle.
            segmentation = SuperpixelEngine(registry).generate(identifier)
            queue_ids = {sid for candidate in recovered["queue"] for sid in candidate["superpixels"]}
            assert recovered["statistics"]["pending_pixels"] == int(np.isin(segmentation.segments, list(queue_ids)).sum())
            oracle_reports = []
            for saved, label_map in snapshots:
                relative = PurePosixPath(saved["snapshot_ref"])
                assert not relative.is_absolute() and "\\" not in str(relative) and ".." not in relative.parts
                directory = paths.snapshots.joinpath(*relative.parts)
                assert {p.name for p in directory.iterdir()} == {"label_map.npz", "label_index.json", "spectra.npz"}
                with np.load(directory / "label_map.npz", allow_pickle=False) as archive:
                    assert archive["label_map"].dtype == np.int32
                    np.testing.assert_array_equal(archive["label_map"], label_map)
                assert json.loads((directory / "label_index.json").read_text("utf-8")) == mapping
                # Independent two-pass sums, then squared deviations; at most 32 original rows.
                sums, counts = {}, {}
                for l0 in range(0, shape[0], 32):
                    dataset, _ = registry.readable(identifier, raw=False)
                    block = dataset.read_region(l0, min(l0+32,shape[0]), 0, shape[1])
                    mask = label_map[l0:l0+32]
                    for index in np.unique(mask[mask >= 0]):
                        pixels = block[mask == index]
                        sums[index] = sums.get(index, 0) + pixels.sum(axis=0, dtype=np.float64)
                        counts[index] = counts.get(index, 0) + len(pixels)
                        del pixels
                    del block, dataset
                means = {i: sums[i]/counts[i] for i in counts}
                squares = {i: np.zeros(200, np.float64) for i in counts}
                for l0 in range(0, shape[0], 32):
                    dataset, _ = registry.readable(identifier, raw=False)
                    block = dataset.read_region(l0, min(l0+32,shape[0]), 0, shape[1])
                    mask = label_map[l0:l0+32]
                    for index in np.unique(mask[mask >= 0]):
                        delta = block[mask == index] - means[index]
                        squares[index] += np.einsum("ij,ij->j", delta, delta)
                        del delta
                    del block, dataset
                max_error = 0.
                with np.load(directory / "spectra.npz", allow_pickle=False) as archive:
                    assert set(archive.files) == {f"{kind}_{i}" for i in counts for kind in ("mean","std")}
                    for i in counts:
                        for kind, actual in (("mean", means[i]), ("std", np.sqrt(squares[i]/counts[i]))):
                            value = archive[f"{kind}_{i}"]
                            assert value.dtype == np.float64
                            np.testing.assert_allclose(value, actual, rtol=0, atol=1e-10)
                            max_error = max(max_error, float(np.max(np.abs(value-actual))))
                with connect_database(paths.database) as db:
                    db.row_factory = sqlite3.Row
                    version = dict(db.execute("SELECT * FROM annotation_version WHERE id=?", (saved["id"],)).fetchone())
                    assert version["labeled_pixels"] == int((label_map >= 0).sum())
                    assert version["auto_ratio"] == 0 and json.loads(version["params"]) == divided["params"]
                    for table in ("annotation", "sample_spectrum"):
                        rows = [dict(row) for row in db.execute(f"SELECT * FROM {table} WHERE version_id=?", (saved["id"],))]
                        assert len(rows) == len(counts) and len({r["label_id"] for r in rows}) == len(counts)
                        for row in rows:
                            index = int(next(i for i, lid in mapping.items() if lid == row["label_id"]))
                            assert row["cube_id"] == identifier and row["version_id"] == version["id"]
                            assert row["pixel_count" if table == "annotation" else "n_pixels"] == counts[index]
                            if table == "annotation":
                                assert row["source"] == "manual" and row["granularity"] == "sample"
                                expected_ids = [int(sid) for sid in np.unique(segmentation.segments)
                                                if np.all(label_map[segmentation.segments == sid] == index)]
                                assert json.loads(row["geometry"])["superpixels"] == expected_ids
                            else:
                                assert row["mean_ref"] == f"mean_{index}" and row["std_ref"] == f"std_{index}"
                                assert row["sample_code"] == item["dataset"]["name"]
                    assert db.execute("SELECT count(*) FROM annotation WHERE granularity='scene'").fetchone()[0] == 0
                oracle_reports.append({"version_id": saved["id"], "label_count": len(counts),
                                       "max_spectrum_absolute_error": max_error, "pixelwise_replay": True})
            report["snapshot_oracles"] = oracle_reports
            assert before == {str(p): {"bytes": p.stat().st_size, "sha256": digest(p)} for p in source_files}
            assert digest(seeds_path) == SEED_HASH
            report["source_and_seeds_unchanged"] = True
        finally:
            if token and process_created_at_for_pid(handshake["pid"]) == handshake["process_created_at"]:
                os.kill(handshake["pid"], signal.SIGTERM)
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)
            report["sidecar_stopped"] = process.poll() is not None and (not token or process_created_at_for_pid(handshake["pid"]) is None)
            assert report["sidecar_stopped"]
    log_paths = [transcript, *(p for p in paths.logs.rglob("*") if p.is_file())]
    assert token and all(token not in p.read_text("utf-8", errors="replace") for p in log_paths)
    report["token_absent_from_logs_and_responses"] = True
    report["checked_log_files"] = [str(p.relative_to(runtime)) for p in log_paths]
    report["passed"] = True
    # PNGs are already decode-checked; retain one example without repeating queue images.
    report["superpixels"].pop("overlay")
    (OUT / "e2e-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", "utf-8")
    print(json.dumps({"passed": True, "http_calls": len(report["events"]),
                      "queue": {k:v for k,v in report["fixed_twenty"].items() if k != "observations"},
                      "saves": report["saves"], "validate": report["validate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
