import base64
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from backend.database import connect_database
from spectrumagent.annotation.engines.diffusion import (
    DiffusionEngine, adjacency_edges, bresenham, grow, prompt_superpixels,
)
from spectrumagent.annotation.engines.superpixels import Parameters, SuperpixelEngine
from spectrumagent.annotation.session import SessionStore
from spectrumagent.data import DataError, SpectrumDataSet


def angle_spectra(angles):
    """Analytic ORIGINAL-band unit vectors; no PCA input to the growth test."""
    spectra = np.zeros((len(angles), 200), dtype=np.float64)
    radians = np.deg2rad(angles)
    spectra[:, 0], spectra[:, 1] = np.cos(radians), np.sin(radians)
    return spectra


def segmentation(labels, angles):
    labels = np.asarray(labels, dtype=np.int32)
    return SimpleNamespace(segments=labels, mean_spectra=angle_spectra(angles),
                           features=SimpleNamespace(normalized=np.full((*labels.shape, 5), .25, dtype=np.float32)))


@pytest.fixture
def seam(annotation_case):
    c = annotation_case
    engine = SuperpixelEngine(c.registry)
    result = SimpleNamespace(segments=c.segments,
                             mean_spectra=np.array([c.values[c.segments == i].mean(axis=0) for i in range(6)]),
                             features=SimpleNamespace(normalized=np.zeros((*c.segments.shape, 5), dtype=np.float32)),
                             report={"params": c.params})
    engine.cache[c.identifier] = (Parameters(), result)
    return c, engine, result, DiffusionEngine(engine, c.store)


def test_four_neighbour_graph_deduplicates_shared_edges_excludes_corners():
    labels = np.array([[0, 1], [2, 3]], dtype=np.int32)
    assert adjacency_edges(labels).tolist() == [[0, 1], [0, 2], [1, 3], [2, 3]]
    assert adjacency_edges(np.repeat(np.repeat(labels, 3, axis=0), 4, axis=1)).tolist() == adjacency_edges(labels).tolist()
    result = grow(segmentation(labels, [0, 90, 90, 0]), {"point": [0, 0]})
    assert result["superpixels"] == [0]  # Similar diagonal-only block cannot be reached.


def test_single_linkage_growth_cos_uv_report_cos_s_drift_default_reproducible():
    data = segmentation([[0, 1, 2, 3]], [0, 20, 40, 60])
    first = grow(data, {"point": [0, 0]})
    second = grow(data, {"point": [0, 0]}, threshold=.92)
    assert first == second
    assert first["superpixels"] == [0, 1, 2, 3]
    assert first["cos_s"][0] == 1
    np.testing.assert_allclose(first["cos_s"], np.cos(np.deg2rad([0, 20, 40, 60])), atol=1e-15)
    assert first["min_similarity"] == pytest.approx(.5)
    assert first["avg_similarity"] == pytest.approx(np.cos(np.deg2rad([0, 20, 40, 60])).mean())
    assert first["min_similarity"] < .80 < .92  # Guard must be reachable at default growth threshold.
    assert grow(data, {"point": [0, 0]}, threshold=.95)["superpixels"] == [0]


@pytest.mark.parametrize("seed", [
    {"box": [0, 1, 0, 4]}, {"doodle": [[0, 0], [0, 3]]},
    {"pixels": [[0, 0], [0, 3], [0, 3]]}, {"superpixels": [1, 0, 1]},
])
def test_composite_one_candidate_pixel_weighted_seed_seed_members_defined_one(seed):
    data = segmentation([[0, 0, 0, 1, 2]], [0, 60, 20])
    result = grow(data, seed, threshold=1)
    assert result["seed_superpixels"] == result["superpixels"] == [0, 1]
    assert result["pixel_count"] == 4
    assert result["cos_s"][:2] == [1., 1.]
    assert result["min_similarity"] == result["avg_similarity"] == 1
    seed_mean = (3*data.mean_spectra[0] + data.mean_spectra[1])/4
    expected = np.dot(seed_mean, data.mean_spectra[2])/np.linalg.norm(seed_mean)
    assert result["cos_s"][2] == pytest.approx(expected, abs=1e-15)
    equal_superpixel_mean = (data.mean_spectra[0]+data.mean_spectra[1])/2
    wrong = np.dot(equal_superpixel_mean, data.mean_spectra[2])/np.linalg.norm(equal_superpixel_mean)
    assert result["cos_s"][2] != pytest.approx(wrong, abs=1e-15)


def test_doodle_bresenham_fills_intermediate_pixels_one_pixel_wide():
    expected = [(0, 0), (0, 1), (1, 2), (1, 3), (2, 4), (2, 5)]
    assert list(bresenham((0, 0), (2, 5))) == expected
    labels = np.arange(18, dtype=np.int32).reshape(3, 6)
    assert prompt_superpixels(labels, {"doodle": [[0, 0], [2, 5]]}) == [int(labels[p]) for p in expected]
    assert list(bresenham((2, 5), (0, 0))) == expected[::-1]
    assert list(bresenham((1, 2), (1, 2))) == [(1, 2)]
    assert list(bresenham((0, 2), (2, 2))) == [(0, 2), (1, 2), (2, 2)]
    assert prompt_superpixels(labels, {"pixels": [[0, 0], [2, 5]]}) == [0, 17]


