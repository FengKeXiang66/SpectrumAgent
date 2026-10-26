"""Three REST routes, legacy bridge and hand-calculated MAT size summaries."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.identity import EngineIdentity
from spectrumagent.annotation.raster import decode_rle, polygon_mask, rasterize
from spectrumagent.app import create_app
from test_draft import POLYGON
from test_routes import http_annotation, ready_http
from test_gestures import fake_diffusion


@pytest.fixture
def draft_api(annotation_case):
    c = annotation_case
    identity = EngineIdentity()
    app = create_app(c.paths, identity)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        yield SimpleNamespace(case=c, app=app, client=client, identity=identity,
                              base=f"/api/v1/annotations/{c.identifier}/draft")


def post(h, revision=0, **fields):
    return h.client.post(h.base + "/regions", json={"revision": revision, "class_code": "PE", "geometry": deepcopy(POLYGON), **fields})


def test_three_size_states_are_zero_16_pixels_and_full_480_pixels(draft_api):
    h = draft_api
    empty = h.client.get(h.base)
    assert empty.status_code == 200
    assert empty.json() == {"cube_id": h.case.identifier, "revision": 0, "document": None,
        "schema_version": 1, "raster_rule_version": 1, "updated_at": None, "estimated_mat_bytes": 0}
    assert empty.headers["X-SpectrumAgent-Boot-Id"] == h.identity.boot_id
    added = post(h)
    assert added.status_code == 200 and set(added.json()) == {"revision", "region_id", "statistics"}
    assert added.json()["statistics"]["labeled_pixels"] == 16
    partial = h.client.get(h.base).json()
    assert partial["estimated_mat_bytes"] == 16 * 200 * 4 == 12800
    changed = h.client.post(h.base + "/regions/r-0001", json={"revision": 1,
        "geometry": {"type": "polygon", "points": [[0, 0], [0, 12], [40, 12], [40, 0]]}})
    assert changed.status_code == 200 and changed.json() == {"revision": 2, "region_id": "r-0001"}
    full = h.client.get(h.base).json()
    assert full["estimated_mat_bytes"] == 480 * 200 * 4 == 384000
    assert full["document"]["regions"][0]["source"] == "manual"
    assert full["document"]["regions"][0]["confidence"] == "high"
    assert full["document"]["regions"][0]["created_at"] == partial["document"]["regions"][0]["created_at"]


@pytest.mark.parametrize("body", [
    {"op": "uncertain", "class_code": "PE"}, {"op": "uncertain", "class_code": None},
    {"op": "erase", "confidence": "high"}, {"op": "erase", "confidence": None},
    {"source": "manual"}, {"source": "algorithm"}, {"class_index": 1},
])
def test_illegal_fields_are_rejected_without_creating_document(draft_api, body):
    h = draft_api
    request = {"revision": 0, "geometry": POLYGON, **body}
    if body.get("op", "add") == "add":
        request["class_code"] = "PE"
    response = h.client.post(h.base + "/regions", json=request)
    assert response.status_code == 400 and response.json()["error"] == "TOOL_ARGS_INVALID"
    assert h.client.get(h.base).json()["revision"] == 0


def test_cas_missing_revision_replay_and_stale_patch(draft_api):
    h = draft_api
    missing = h.client.post(h.base + "/regions", json={"class_code": "PE", "geometry": POLYGON})
    assert missing.status_code == 400 and missing.json()["error"] == "TOOL_ARGS_INVALID"
    assert post(h).status_code == 200
    assert post(h).status_code == 409
    assert post(h).json()["error"] == "DRAFT_REVISION_CONFLICT"
    stale = h.client.post(h.base + "/regions/r-0001", json={"revision": 0, "deleted": True})
    assert stale.status_code == 409
    assert h.client.get(h.base).json()["revision"] == 1


@pytest.mark.parametrize("field", ["source", "region_id", "created_at", "op"])
def test_patch_rejects_lineage_fields(draft_api, field):
    h = draft_api
    assert post(h).status_code == 200
    response = h.client.post(h.base + "/regions/r-0001", json={"revision": 1, field: "forged"})
    assert response.status_code == 400 and response.json()["error"] == "TOOL_ARGS_INVALID"
    assert h.client.get(h.base).json()["revision"] == 1


def test_gesture_reference_add_is_resolved_but_patch_still_refuses(draft_api):
    h = draft_api
    h.app.state.annotation_sessions.set_segmentation(h.case.identifier, SimpleNamespace(segments=h.case.segments, report={"params": h.case.params}))
    stored = h.client.post(f"/api/v1/annotations/{h.case.identifier}/gestures", json={"seed": {"point": [1, 1]}})
    assert stored.status_code == 200 and stored.json()["kind"] == "point"
    response = post(h, geometry={"gesture_ref": stored.json()["gesture_ref"]})
    assert response.status_code == 200 and set(response.json()) == {"revision", "region_id", "statistics"}
    assert h.client.get(h.base).json()["document"]["regions"][-1]["geometry"]["type"] == "pixel_set"
    response = h.client.post(h.base + "/regions/r-0001", json={"revision": 1, "geometry": {"gesture_ref": "gesture-1"}})
    assert response.status_code == 400 and "手势引用尚未接入" in response.json()["detail"]


@pytest.mark.parametrize("seed", [{"point": [2, 3]}, {"box": [0, 5, 0, 4]}, {"doodle": [[1, 1], [2, 2]]}])
def test_store_gesture_rest_shapes_unique_refs_and_unknown_refs(draft_api, seed):
    h = draft_api
    path = f"/api/v1/annotations/{h.case.identifier}/gestures"
    first = h.client.post(path, json={"seed": seed})
    second = h.client.post(path, json={"seed": seed})
    assert first.status_code == second.status_code == 200
    assert set(first.json()) == {"gesture_ref", "kind"} and first.json()["kind"] == next(iter(seed))
    assert first.json()["gesture_ref"] != second.json()["gesture_ref"]
    h.app.state.annotation_sessions.set_segmentation(h.case.identifier, SimpleNamespace(segments=h.case.segments, report={"params": h.case.params}))
    missing = post(h, geometry={"gesture_ref": "g-" + "0" * 32})
    assert missing.status_code == 404 and missing.json()["error"] == "GESTURE_NOT_FOUND"
    assert h.client.get(h.base).json()["revision"] == 0


@pytest.mark.parametrize("seed", [{}, {"point": [1]}, {"point": ["1", 2]}, {"doodle": []},
    {"box": [0, 1, 2]}, {"point": [1, 2], "box": [0, 2, 0, 2]}])
def test_store_gesture_rejects_malformed_seed_without_storage(draft_api, seed):
    h = draft_api
    response = h.client.post(f"/api/v1/annotations/{h.case.identifier}/gestures", json={"seed": seed})
    assert response.status_code == 400 and response.json()["error"] == "TOOL_ARGS_INVALID"
    assert not h.app.state.annotation_sessions._states


@pytest.mark.parametrize("floor,confidence", [(.8, "medium"), (.99, "low")])
def test_candidates_rest_shared_service_cas_and_source(draft_api, monkeypatch, floor, confidence):
    h = draft_api
    sessions = h.app.state.annotation_sessions
    sessions.set_segmentation(h.case.identifier, SimpleNamespace(segments=h.case.segments, report={"params": h.case.params}))
    controlled = fake_diffusion(SimpleNamespace(store=sessions))
    monkeypatch.setattr(h.app.state.diffusion_engine, "generate", controlled.generate)
    ref = sessions.store_gesture(h.case.identifier, {"point": [1, 1]})
    body = {"revision": 0, "class_code": "PE", "method": "SAM", "params": {
        "gesture_ref": ref, "threshold": .5, "queue_min_similarity": floor}}
    response = h.client.post(h.base + "/candidates", json=body)
    assert response.status_code == 200
    assert set(response.json()) == {"revision", "region_id", "geometry_type", "preview_statistics"}
    assert set(response.json()["preview_statistics"]) == {"n_superpixels", "pixel_count", "min_similarity", "avg_similarity"}
    assert response.json()["geometry_type"] == "pixel_set"
    before = h.client.get(h.base).json()
    assert before["document"]["regions"][-1]["source"] == "algorithm"
    assert before["document"]["regions"][-1]["confidence"] == confidence
    assert sessions._state(h.case.identifier).candidates == []
    stale = h.client.post(h.base + "/candidates", json=body)
    assert stale.status_code == 409 and stale.json()["error"] == "DRAFT_REVISION_CONFLICT"
    assert h.client.get(h.base).json() == before
    body.update(revision=1, method="SLIC", params={"n_segments": 24, "compactness": .5, "pca_components": 5})
    slic = h.client.post(h.base + "/candidates", json=body)
    assert slic.status_code == 400 and slic.json()["error"] == "TOOL_NOT_IMPLEMENTED"
    controlled.generate.assert_called_once()


@pytest.mark.parametrize("method,params", [("SAM", {"n_segments": 8, "compactness": .5, "pca_components": 3}),
    ("SLIC", {"gesture_ref": "g-1", "threshold": .5, "queue_min_similarity": .8}), ("SLIC", {"n_segments": 0})])
def test_candidates_method_params_mismatch_is_400(draft_api, method, params):
    response = draft_api.client.post(draft_api.base + "/candidates", json={"revision": 0, "class_code": "PE", "method": method, "params": params})
    assert response.status_code == 400 and response.json()["error"] == "TOOL_ARGS_INVALID"


def test_uncertain_erase_and_deletion_preserve_document_semantics(draft_api):
    h = draft_api
    assert post(h).status_code == 200
    for revision, op, value in [(1, "uncertain", -2), (2, "erase", -1)]:
        response = h.client.post(h.base + "/regions", json={"revision": revision, "op": op, "geometry": POLYGON})
        assert response.status_code == 200
        document = h.client.get(h.base).json()["document"]
        region = document["regions"][-1]
        assert "class_index" not in region and "confidence" not in region and region["source"] == "manual"
        assert rasterize(document, h.case.values.shape)[0, 0] == value
    assert h.client.get(h.base).json()["estimated_mat_bytes"] == 0
    deleted = h.client.post(h.base + "/regions/r-0003", json={"revision": 3, "deleted": True})
    assert deleted.status_code == 200 and deleted.json()["revision"] == 4
    new = post(h, 4)
    assert new.json()["region_id"] == "r-0005"


def test_not_found_errors_and_deferred_routes(draft_api):
    h = draft_api
    missing = h.client.get(f"/api/v1/annotations/{uuid4()}/draft")
    assert missing.status_code == 404 and missing.json()["error"] == "DATASET_NOT_FOUND"
    bad_label = post(h, class_code="missing")
    assert bad_label.status_code == 400 and bad_label.json()["error"] == "LABEL_NOT_FOUND"
    missing_region = h.client.post(h.base + "/regions/r-9999", json={"revision": 0, "deleted": True})
    assert missing_region.status_code == 404 and missing_region.json()["error"] == "REGION_NOT_FOUND"
    for suffix in ["/candidates"]:
        response = h.client.post(h.base + suffix, json={})
        assert response.status_code == 400 and response.json()["error"] == "TOOL_ARGS_INVALID"


def test_draft_routes_require_existing_sidecar_authentication(draft_api):
    h = draft_api
    authorization = h.client.headers.pop("Authorization")
    try:
        response = h.client.get(h.base)
        assert response.status_code == 401
        assert "X-SpectrumAgent-Boot-Id" not in response.headers
    finally:
        h.client.headers["Authorization"] = authorization


@pytest.mark.parametrize("action", ["confirm", "uncertain", "erase"])
@pytest.mark.parametrize("kind", ["polygon", "superpixels"])
def test_legacy_geometry_and_action_mapping_are_preserved(ready_http, action, kind):
    h = ready_http
    geometry = {"polygon": POLYGON["points"]} if kind == "polygon" else {"superpixels": [0]}
    body = {"geometry": geometry, "action": action}
    if action == "confirm":
        body["label_id"] = h.case.labels["PE"]
    response = h.client.post(h.base + "/annotations/regions", json=body)
    assert response.status_code == 200
    state = h.sessions._state(h.case.identifier)
    document = h.sessions.drafts.get(h.case.identifier)["document"]
    region, = document["regions"]
    assert region["op"] == ("add" if action == "confirm" else action)
    assert region["source"] == "manual"
    if kind == "polygon":
        assert region["geometry"] == {"type": "polygon", "points": POLYGON["points"]}
        mask = polygon_mask(state.label_map.shape, POLYGON["points"])
    else:
        assert region["geometry"]["segments_fingerprint"] == state.params
        mask = state.segments == 0
        np.testing.assert_array_equal(decode_rle(region["geometry"]["rows"], state.label_map.shape), mask)
    expected = list(state.label_ids).index(h.case.labels["PE"]) if action == "confirm" else (-2 if action == "uncertain" else -1)
    assert np.all(state.label_map[mask] == expected)
    assert np.all(state.label_map[~mask] == -1)
    if action == "confirm":
        assert region["confidence"] == "high"
    else:
        assert "class_index" not in region and "confidence" not in region


def test_rest_edits_and_legacy_undo_share_one_document(ready_http):
    h = ready_http
    base = f"/api/v1/annotations/{h.case.identifier}/draft"
    assert h.client.post(base + "/regions", json={"revision": 0, "class_code": "PE", "geometry": POLYGON}).status_code == 200
    assert h.client.post(h.base + "/annotations/undo").status_code == 200
    doc = h.client.get(base).json()
    assert doc["revision"] == 2 and doc["document"]["regions"] == []
    assert h.sessions.working(h.case.identifier)["statistics"]["labeled_pixels"] == 0
