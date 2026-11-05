import json
from pathlib import Path

import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.annotation.quality import DEFAULT_COSINE_THRESHOLD, validate
from spectrumagent.annotation.session import aggregate_spectra
from spectrumagent.data import DataError


def test_mixed_superpixels_partial_means_original_spectra_exclude_negative(annotation_case):
    c = annotation_case
    rows, cols = np.indices(c.segments.shape)
    c.store.edit(c.identifier, (c.segments == 0) | ((c.segments == 2) & (cols == 8)),
                 action="confirm", label_id=c.labels["PE"])
    c.store.edit(c.identifier, (c.segments == 2) & (cols == 9), action="confirm", label_id=c.labels["PET"])
    c.store.edit(c.identifier, (c.segments == 2) & (cols == 10), action="uncertain")
    # Remaining column11 is blank: neither blank nor uncertain may enter means.
    working = c.store.working(c.identifier)
    report = c.store.validate(c.identifier, threshold=.99)  # Explicit test threshold, not product default.
    comparisons = report["comparisons"]
    assert len(comparisons) == 3
    assert {(item["superpixel_id"], item["label_index"]) for item in comparisons} == {(0, 1), (2, 1), (2, 2)}
    for item in comparisons:
        label_mask = working["label_map"] == item["label_index"]
        part_mask = label_mask & (c.segments == item["superpixel_id"])
        left, right = c.values[part_mask].mean(axis=0), c.values[label_mask].mean(axis=0)
        expected = np.dot(left, right) / (np.linalg.norm(left)*np.linalg.norm(right))
        assert item["cos"] == pytest.approx(expected, abs=1e-12)
        assert item["pixel_count"] == int(part_mask.sum())
    assert any(item["superpixel_id"] == 2 and item["label_index"] == 1 for item in report["suspicious"])
    assert 0 < len(report["suspicious"]) < len(comparisons)
    assert report["completeness"]["labeled_pixels"] == 120
    assert report["completeness"]["uncertain_pixels"] == 20
    assert report["completeness"]["blank_pixels"] == 340
    assert sum(report["completeness"][key] for key in ("labeled_percent", "uncertain_percent", "blank_percent")) == pytest.approx(100)
    assert report["not_applicable"] == {"标签与聚类中心冲突": "无模型阶段不适用", "类间重叠": "无模型阶段不适用"}


def test_quality_recomputes_current_means_ignores_saved_sample_spectrum(annotation_case, monkeypatch):
    c = annotation_case
    c.store.edit(c.identifier, c.segments == 0, action="confirm", label_id=c.labels["PE"])
    saved = c.store.save(c.identifier)
    with connect_database(c.paths.database) as db:
        db.execute("UPDATE sample_spectrum SET mean_ref='not-a-real-key',std_ref='not-a-real-key'")
    monkeypatch.setattr(np, "load", lambda *_args, **_kwargs: pytest.fail("quality read historical spectra"))
    c.store.edit(c.identifier, c.segments == 2, action="confirm", label_id=c.labels["PE"])
    report = c.store.validate(c.identifier, threshold=.99)
    assert len(report["comparisons"]) == 2
    assert report["completeness"]["labeled_pixels"] == 160
    assert report["comparisons"][0]["cos"] < saved["quality"]["comparisons"][0]["cos"]


def test_high_variance_same_definition_as_engine_current_segments(annotation_case):
    c = annotation_case
    report = c.store.validate(c.identifier)
    expected = np.array([c.values[c.segments == i].std(axis=0).mean() for i in range(6)])
    np.testing.assert_allclose(report["high_variance"]["d_s"], expected, rtol=0, atol=1e-10)
    tau = 3*np.median(expected)
    assert report["high_variance"]["tau"] == pytest.approx(tau, abs=1e-10)
    assert report["high_variance"]["superpixel_ids"] == np.flatnonzero(expected > tau).tolist()
    assert report["comparisons"] == report["suspicious"] == []
    # Merge two spectrally different fixture blocks: current-segment d_s must
    # detect it, rather than returning cached/pre-refinement engine statistics.
    from types import SimpleNamespace
    remap = np.array([0, 0, 1, 2, 3, 4], dtype=np.int32)
    merged = remap[c.segments]
    c.store.set_segmentation(c.identifier, SimpleNamespace(segments=merged, report={"params": c.params}))
    updated = c.store.validate(c.identifier)
    expected = np.array([c.values[merged == i].std(axis=0).mean() for i in range(5)])
    np.testing.assert_allclose(updated["high_variance"]["d_s"], expected, rtol=0, atol=1e-10)
    assert updated["high_variance"]["superpixel_ids"] == [0]