def test_box_half_open_hits_all_covered_superpixels_and_all_three_prompts_work():
    labels = np.arange(9, dtype=np.int32).reshape(3, 3)
    assert prompt_superpixels(labels, {"box": [0, 2, 0, 2]}) == [0, 1, 3, 4]
    assert prompt_superpixels(labels, {"box": [1, 3, 1, 3]}) == [4, 5, 7, 8]
    data = segmentation(labels, [0]*9)
    for seed in ({"point": [1, 1]}, {"box": [0, 2, 0, 2]}, {"doodle": [[0, 0], [2, 2]]}):
        assert grow(data, seed)["superpixels"] == list(range(9))


def test_original_means_only_pca_changes_do_not_change_spectral_result():
    data = segmentation([[0, 1, 2, 3]], [0, 20, 40, 60])
    first = grow(data, {"point": [0, 0]})
    data.features.normalized = np.random.default_rng(0).random((1, 4, 5), dtype=np.float32)
    second = grow(data, {"point": [0, 0]})
    for key in ("superpixels", "pixel_count", "cos_s", "min_similarity", "avg_similarity"):
        assert first[key] == second[key]


def test_candidate_png_side_limit_and_pixel_count():
    labels = np.zeros((701, 1003), dtype=np.int32)
    result = grow(segmentation(labels, [0]), {"point": [700, 1002]})
    assert result["pixel_count"] == labels.size
    overlay = result["overlay"]
    image = Image.open(BytesIO(base64.b64decode(overlay["png_base64"])))
    assert image.format == "PNG" and max(image.size) <= 512
    assert image.size == (overlay["width"], overlay["height"])


@pytest.mark.parametrize("seed", [{}, {"point": [0, 0], "box": [0, 1, 0, 1]},
                                  {"point": [-1, 0]}, {"point": [.5, 0]},
                                  {"box": [0, 0, 0, 1]}, {"doodle": []},
                                  {"superpixels": [99]}, {"pixels": [[0, 100]]}])
def test_bad_prompt_structured_no_candidate(seed):
    with pytest.raises(DataError) as error:
        grow(segmentation([[0]], [0]), seed)
    assert error.value.code == "INVALID_DIFFUSION_PROMPT"
    assert error.value.as_dict()["context"]["fields"][0]["field"] == "seed"


@pytest.mark.parametrize("field,value", [("threshold", float("nan")), ("threshold", 2),
                                        ("queue_min_similarity", True), ("queue_min_similarity", -2)])
def test_threshold_validation_is_independent_and_structured(seam, field, value):
    c, _, _, engine = seam
    with pytest.raises(DataError) as error:
        engine.generate(c.identifier, {"point": [0, 0]}, **{field: value})
    assert error.value.code == "INVALID_DIFFUSION_PARAMETERS"
    assert c.store._state(c.identifier).candidates == []


