"""TASK-04 §6.1 queue acceptance through real authenticated HTTP endpoints."""
import argparse
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src-python"))

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app


def run_http_seeds(workspace):
    manifest = ROOT / "milestone04/evidence/seeds_20.json"
    if not manifest.is_file():
        pytest.skip("固定 seeds_20.json 未入库且本机缺失；禁止重生成")
    original = manifest.read_bytes()
    points = json.loads(original)
    assert len(points) == 20
    header = Path((ROOT / "milestone04/evidence/calibration/cubes_11.txt").read_text("utf-8").splitlines()[0])
    if not header.is_file():
        pytest.skip("真实 pe 基线 cube 不可用，HTTP 固定种子验收无法执行")
    identity = EngineIdentity()
    app = create_app(AppPaths(workspace / "http-app"), identity)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        imported = client.post("/api/v1/datasets/import", json={"path": str(header)})
        assert imported.status_code == 200, imported.text
        cube_id = imported.json()["datasets"][0]["id"]
        base = "/api/v1/datasets/" + cube_id
        divided = client.post(base+"/superpixels", json={})
        assert divided.status_code == 200, divided.text
        observations = []
        for point in points:
            response = client.post(base+"/diffuse", json={"seed": {"point": [point["row"], point["col"]]}})
            assert response.status_code == 200, response.text
            assert response.headers["X-SpectrumAgent-Boot-Id"] == identity.boot_id
            result = response.json()
            assert result["params"] == {"threshold": .92, "queue_min_similarity": .80}
            assert len(result["candidates"]) == 1
            candidate = result["candidates"][0]
            assert len(candidate["cos_s"]) == divided.json()["n_after"]
            image = Image.open(BytesIO(base64.b64decode(candidate["overlay"]["png_base64"])))
            assert image.format == "PNG" and max(image.size) <= 512
            observations.append({"row": point["row"], "col": point["col"],
                                 "min_similarity": candidate["min_similarity"],
                                 "enqueued": result["enqueued"],
                                 "blocked": result["not_queued_reasons"]["below_queue_min_similarity"]})
        admitted = [item for item in observations if item["enqueued"]]
        blocked = sum(item["blocked"] for item in observations)
        below = sum(item["min_similarity"] < .92 for item in observations)
        assert len(admitted) >= 1 and blocked >= 1
        assert below >= 1
        assert all(item["min_similarity"] >= .80 for item in admitted)
        assert len(result["queue"]) == len(admitted)
        working = client.get(base+"/annotations/working")
        assert working.status_code == 200
        queue_ids = {sid for candidate in result["queue"] for sid in candidate["superpixels"]}
        state = app.state.annotation_sessions._state(cube_id)
        expected_pending = int(np.isin(state.segments, list(queue_ids)).sum())
        assert working.json()["statistics"]["pending_pixels"] == expected_pending
        assert working.json()["statistics"]["labeled_pixels"] == 0
        assert np.all(state.label_map == -1)
        assert client.get(base+"/annotations").json()["versions"] == []
    assert manifest.read_bytes() == original
    return {"source_level": "implementation measurement; authenticated HTTP / TASK-04 §6.1",
            "header": str(header), "seed_sha256": hashlib.sha256(original).hexdigest(),
            "params": result["params"], "n_before": divided.json()["n_before"], "n_after": divided.json()["n_after"],
            "enqueued": len(admitted), "blocked": blocked, "below_growth_threshold": below,
            "admitted_min_similarity": min(item["min_similarity"] for item in admitted),
            "pending_union_pixels": expected_pending, "observations": observations,
            "feature_bytes": divided.json()["feature_bytes"], "peak_rss_bytes": result["peak_rss_bytes"]}


def test_http_fixed_twenty_default_queue_three_assertions(tmp_path):
    report = run_http_seeds(tmp_path)
    (tmp_path / "http_queue_20.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output
    workspace = ROOT / ".runtime/m04-http-acceptance" / uuid4().hex
    workspace.mkdir(parents=True)
    report = run_http_seeds(workspace)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", "utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
