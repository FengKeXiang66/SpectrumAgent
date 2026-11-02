"""TASK-13: PIL product checks, optional independent cv2 consumer checks."""
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.annotation import projection, projection_io
from spectrumagent.annotation.projection import ProjectionError, project
from spectrumagent.annotation.projection_io import configure_project, write_projection
from test_routes import http_annotation, ready_http


def generate(labels, mapping=None):
    return project(labels, {"0": "PE", "1": "PP"}, {"PE": "PE_W0", "PP": "PP_W1"} if mapping is None else mapping, rule_version=1)


def restore(text, shape):
    mask = np.zeros(shape, dtype=bool)
    for item in json.loads(text)["shapes"]:
        mask |= projection._rasterize(item["points"], shape)
    return mask


def rectangle():
    labels = np.full((282, 1945), -1, dtype=np.int32)
    labels[265:280, 1925:1943] = 0
    return labels


def lshape():
    labels = np.zeros((3, 5), dtype=np.int32)
    labels[:2, 3:] = -1
    return labels


def test_b1_rectangle_cv2_exact_270():
    cv2 = pytest.importorskip("cv2")
    labels = rectangle()
    text, _ = generate(labels)
    result = np.zeros(labels.shape, dtype=np.uint8)
    for item in json.loads(text)["shapes"]:
        cv2.fillPoly(result, [np.asarray(item["points"], dtype=np.int32)], 1)
    assert np.count_nonzero(result.astype(bool) != (labels == 0)) == 0
    assert int(result.sum()) == 270


def test_b2_concave_cv2_region_difference():
    cv2 = pytest.importorskip("cv2")
    labels = lshape()
    text, _ = generate(labels)
    result = np.zeros(labels.shape, dtype=np.uint8)
    for item in json.loads(text)["shapes"]:
        cv2.fillPoly(result, [np.asarray(item["points"], dtype=np.int32)], 1)
    assert np.count_nonzero(result.astype(bool) != (labels == 0)) <= max(2, int(np.ceil(.002 * np.count_nonzero(labels == 0))))


def test_rectangle_internal_pil_exact_and_all_points_integer():
    labels = rectangle()
    before = labels.copy()
    text, meta = generate(labels)
    assert int(restore(text, labels.shape).sum()) == 270
    np.testing.assert_array_equal(restore(text, labels.shape), labels == 0)
    np.testing.assert_array_equal(labels, before)
    assert meta["class_pixels"] == {"PE": 270}
    assert all(type(value) is int for item in json.loads(text)["shapes"] for point in item["points"] for value in point)


def test_b3_determinism_and_spatial_sort_independent_of_class_index():
    labels = np.full((20, 25), -1, dtype=np.int32)
    labels[1:4, 2:8] = 1
    labels[10:18, 15:22] = 0
    first, _ = generate(labels)
    second, _ = generate(labels.copy())
    assert first == second and sha256(first.encode()).hexdigest() == sha256(second.encode()).hexdigest()
    assert [shape["label"] for shape in json.loads(first)["shapes"]] == ["PP_W1", "PE_W0"]


def test_b4_hole_stays_empty_and_slot_cost_is_counted():
    labels = np.full((50, 70), -1, dtype=np.int32)
    labels[3:47, 3:67] = 0
    labels[17:24, 30:38] = -1
    text, meta = generate(labels)
    result = restore(text, labels.shape)
    assert not result[17:24, 30:38].any()
    assert meta["holes_bridged"] == 1 and meta["hole_boxes"] == [[17, 30, 23, 37]]
    assert meta["bridge_pixels"] == 14  # Nearest hole row 17 to outer row 3, inclusive ring pixels.
    assert np.count_nonzero(result != (labels == 0)) == meta["bridge_pixels"]
    assert not meta["simplified"]


def test_b5_uncertain_and_blank_never_become_shapes():
    labels = np.full((10, 20), -1, dtype=np.int32)
    labels[2:5, 7:12] = -2
    text, meta = generate(labels)
    assert json.loads(text)["shapes"] == []
    assert meta["uncertain_pixels"] == 15 and meta["uncertain_boxes"] == [[2, 7, 4, 11]]