def test_queue_guard_default_active_separate_from_growth_no_auto_labels(seam):
    c, _, data, engine = seam
    data.mean_spectra = angle_spectra([0, 20, 40, 20, 40, 60])
    before = c.store.working(c.identifier)["label_map"]
    rejected = engine.generate(c.identifier, {"point": [0, 0]})
    assert not rejected["enqueued"] and rejected["candidates"] == []
    assert rejected["not_queued_reasons"] == {"below_queue_min_similarity": 1}
    assert rejected["candidate"]["superpixels"] == list(range(6))
    assert rejected["candidate"]["min_similarity"] == pytest.approx(.5)
    assert c.store.working(c.identifier)["statistics"]["pending_pixels"] == 0
    accepted = engine.generate(c.identifier, {"point": [0, 0]}, queue_min_similarity=.4)
    assert accepted["enqueued"] and len(accepted["candidates"]) == 1
    assert accepted["candidate"] == rejected["candidate"]
    assert accepted["not_queued_reasons"] == {"below_queue_min_similarity": 0}
    # Changing only the diffusion threshold does not fork/clear the queue.
    third = engine.generate(c.identifier, {"point": [0, 0]}, threshold=.95)
    assert third["enqueued"] and len(third["candidates"]) == 2
    np.testing.assert_array_equal(c.store.working(c.identifier)["label_map"], before)
    with connect_database(c.paths.database) as db:
        for table in ("annotation", "annotation_version", "sample_spectrum"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert not c.paths.snapshots.exists()


@pytest.mark.parametrize("action", ["confirm", "uncertain"])
def test_existing_session_consumes_confirm_uncertain_candidate(seam, action):
    c, _, _, engine = seam
    result = engine.generate(c.identifier, {"point": [0, 0]})
    assert result["enqueued"]
    selected = np.isin(c.segments, result["candidate"]["superpixels"])
    c.store.edit(c.identifier, selected, action=action, label_id=c.labels["PE"])
    working = c.store.working(c.identifier)
    assert working["statistics"]["pending_pixels"] == 0
    assert c.store._state(c.identifier).candidates == []
    assert np.all(working["label_map"][selected] == (1 if action == "confirm" else -2))


def test_existing_erase_does_not_consume_queue_pending_is_pixel_union(seam):
    c, _, _, engine = seam
    first = engine.generate(c.identifier, {"point": [0, 0]}, threshold=1)
    engine.generate(c.identifier, {"point": [0, 0]}, threshold=1)
    third = engine.generate(c.identifier, {"point": [0, 9]}, threshold=1)
    union = np.isin(c.segments, first["candidate"]["superpixels"]+third["candidate"]["superpixels"])
    queue = deepcopy(c.store._state(c.identifier).candidates)
    assert c.store.working(c.identifier)["statistics"]["pending_pixels"] == int(union.sum())
    c.store.edit(c.identifier, union, action="erase")
    assert c.store._state(c.identifier).candidates == queue
    assert c.store.working(c.identifier)["statistics"]["pending_pixels"] == int(union.sum())


@pytest.mark.parametrize("field,value", [("n_segments", 400), ("compactness", 1), ("pca_components", 3)])
def test_existing_parameter_change_clears_single_queue_preserves_pixel_states(seam, field, value):
    c, _, data, engine = seam
    c.store.edit(c.identifier, c.segments == 0, action="confirm", label_id=c.labels["PE"])
    c.store.edit(c.identifier, c.segments == 5, action="uncertain")
    engine.generate(c.identifier, {"point": [0, 5]})
    before = c.store.working(c.identifier)
    assert before["statistics"]["pending_pixels"] > 0
    changed = SimpleNamespace(segments=data.segments, report={"params": {**c.params, field: value}})
    c.store.set_segmentation(c.identifier, changed)
    after = c.store.working(c.identifier)
    np.testing.assert_array_equal(before["label_map"], after["label_map"])
    for key in ("labeled_pixels", "uncertain_pixels", "blank_pixels", "label_counts"):
        assert before["statistics"][key] == after["statistics"][key]
    assert after["statistics"]["pending_pixels"] == 0


def test_queue_owned_by_session_cube_isolation_new_session_empty_response_copies(seam):
    c, superpixels, data, engine = seam
    other = str(c.registry.import_path(str(c.header), raw=False).datasets[0].id)
    superpixels.cache[other] = (Parameters(), data)
    first = engine.generate(c.identifier, {"point": [0, 0]}, threshold=1)
    first["candidate"]["superpixels"].clear()
    first["candidates"][0]["superpixels"].clear()
    assert c.store.working(c.identifier)["statistics"]["pending_pixels"] > 0
    separate = engine.generate(other, {"point": [0, 9]}, threshold=1)
    assert len(separate["candidates"]) == 1
    same_session = DiffusionEngine(superpixels, c.store)
    again = same_session.generate(c.identifier, {"point": [0, 0]}, threshold=1)
    assert len(again["candidates"]) == 2  # No engine-owned second queue.
    new_session = SessionStore(c.registry, c.paths)
    assert new_session.working(c.identifier)["statistics"]["pending_pixels"] == 0
    assert new_session.working(other)["statistics"]["pending_pixels"] == 0


def test_cache_seam_reads_only_validated_resident_original_means(seam, monkeypatch):
    c, _, _, engine = seam
    original = c.registry.readable
    calls = []
    def checked(identifier, raw=None):
        assert raw is False
        calls.append(str(identifier))
        return original(identifier, raw=raw)
    monkeypatch.setattr(c.registry, "readable", checked)
    monkeypatch.setattr(SpectrumDataSet, "read_region", lambda *_: pytest.fail("resident means must be reused"))
    monkeypatch.setattr(SpectrumDataSet, "to_numpy", lambda *_: pytest.fail("full original cube"))
    assert engine.generate(c.identifier, {"point": [0, 0]})["enqueued"]
    assert calls == [c.identifier]


def test_missing_superpixels_structured_without_implicit_generation(seam, monkeypatch):
    c, superpixels, _, engine = seam
    superpixels.cache.clear()
    monkeypatch.setattr(superpixels, "generate", lambda *_: pytest.fail("implicit superpixel generation"))
    with pytest.raises(DataError) as error:
        engine.generate(c.identifier, {"point": [0, 0]})
    assert error.value.code == "SUPERPIXELS_REQUIRED"


def test_source_changed_and_unknown_id_preserve_registry_classification(seam):
    c, _, _, engine = seam
    engine.generate(c.identifier, {"point": [0, 0]})
    c.header.unlink()
    with pytest.raises(DataError) as error:
        engine.generate(c.identifier, {"point": [0, 0]})
    assert error.value.code == "SOURCE_CHANGED"
    with pytest.raises(DataError) as missing:
        engine.generate("missing", {"point": [0, 0]})
    assert missing.value.code == "DATASET_NOT_FOUND"