def test_default_threshold_provenance_real_cube_synthetic_behavior_only():
    evidence = Path(__file__).parents[3] / "milestone04/evidence/10.3/quality-calibration.json"
    report = json.loads(evidence.read_text("utf-8"))
    assert DEFAULT_COSINE_THRESHOLD == report["default_threshold"] == report["quantiles"]["0.05"]
    assert report["shape"] == [231, 640, 200] and report["params"]["compactness"] == .5
    assert report["clustering"] == {"n_clusters": 4, "random_state": 0, "n_init": 10}
    assert 0 < report["triggered"] < report["comparisons"]
    assert report["implant"]["detected"] is True
    assert "不是人工标注" in report["purpose"] and "不是标注质量断言" in report["purpose"]


@pytest.mark.parametrize("threshold", [-2, 2, float("nan")])
def test_invalid_quality_threshold_structured(annotation_case, threshold):
    with pytest.raises(DataError) as error:
        annotation_case.store.validate(annotation_case.identifier, threshold=threshold)
    assert error.value.code == "INVALID_QUALITY_THRESHOLD"


def test_bounded_aggregation_constant_spectra_stable_population_std(annotation_case, monkeypatch):
    c = annotation_case
    working = np.ones(c.segments.shape, dtype=np.int32)
    # Arithmetic edge, not a fake quality result: bounded reader returns a constant.
    from spectrumagent.annotation import session
    def constant_blocks(dataset, block_size):
        assert block_size == 32
        for start, end in ((0, 32), (32, 40)):
            yield start, end, np.full((end-start, 12, 200), .5, dtype=np.float64)
    monkeypatch.setattr(session, "row_blocks", constant_blocks)
    result = aggregate_spectra(c.registry, c.identifier, working)
    np.testing.assert_array_equal(result.labels[1].mean, np.full(200, .5))
    np.testing.assert_array_equal(result.labels[1].std, np.zeros(200))


# TASK-28 additions: keep all existing tests, including the assertion at :53.
def _review_cube(case, values, name):
    header = case.header.parent / (name + ".hdr")
    header.with_suffix(".img").write_bytes(values.astype("<f8").transpose(0, 2, 1).tobytes())
    lines, samples, bands = values.shape
    header.write_text(
        f"ENVI\nsamples={samples}\nlines={lines}\nbands={bands}\ndata type=5\n"
        "interleave=bil\nbyte order=0\nreflectance scale factor=1\n", encoding="utf-8")
    return str(case.registry.import_path(str(header), raw=True).datasets[0].id)


from contextlib import contextmanager


@contextmanager
def _review_http(case, identifier=None, *, segmented=True):
    from dataclasses import asdict
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from backend.identity import EngineIdentity
    from spectrumagent.app import create_app
    from spectrumagent.annotation.engines.superpixels import Parameters

    identifier = identifier or case.identifier
    identity = EngineIdentity()
    app = create_app(case.paths, identity)
    if segmented:
        params = Parameters(**{key: case.params[key] for key in asdict(Parameters())})
        result = SimpleNamespace(segments=case.segments, report={"params": case.params})
        app.state.superpixel_engine.cache[identifier] = (params, result)
        app.state.annotation_sessions.set_segmentation(identifier, result)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        yield SimpleNamespace(client=client, app=app, identifier=identifier,
                              sessions=app.state.annotation_sessions,
                              base=f"/api/v1/datasets/{identifier}")