def test_b6_lshape_axes_and_notch_exact():
    labels = lshape()
    text, _ = generate(labels)
    points = np.asarray(json.loads(text)["shapes"][0]["points"])
    assert np.ptp(points[:, 0]) + 1 == 5 and np.ptp(points[:, 1]) + 1 == 3
    result = restore(text, labels.shape)
    assert not result[:2, 3:5].any()
    np.testing.assert_array_equal(result, labels == 0)


@pytest.mark.parametrize("name", ["PE_W0", "PE_W0_2", "PS_HI", "PET_W1"])
def test_b7_external_name_is_verbatim_and_missing_mapping_is_reported(name):
    labels = np.zeros((4, 7), dtype=np.int32)
    text, _ = generate(labels, {"PE": name})
    assert json.loads(text)["shapes"][0]["label"] == name
    missing, meta = generate(labels, {})
    assert json.loads(missing)["shapes"] == [] and meta["unmapped"] == ["PE"]


def test_b8_exact_minimal_key_sets():
    text, _ = generate(lshape())
    value = json.loads(text)
    assert set(value) == {"version", "flags", "shapes"} and value["version"] == "5.4.1"
    assert set(value["shapes"][0]) == {"label", "points", "group_id", "shape_type", "flags"}
    assert " " not in text and "\n" not in text


def test_b9_entire_batch_rejects_a_bad_raster_with_diagnostics(monkeypatch):
    labels = np.full((30, 40), -1, dtype=np.int32)
    labels[1:4, 1:4] = 0
    labels[8:28, 10:38] = 1
    original = projection._rasterize
    def failed(points, shape):
        return np.zeros(shape, bool) if shape == (20, 28) else original(points, shape)
    monkeypatch.setattr(projection, "_rasterize", failed)
    with pytest.raises(ProjectionError) as error:
        generate(labels)
    for token in ("PP", "bbox=[8, 10, 27, 37]", "面积=560", "对称差=560", "上限=2"):
        assert token in str(error.value)


def test_more_than_5000_vertices_are_not_silently_simplified():
    labels = np.zeros((3, 2600), dtype=np.int32)
    text, meta = generate(labels)
    assert len(json.loads(text)["shapes"][0]["points"]) > 5000
    assert meta["simplified"] is False
    np.testing.assert_array_equal(restore(text, labels.shape), labels == 0)


def test_b10_save_failure_returns_success_version_and_export_error(annotation_case, monkeypatch, caplog):
    c = annotation_case
    def failed(*args, **kwargs):
        raise OSError("simulated projection IO error")
    monkeypatch.setattr(projection_io, "write_projection", failed)
    saved = c.store.save(c.identifier)
    assert saved["export"] == {"ok": False, "path": None, "error": "simulated projection IO error"}
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_version WHERE id=?", (saved["id"],)).fetchone()[0] == 1
    assert "JSON 投影失败" in caplog.text
    folder = c.paths.snapshots / saved["snapshot_ref"]
    assert {path.name for path in folder.iterdir()} == {"annotation.json", "label_map.npz", "label_index.json", "spectra.npz"}


def test_b11_export_layout_metadata_and_configurable_project_mapping(annotation_case):
    c = annotation_case
    configure_project(c.paths, c.project, {"PE": "PE_W0"})
    c.store.edit(c.identifier, c.segments == 0, action="confirm", label_id=c.labels["PE"])
    saved = c.store.save(c.identifier)
    assert saved["export"]["ok"] and saved["export"]["error"] is None
    path = Path(saved["export"]["path"])
    assert path == c.paths.exports / c.identifier / "sample.json" and path.is_absolute() and path.exists()
    assert json.loads(path.read_text("utf-8"))["shapes"][0]["label"] == "PE_W0"
    meta = json.loads(path.with_name("sample.meta.json").read_text("utf-8"))
    assert meta["cube_id"] == c.identifier and meta["source_hdr"] == str(c.header)
    assert meta["version_no"] == 1 and meta["shape_count"] == 1
    assert set(path.parent.iterdir()) == {path, path.with_name("sample.meta.json"), path.with_name("manifest.json")}
    assert not c.header.with_suffix(".json").exists() and not list(c.paths.exports.glob(".*.tmp"))


