import base64
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image, ImageColor
import pytest

from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.data import DataError


@pytest.fixture
def http_annotation(annotation_case):
    c = annotation_case
    identity = EngineIdentity()
    app = create_app(c.paths, identity)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        yield SimpleNamespace(case=c, app=app, client=client, identity=identity,
                              base=f"/api/v1/datasets/{c.identifier}",
                              sessions=app.state.annotation_sessions,
                              engine=app.state.superpixel_engine)


def segment(h, **changes):
    params = {"n_segments": 24, "compactness": .5, "pca_components": 5, **changes}
    response = h.client.post(h.base+"/superpixels", json=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def ready_http(http_annotation):
    segment(http_annotation)
    return http_annotation


def state(h):
    return h.sessions._state(h.case.identifier)


def pixels(h):
    return h.sessions.working(h.case.identifier)["label_map"]


def region(h, *, action="confirm", label="PE", geometry=None):
    body = {"action": action, "geometry": geometry or {"superpixels": [int(state(h).segments[0, 0])]}}
    if label is not None:
        body["label_id"] = h.case.labels[label]
    return h.client.post(h.base+"/annotations/regions", json=body)


def decode_png(overlay):
    image = Image.open(BytesIO(base64.b64decode(overlay["png_base64"])))
    assert image.format == "PNG" and max(image.size) <= 512
    assert image.size == (overlay["width"], overlay["height"])
    return np.asarray(image)


def test_working_empty_versions_empty_and_single_registry_assembly(http_annotation):
    h = http_annotation
    response = h.client.get(h.base+"/annotations/working")
    assert response.status_code == 200
    assert response.json() == {"superpixel_count": 0, "params": None, "statistics": {}, "overlay": None}
    listing = h.client.get(h.base+"/annotations").json()
    assert listing == {"versions": [], "working": response.json()}
    assert h.app.state.diffusion_engine.superpixels is h.engine
    assert h.app.state.diffusion_engine.sessions is h.sessions
    assert h.engine.registry is h.sessions.registry


def test_superpixels_generate_then_sync_before_response_initializes_state(http_annotation, monkeypatch):
    h = http_annotation
    assert h.sessions._states == {}
    events = []
    original_generate, original_sync = h.engine.generate, h.sessions.set_segmentation
    def generate(*args, **kwargs):
        result = original_generate(*args, **kwargs)
        events.append("generated")
        assert h.sessions._states == {}
        return result
    def sync(identifier, result):
        assert events == ["generated"]
        assert h.engine.cache[str(identifier)][1] is result
        original_sync(identifier, result)
        events.append("synced")
    monkeypatch.setattr(h.engine, "generate", generate)
    monkeypatch.setattr(h.sessions, "set_segmentation", sync)
    report = segment(h)
    assert events == ["generated", "synced"]
    assert state(h).params == report["params"]
    np.testing.assert_array_equal(state(h).segments, h.engine.cache[h.case.identifier][1].segments)
    working = h.client.get(h.base+"/annotations/working").json()
    assert working["superpixel_count"] == report["superpixel_count"]
    decode_png(working["overlay"])


@pytest.mark.parametrize("seed", [{"point": [0, 0]}, {"box": [0, 5, 0, 4]}, {"doodle": [[0, 0], [4, 3]]}])
def test_diffuse_three_prompts_response_cos_s_queue_effective_defaults(ready_http, seed):
    h = ready_http
    response = h.client.post(h.base+"/diffuse", json={"seed": seed})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["params"] == {"threshold": .92, "queue_min_similarity": .80}
    assert len(result["candidates"]) == 1 and result["candidates"][0] == result["candidate"]
    candidate = result["candidate"]
    assert len(candidate["cos_s"]) == len(h.engine.cache[h.case.identifier][1].mean_spectra)
    assert all(candidate["cos_s"][i] == 1 for i in candidate["seed_superpixels"])
    assert candidate["pixel_count"] == int(np.isin(state(h).segments, candidate["superpixels"]).sum())
    assert candidate["min_similarity"] == min(candidate["cos_s"][i] for i in candidate["superpixels"])
    decode_png(candidate["overlay"])
    assert result["not_queued_reasons"]["below_queue_min_similarity"] == int(not result["enqueued"])
    assert len(result["queue"]) == int(result["enqueued"])
    assert np.all(pixels(h) == -1)


@pytest.mark.parametrize("action,label,expected", [("confirm", "PP", 3), ("erase", None, -1), ("uncertain", None, -2)])
def test_regions_superpixel_actions_working_statistics_registered_colors(ready_http, action, label, expected):
    h = ready_http
    assert region(h).status_code == 200
    mask = state(h).segments == int(state(h).segments[0, 0])
    response = region(h, action=action, label=label)
    assert response.status_code == 200, response.text
    working = response.json()
    assert np.all(pixels(h)[mask] == expected) and np.all(pixels(h)[~mask] == -1)
    assert working["statistics"]["labeled_pixels"] == (int(mask.sum()) if expected >= 0 else 0)
    assert working["statistics"]["uncertain_pixels"] == (int(mask.sum()) if expected == -2 else 0)
    assert sum(working["statistics"][key] for key in ("labeled_percent", "uncertain_percent", "blank_percent")) == pytest.approx(100)
    image = decode_png(working["overlay"])
    if expected >= 0:
        with connect_database(h.case.paths.database) as db:
            color = db.execute("SELECT color_hex FROM label WHERE id=?", (h.case.labels[label],)).fetchone()[0]
        assert np.all(image[mask] == ImageColor.getrgb(color))
    if expected == -2:
        assert image[mask].max() < np.iinfo(np.uint8).max
    assert "label_map" not in working  # Working map remains sidecar-owned.


@pytest.mark.parametrize("vertices,expected", [
    ([[0, 0], [0, 2], [2, 2], [2, 0]], [[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]),
    ([[.5, .5], [.5, 2.5], [2.5, 2.5], [2.5, .5]], [[1, 1, 1, 0], [1, 1, 1, 0], [1, 1, 1, 0], [0, 0, 0, 0]]),
    ([[0, 0], [4, 4], [0, 4], [4, 0]], [[1, 0, 0, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 0, 0, 1]]),
])
def test_polygon_centres_even_odd_boundary_included_no_dilation(ready_http, vertices, expected):
    h = ready_http
    response = region(h, geometry={"polygon": vertices})
    assert response.status_code == 200, response.text
    wanted = np.full(pixels(h).shape, -1, dtype=np.int32)
    wanted[:4, :4][np.array(expected, dtype=bool)] = 1
    np.testing.assert_array_equal(pixels(h), wanted)


def test_polygon_after_superpixels_overwrites_only_selected_centres(ready_http):
    h = ready_http
    assert region(h).status_code == 200
    before = pixels(h)
    polygon = [[0, 0], [0, 2], [2, 2], [2, 0]]
    assert region(h, label="PET", geometry={"polygon": polygon}).status_code == 200
    expected = before.copy()
    expected[:2, :2] = 2
    np.testing.assert_array_equal(pixels(h), expected)


def test_five_http_undos_empty_409_then_edit_stays_aligned(ready_http):
    h = ready_http
    history = []
    for index in range(6):
        history.append(pixels(h))
        polygon = [[index, 0], [index, 1], [index+1, 1], [index+1, 0]]
        assert region(h, action="uncertain" if index % 2 else "confirm", geometry={"polygon": polygon}).status_code == 200
    for expected in reversed(history[1:]):
        response = h.client.post(h.base+"/annotations/undo")
        assert response.status_code == 200
        np.testing.assert_array_equal(pixels(h), expected)
        assert response.json()["statistics"]["labeled_pixels"] == np.count_nonzero(expected >= 0)
        assert response.json()["statistics"]["uncertain_pixels"] == np.count_nonzero(expected == -2)
    empty = h.client.post(h.base+"/annotations/undo")
    assert empty.status_code == 409 and empty.json()["error"] == "ANNOTATION_CONFLICT"
    restored = pixels(h)
    assert region(h, label="PP").status_code == 200
    assert h.client.post(h.base+"/annotations/undo").status_code == 200
    np.testing.assert_array_equal(pixels(h), restored)


@pytest.mark.parametrize("action", ["confirm", "uncertain", "erase"])
def test_http_candidate_consumption_and_pending_union(ready_http, action):
    h = ready_http
    for _ in range(2):
        result = h.client.post(h.base+"/diffuse", json={"seed": {"point": [0, 0]}}).json()
        assert result["enqueued"]
    selected = np.isin(state(h).segments, result["candidate"]["superpixels"])
    queue = deepcopy(state(h).candidates)
    assert h.client.get(h.base+"/annotations/working").json()["statistics"]["pending_pixels"] == int(selected.sum())
    assert region(h, action=action, label="PE" if action == "confirm" else None,
                  geometry={"superpixels": result["candidate"]["superpixels"]}).status_code == 200
    if action == "erase":
        assert state(h).candidates == queue
        assert h.client.get(h.base+"/annotations/working").json()["statistics"]["pending_pixels"] == int(selected.sum())
    else:
        assert state(h).candidates == []
        assert h.client.get(h.base+"/annotations/working").json()["statistics"]["pending_pixels"] == 0


@pytest.mark.parametrize("field,value", [("n_segments", 32), ("compactness", 1), ("pca_components", 3)])
def test_http_resegment_clears_queue_preserves_labels_uncertain_and_statistics(ready_http, field, value):
    h = ready_http
    assert region(h).status_code == 200
    last = int(state(h).segments[-1, -1])
    assert region(h, action="uncertain", label=None, geometry={"superpixels": [last]}).status_code == 200
    assert h.client.post(h.base+"/diffuse", json={"seed": {"point": [0, 0]}}).json()["enqueued"]
    before = pixels(h)
    before_stats = h.client.get(h.base+"/annotations/working").json()["statistics"]
    report = segment(h, **{field: value})
    after = h.client.get(h.base+"/annotations/working").json()
    np.testing.assert_array_equal(pixels(h), before)
    for key in ("labeled_pixels", "uncertain_pixels", "blank_pixels", "label_counts"):
        assert before_stats[key] == after["statistics"][key]
    assert after["statistics"]["pending_pixels"] == 0
    assert after["params"] == report["params"]


@pytest.mark.parametrize("endpoint,body", [
    ("/diffuse", {"seed": {"point": [0, 0]}}),
    ("/annotations/regions", {"action": "uncertain", "geometry": {"superpixels": [0]}}),
    ("/annotations/validate", None), ("/annotations/save", {}),
])
def test_segmentation_stale_four_routes_409_no_silent_sync(ready_http, endpoint, body):
    h = ready_http
    state(h).params["compactness"] = 2
    before = pixels(h)
    response = h.client.post(h.base+endpoint, **({"json": body} if body is not None else {}))
    assert response.status_code == 409 and response.json()["error"] == "SEGMENTATION_STALE"
    assert state(h).params["compactness"] == 2
    np.testing.assert_array_equal(pixels(h), before)
    # Working remains available during a mismatch.
    assert h.client.get(h.base+"/annotations/working").status_code == 200


def test_cache_params_stale_detected_and_superpixels_resynchronizes(ready_http):
    h = ready_http
    cached, result = h.engine.cache[h.case.identifier]
    h.engine.cache[h.case.identifier] = (replace(cached, compactness=2), result)
    response = h.client.post(h.base+"/annotations/validate")
    assert response.status_code == 409 and response.json()["error"] == "SEGMENTATION_STALE"
    segment(h)
    assert h.client.post(h.base+"/annotations/validate").status_code == 200


def test_validate_save_list_uuid_overlay_note_overwrite_and_old_version(ready_http, monkeypatch):
    h = ready_http
    assert region(h).status_code == 200
    assert region(h, action="uncertain", label=None,
                  geometry={"superpixels": [int(state(h).segments[-1, -1])]}).status_code == 200
    quality = h.client.post(h.base+"/annotations/validate")
    assert quality.status_code == 200
    assert set(quality.json()["not_applicable"]) == {"标签与聚类中心冲突", "类间重叠"}
    first = h.client.post(h.base+"/annotations/save", json={})
    assert first.status_code == 200, first.text
    first = first.json()
    assert first["note"] is None
    assert "version_no" not in first  # R20: display numbers belong to the version list.
    frozen = pixels(h)
    first_overlay = h.client.get(h.base+f"/annotations/{first['id']}/overlay")
    assert first_overlay.status_code == 200
    decode_png(first_overlay.json())
    second = h.client.post(h.base+"/annotations/save", json={"note": "人工复核"}).json()
    assert second["id"] != first["id"] and "version_no" not in second
    assert json.loads(second["note"])["event"] == "save"
    assert json.loads(second["note"])["text"] == "人工复核"
    assert region(h, label="PP").status_code == 200
    missing_confirm = h.client.post(h.base+"/annotations/save", json={"overwrite": True})
    assert missing_confirm.status_code == 409 and missing_confirm.json()["error"] == "ANNOTATION_CONFLICT"
    overwritten = h.client.post(h.base+"/annotations/save", json={"overwrite": True, "confirm": True, "note": "更正"}).json()
    assert overwritten["id"] == second["id"] and "version_no" not in overwritten
    assert overwritten["created_at"] == second["created_at"]
    assert json.loads(overwritten["note"])["event"] == "overwrite"
    assert json.loads(overwritten["note"])["text"] == "更正"
    listing = h.client.get(h.base+"/annotations").json()
    assert [record["version_no"] for record in listing["versions"]] == [2, 1]
    assert listing["working"]["statistics"] == h.client.get(h.base+"/annotations/working").json()["statistics"]
    assert listing["versions"][0]["note"]["event"] == "overwrite"
    np.testing.assert_array_equal(h.sessions.read_version(first["id"])["label_map"], frozen)
    assert h.client.get(h.base+f"/annotations/{first['id']}/overlay").json() == first_overlay.json()
    # UUID path must delegate to the existing snapshot reader (R20).
    calls = []
    original = h.sessions.read_version
    def read(version):
        calls.append(str(version))
        return original(version)
    monkeypatch.setattr(h.sessions, "read_version", read)
    assert h.client.get(h.base+f"/annotations/{second['id']}/overlay").status_code == 200
    assert calls == [second["id"]]
    unknown_version = str(uuid4())
    missing = h.client.get(h.base+f"/annotations/{unknown_version}/overlay")
    assert missing.status_code == 400 and missing.json()["error"] == "VERSION_NOT_FOUND"
    assert calls == [second["id"], unknown_version]
    with connect_database(h.case.paths.database) as db:
        assert db.execute("SELECT count(*) FROM annotation WHERE granularity!='sample' OR source!='manual'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM annotation WHERE granularity='scene'").fetchone()[0] == 0
        for version in (first, second):
            counts = db.execute("SELECT label_id,count(*) FROM sample_spectrum WHERE version_id=? GROUP BY label_id", (version["id"],)).fetchall()
            assert all(count == 1 for _, count in counts)


@pytest.mark.parametrize("confirm", [False, True])
def test_no_version_overwrite_http_409(ready_http, confirm):
    h = ready_http
    response = h.client.post(h.base+"/annotations/save", json={"overwrite": True, "confirm": confirm})
    assert response.status_code == 409 and response.json()["error"] == "ANNOTATION_CONFLICT"


def test_note_2000_boundary_request_and_application_layer_double_validation(ready_http):
    h = ready_http
    response = h.client.post(h.base+"/annotations/save", json={"note": "注"*2000})
    assert response.status_code == 200
    assert len(json.loads(response.json()["note"])["text"]) == 2000
    too_long = h.client.post(h.base+"/annotations/save", json={"note": "注"*2001})
    assert too_long.status_code == 400 and too_long.json()["error"] == "INVALID_VERSION_NOTE"
    with pytest.raises(DataError) as error:
        h.sessions.save(h.case.identifier, note="注"*2001)
    assert error.value.code == "INVALID_VERSION_NOTE"
    without_text = h.client.post(h.base+"/annotations/save", json={"overwrite": True, "confirm": True}).json()
    assert set(json.loads(without_text["note"])) == {"event", "at"}
    empty_text = h.client.post(h.base+"/annotations/save", json={"note": ""}).json()
    assert json.loads(empty_text["note"])["text"] == ""


@pytest.mark.parametrize("endpoint,body", [
    ("/diffuse", {"seed": {"point": [0, 0]}, "extra": 1}),
    ("/diffuse", {"seed": {"point": [0, 0], "box": [0, 1, 0, 1]}}),
    ("/diffuse", {"seed": {"point": [0, 999]}}),
    ("/annotations/regions", {"action": "confirm", "geometry": {"superpixels": [0]}}),
    ("/annotations/regions", {"action": "uncertain", "geometry": {"superpixels": [0], "polygon": [[0, 0], [0, 1], [1, 1]]}}),
    ("/annotations/regions", {"action": "uncertain", "geometry": {"superpixels": [999999]}}),
    ("/annotations/regions", {"action": "uncertain", "geometry": {"polygon": [[0, 0], [0, 1]]}}),
    ("/annotations/regions", {"action": "uncertain", "geometry": {"polygon": [[0, 0], [0, 1], [1, 1]], "dilate": 1}}),
    ("/annotations/save", {"version_no": 1}), ("/annotations/save", {"overwrite": "true"}),
])
def test_bad_bodies_geometry_mixed_geometry_400_no_side_effect(ready_http, endpoint, body):
    h = ready_http
    before = pixels(h)
    response = h.client.post(h.base+endpoint, json=body)
    assert response.status_code == 400, response.text
    assert {"error", "detail", "context"} <= response.json().keys()
    np.testing.assert_array_equal(pixels(h), before)


def test_validation_has_no_body_and_uuid_only_version_errors(ready_http):
    h = ready_http
    assert h.client.post(h.base+"/annotations/validate", json={}).status_code == 400
    unknown = h.client.get(h.base+f"/annotations/{uuid4()}/overlay")
    assert unknown.status_code == 400 and unknown.json()["error"] == "VERSION_NOT_FOUND"
    for value in ("not-a-uuid", "1"):
        malformed = h.client.get(h.base+f"/annotations/{value}/overlay")
        assert malformed.status_code == 400 and malformed.json()["error"] == "INVALID_REQUEST"
    saved = h.client.post(h.base+"/annotations/save", json={}).json()
    other = str(h.engine.registry.import_path(str(h.case.header), raw=False).datasets[0].id)
    wrong_cube = h.client.get(f"/api/v1/datasets/{other}/annotations/{saved['id']}/overlay")
    assert wrong_cube.status_code == 404 and wrong_cube.json()["error"] == "VERSION_NOT_FOUND"


def test_http_error_envelopes_identity_and_source_changed(ready_http):
    h = ready_http
    unknown = h.client.get(f"/api/v1/datasets/{uuid4()}/annotations/working")
    assert unknown.status_code == 404 and unknown.json()["error"] == "DATASET_NOT_FOUND"
    h.case.header.unlink()
    for endpoint, body in (("/diffuse", {"seed": {"point": [0, 0]}}), ("/annotations/validate", None), ("/annotations/save", {})):
        response = h.client.post(h.base+endpoint, **({"json": body} if body is not None else {}))
        assert response.status_code == 400 and response.json()["error"] == "SOURCE_CHANGED"
        assert response.headers["X-SpectrumAgent-Boot-Id"] == h.identity.boot_id
        assert response.headers["X-SpectrumAgent-Pid"] == str(h.identity.pid)
    h.client.headers.pop("Authorization")
    unauthorized = h.client.get(h.base+"/annotations/working")
    assert unauthorized.status_code == 401
    assert "X-SpectrumAgent-Boot-Id" not in unauthorized.headers


def test_missing_superpixels_http_structured_and_empty_undo_409(http_annotation):
    h = http_annotation
    for endpoint, body in (("/diffuse", {"seed": {"point": [0, 0]}}), ("/annotations/save", {}), ("/annotations/validate", None)):
        response = h.client.post(h.base+endpoint, **({"json": body} if body is not None else {}))
        assert response.status_code == 400 and response.json()["error"] == "SUPERPIXELS_REQUIRED"
    empty = h.client.post(h.base+"/annotations/undo")
    assert empty.status_code == 409 and empty.json()["error"] == "ANNOTATION_CONFLICT"
