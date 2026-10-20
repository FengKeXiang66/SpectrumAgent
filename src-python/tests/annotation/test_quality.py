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