def _review_disk(case):
    with connect_database(case.paths.database) as db:
        tables = {table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                  for table in ("annotation_version", "sample_spectrum", "annotation_draft")}
    snapshots = [(path.relative_to(case.paths.snapshots).as_posix(),
                  path.read_bytes() if path.is_file() else None)
                 for path in sorted(case.paths.snapshots.rglob("*"))]
    return tables, snapshots


def test_review_curves(annotation_case, monkeypatch):
    from spectrumagent.annotation import quality
    c = annotation_case
    cols = np.indices(c.segments.shape)[1]
    c.store.edit(c.identifier, (c.segments == 0) | ((c.segments == 2) & (cols == 8)),
                 action="confirm", label_id=c.labels["PE"])
    c.store.edit(c.identifier, (c.segments == 2) & (cols == 9), action="confirm", label_id=c.labels["PET"])
    c.store.edit(c.identifier, (c.segments == 2) & (cols == 10), action="uncertain")
    label_map = c.store.working(c.identifier)["label_map"]
    aggregates = aggregate_spectra(c.registry, c.identifier, label_map, segments=c.segments)
    original_cosine, original_convert = quality.cosine, quality._json_safe
    calls, boundaries = [], []
    def cosine(left, right):
        assert isinstance(left, np.ndarray) and isinstance(right, np.ndarray)
        assert left.dtype == right.dtype == np.float64
        calls.append((left.copy(), right.copy()))
        return original_cosine(left, right)
    def boundary(value):
        if isinstance(value, dict) and "comparisons" in value:
            boundaries.append(value)
        return original_convert(value)
    monkeypatch.setattr(quality, "cosine", cosine)
    monkeypatch.setattr(quality, "_json_safe", boundary)
    report = c.store.validate(c.identifier, threshold=.99)
    assert len(boundaries) == 1
    assert len(report["comparisons"]) == len(aggregates.parts) == len(calls) == 3
    expected_order = sorted(aggregates.parts)
    assert [(item["superpixel_id"], item["label_index"]) for item in report["comparisons"]] == expected_order
    expected_suspicious = []
    for item, (left, right) in zip(report["comparisons"], calls):
        mask = (label_map == item["label_index"]) & (c.segments == item["superpixel_id"])
        expected_mean = c.values[mask].mean(axis=0)
        np.testing.assert_allclose(item["mean"], expected_mean, rtol=0, atol=1e-12)
        np.testing.assert_allclose(left, expected_mean, rtol=0, atol=1e-12)
        assert len(item["mean"]) == c.values.shape[2]
        expected_cos = float(np.clip(np.dot(left, right) / (np.linalg.norm(left)*np.linalg.norm(right)), -1, 1))
        assert item["cos"] == pytest.approx(expected_cos, abs=1e-12)
        assert set(item) == {"superpixel_id", "label_index", "pixel_count", "cos", "mean"}
        if expected_cos < .99:
            expected_suspicious.append((item["superpixel_id"], item["label_index"]))
    assert [(item["superpixel_id"], item["label_index"]) for item in report["suspicious"]] == expected_suspicious
    assert [item["label_index"] for item in report["references"]] == sorted(aggregates.labels)
    for reference in report["references"]:
        np.testing.assert_allclose(reference["mean"], c.values[label_map == reference["label_index"]].mean(axis=0),
                                   rtol=0, atol=1e-12)
    assert set(report) == {"threshold", "threshold_level", "reference", "suspicious", "comparisons",
                           "high_variance", "completeness", "not_applicable", "references"}