def test_filename_conflicts_custom_name_and_manifest_are_stable(annotation_case):
    c = annotation_case
    labels = np.zeros((3, 7), dtype=np.int32)
    first, _ = write_projection(c.paths, c.identifier, c.project, c.header, 1, labels, {"0": "PE"})
    other = str(uuid4())
    second, _ = write_projection(c.paths, other, c.project, c.header.parent / "other" / c.header.name, 1, labels, {"0": "PE"})
    assert Path(first).name == "sample.json" and Path(second).name == f"sample_{other[:8]}.json"
    again, _ = write_projection(c.paths, other, c.project, c.header.parent / "other" / c.header.name, 2, labels, {"0": "PE"})
    assert second == again
    configure_project(c.paths, c.project, {"PE": "PE_W0"}, filenames={other: "company.json"})
    custom, _ = write_projection(c.paths, other, c.project, c.header, 3, labels, {"0": "PE"})
    assert Path(custom).name == "company.json"
    assert not Path(second).exists() and not Path(second).with_suffix(".meta.json").exists()
    assert json.loads(Path(custom).with_name("manifest.json").read_text("utf-8"))["filename"] == "company.json"


def test_atomic_publish_failure_preserves_previous_generation(annotation_case, monkeypatch):
    c = annotation_case
    configure_project(c.paths, c.project, {"PE": "PE_W0"})
    labels = np.zeros((3, 7), dtype=np.int32)
    path, _ = write_projection(c.paths, c.identifier, c.project, c.header, 1, labels, {"0": "PE"})
    folder = Path(path).parent
    (folder / "existing-training.mat").write_bytes(b"untouched")
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    original = projection_io.os.replace
    injected = []
    def fail_publish(source, target):
        if Path(target).name == "sample.meta.json" and not injected:
            injected.append(True)
            raise OSError("publish failed")
        return original(source, target)
    monkeypatch.setattr(projection_io.os, "replace", fail_publish)
    with pytest.raises(OSError, match="publish failed"):
        changed = labels.copy()
        changed[0, 0] = -1
        write_projection(c.paths, c.identifier, c.project, c.header, 2, changed, {"0": "PE"})
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    assert not list(c.paths.exports.rglob(".*.tmp"))


def test_http_save_export_shape_warning_and_overwrite_retry(ready_http, monkeypatch):
    h = ready_http
    h.sessions.edit(h.case.identifier, h.sessions._state(h.case.identifier).segments == 0,
                    action="confirm", label_id=h.case.labels["PE"])
    saved = h.client.post(h.base + "/annotations/save", json={}).json()
    assert set(saved["export"]) == {"ok", "path", "error"}
    assert "png_base64" not in json.dumps(saved["export"]) and "segments_png" not in json.dumps(saved["export"])
    assert saved["export"]["ok"] and saved["export"]["error"] == "有 1 个类未配置对外名称"
    original = projection_io.write_projection
    monkeypatch.setattr(projection_io, "write_projection", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("retry me")))
    failed = h.client.post(h.base + "/annotations/save", json={"overwrite": True, "confirm": True}).json()
    assert failed["id"] == saved["id"] and not failed["export"]["ok"]
    monkeypatch.setattr(projection_io, "write_projection", original)
    configure_project(h.case.paths, h.case.project, {"PE": "PE_W0"})
    recovered = h.client.post(h.base + "/annotations/save", json={"overwrite": True, "confirm": True}).json()
    assert recovered["id"] == saved["id"] and recovered["export"]["ok"]
    assert len(h.client.get(h.base + "/annotations").json()["versions"]) == 1


def test_projection_io_has_no_spectra_read_or_source_write(annotation_case, monkeypatch):
    c = annotation_case
    from spectrumagent.data import SpectrumDataSet
    monkeypatch.setattr(SpectrumDataSet, "read_region", lambda *args: pytest.fail("projection read IMG"))
    path, _ = write_projection(c.paths, c.identifier, c.project, c.header, 1, np.zeros((2, 3), np.int32), {"0": "PE"})
    assert Path(path).is_relative_to(c.paths.exports)