def test_review_http_erase(annotation_case):
    c = annotation_case
    with _review_http(c) as h:
        for block in (0, 2):
            edited = h.client.post(h.base + "/annotations/regions",
                                   json={"action": "confirm", "label_id": c.labels["PE"],
                                         "geometry": {"superpixels": [block]}})
            assert edited.status_code == 200, edited.text
        before = _review_disk(c)
        checked = h.client.post(h.base + "/annotations/validate")
        assert checked.status_code == 200, checked.text
        assert _review_disk(c) == before
        report = checked.json()
        assert len(report["comparisons"]) == 2
        saved = h.client.post(h.base + "/annotations/save", json={})
        assert saved.status_code == 200, saved.text
        assert saved.json()["quality"] == report
        before_erase = _review_disk(c)
        erased = h.client.post(h.base + "/annotations/regions",
                               json={"action": "erase", "geometry": {"superpixels": [0]}})
        assert erased.status_code == 200, erased.text
        after_erase = _review_disk(c)
        assert after_erase[0]["annotation_draft"] != before_erase[0]["annotation_draft"]
        assert after_erase[0]["annotation_version"] == before_erase[0]["annotation_version"]
        assert after_erase[0]["sample_spectrum"] == before_erase[0]["sample_spectrum"]
        assert after_erase[1] == before_erase[1]
        refreshed = h.client.post(h.base + "/annotations/validate")
        assert refreshed.status_code == 200, refreshed.text
        assert _review_disk(c) == after_erase
        refreshed = refreshed.json()
        assert len(refreshed["comparisons"]) == 1
        assert refreshed["comparisons"][0]["superpixel_id"] == 2
        assert refreshed["completeness"]["labeled_pixels"] == int((c.segments == 2).sum())
        assert erased.json()["statistics"] == refreshed["completeness"]
        np.testing.assert_allclose(refreshed["references"][0]["mean"],
                                   c.values[c.segments == 2].mean(axis=0), rtol=0, atol=1e-12)


@pytest.mark.parametrize("channel", ["validate", "save"])
def test_review_nan_guard(annotation_case, channel):
    c = annotation_case
    values = c.values.copy()
    values[0, 0, 7] = np.nan
    identifier = _review_cube(c, values, "nan")
    with _review_http(c, identifier) as h:
        h.sessions.edit(identifier, c.segments == 0, action="confirm", label_id=c.labels["PE"])
        before = _review_disk(c)
        response = h.client.post(h.base + "/annotations/" + channel, **({"json": {}} if channel == "save" else {}))
        assert response.status_code == 400, response.text
        assert response.json() == {"error": "NON_FINITE_SPECTRA",
                                   "detail": "超像素输入包含非有限光谱值", "context": {}}
        assert _review_disk(c) == before


def _review_boundary_payload():
    # Explicit output-contract injection; these are not cube spectra or Aggregates.
    item = {"superpixel_id": 0, "label_index": 1, "pixel_count": np.int64(8),
            "cos": np.float64(np.nan), "mean": np.array([.5, np.nan, np.inf, -np.inf])}
    suspicious = {"superpixel_id": 1, "label_index": 1, "pixel_count": 8,
                  "cos": .2, "mean": [.2, .3, .4, .5]}
    return {"threshold": .9, "threshold_level": "contract", "reference": "output boundary",
            "comparisons": [item, suspicious], "suspicious": [suspicious],
            "references": [{"label_index": np.int32(1), "mean": (np.nan, np.inf, -np.inf, .5)}],
            "high_variance": {"d_s": np.array([np.nan, np.inf, -np.inf, .1]), "tau": np.float64(np.inf),
                              "superpixel_ids": np.array([1], dtype=np.int32)},
            "completeness": {}, "not_applicable": {}}


def test_review_boundary_conversion():
    from spectrumagent.annotation.quality import _json_safe
    original = _review_boundary_payload()
    result = _json_safe(original)
    json.dumps(result, allow_nan=False)
    assert result["comparisons"][0]["cos"] is None
    assert result["comparisons"][0]["mean"] == [.5, None, None, None]
    assert result["references"][0]["mean"] == [None, None, None, .5]
    assert result["high_variance"]["d_s"] == [None, None, None, .1]
    assert result["high_variance"]["tau"] is None
    assert result["high_variance"]["superpixel_ids"] == [1]
    assert [item["superpixel_id"] for item in result["suspicious"]] == [1]
    assert np.isnan(original["comparisons"][0]["cos"])
    assert np.isinf(original["comparisons"][0]["mean"][2])


def test_review_boundary_http(annotation_case, monkeypatch):
    from spectrumagent.annotation.quality import _json_safe
    with _review_http(annotation_case) as h:
        # The permitted validate-route return-value contract test: no cube read.
        monkeypatch.setattr(h.sessions, "validate", lambda *_args, **_kwargs: _json_safe(_review_boundary_payload()))
        monkeypatch.setattr(h.sessions.registry, "readable",
                            lambda *_args, **_kwargs: pytest.fail("boundary contract must not read cube"))
        response = h.client.post(h.base + "/annotations/validate")
        assert response.status_code == 200, response.text
        result = json.loads(response.text, parse_constant=lambda value: pytest.fail("bare " + value))
        assert result == _json_safe(_review_boundary_payload())
        assert result["comparisons"][0]["cos"] is None
        assert result["comparisons"][0]["mean"] == [.5, None, None, None]
        assert result["references"][0]["mean"] == [None, None, None, .5]
        assert result["high_variance"] == {"d_s": [None, None, None, .1], "tau": None, "superpixel_ids": [1]}
        assert [item["superpixel_id"] for item in result["suspicious"]] == [1]


def test_review_bounded(annotation_case, monkeypatch):
    from spectrumagent.data import SpectrumDataSet
    c = annotation_case
    c.store.edit(c.identifier, c.segments == 0, action="confirm", label_id=c.labels["PE"])
    original = SpectrumDataSet.read_region
    reads = []
    def bounded(dataset, l0, l1, s0, s1):
        assert l1-l0 <= c.params["block_size"]
        assert dataset.metadata["value_mode"] == "reflectance"
        reads.append((l0, l1))
        return original(dataset, l0, l1, s0, s1)
    monkeypatch.setattr(SpectrumDataSet, "read_region", bounded)
    monkeypatch.setattr(SpectrumDataSet, "to_numpy", lambda *_args: pytest.fail("full cube"))
    report = c.store.validate(c.identifier)
    assert reads == [(0, 32), (32, 40)] * 2
    assert len(report["comparisons"]) == 1
    assert len(report["comparisons"][0]["mean"]) == 200


@pytest.mark.parametrize("n_segments", [200, 400])
def test_review_response_bytes(annotation_case, n_segments):
    c = annotation_case
    values = np.tile(c.values, (2, 4, 1))
    identifier = _review_cube(c, values, "size")
    with _review_http(c, identifier, segmented=False) as h:
        segmented = h.client.post(h.base + "/superpixels",
                                  json={"n_segments": n_segments, "compactness": .5, "pca_components": 5})
        assert segmented.status_code == 200, segmented.text
        count = segmented.json()["superpixel_count"]
        actual = np.unique(h.sessions._state(identifier).segments).tolist()
        assert len(actual) == count and count > 0
        edited = h.client.post(h.base + "/annotations/regions",
                               json={"action": "confirm", "label_id": c.labels["PE"],
                                     "geometry": {"superpixels": actual}})
        assert edited.status_code == 200, edited.text
        checked = h.client.post(h.base + "/annotations/validate")
        saved = h.client.post(h.base + "/annotations/save", json={})
        assert checked.status_code == saved.status_code == 200
        assert len(checked.json()["comparisons"]) == count
        assert saved.json()["quality"] == checked.json()
        sizes = {"requested_n_segments": n_segments, "actual_superpixel_count": count,
                 "comparison_count": len(checked.json()["comparisons"]), "bands": values.shape[2],
                 "cube_shape": list(values.shape), "validate_bytes": len(checked.content),
                 "save_bytes": len(saved.content), "limit_bytes": 8*1024*1024}
        print("TASK28_RESPONSE_BYTES " + json.dumps(sizes, sort_keys=True))
        assert sizes["validate_bytes"] <= sizes["limit_bytes"]
        assert sizes["save_bytes"] <= sizes["limit_bytes"]
