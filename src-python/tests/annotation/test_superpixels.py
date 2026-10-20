"""Real SLIC/IPCA and bounded I/O; fixtures and basetemp stay on E:."""
import base64
import importlib.util
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from backend.database import connect_database
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.annotation.engines.superpixels import (
    Parameters, SuperpixelEngine, boundary_ratio, pca_features, refine,
)
from spectrumagent.data import DataError, SpectrumDataSet


@pytest.fixture
def source(tmp_path):
    rng = np.random.default_rng(0)
    values = rng.integers(1000, 4000, size=(40, 48, 6), dtype=np.uint16)
    values[:, 16:32, :3] += 16000
    values[:, 32:, 3:] += 32000
    data = tmp_path / "cube.img"
    data.write_bytes(values.transpose(0, 2, 1).tobytes())
    header = tmp_path / "cube.hdr"
    header.write_text("ENVI\nsamples=48\nlines=40\nbands=6\ndata type=12\ninterleave=bil\nbyte order=0\nreflectance scale factor=65535\n", "utf-8")
    registry = DatasetRegistry(tmp_path / "registry.sqlite3")
    # Persist raw=True deliberately; engine must request reflectance explicitly.
    identifier = registry.import_path(str(header), raw=True).datasets[0].id
    return registry, identifier, header, values.astype(np.float64)/65535


def test_bounded_reads_two_pca_passes_and_original_statistics(source, monkeypatch):
    registry, identifier, _, values = source
    original = SpectrumDataSet.read_region
    reads = []
    def bounded(dataset, l0, l1, s0, s1):
        assert l1-l0 <= 32
        reads.append((l0, l1, s0, s1))
        return original(dataset, l0, l1, s0, s1)
    monkeypatch.setattr(SpectrumDataSet, "read_region", bounded)
    monkeypatch.setattr(SpectrumDataSet, "to_numpy", lambda *_: pytest.fail("full original cube materialized"))
    result = SuperpixelEngine(registry).generate(identifier, Parameters(n_segments=64))
    assert reads == [(0, 32, 0, 48), (32, 40, 0, 48)] * 4
    assert result.features.normalized.dtype == np.float32
    assert result.segments.dtype == np.int32 and result.segments.shape == (40, 48)
    for segment in np.unique(result.segments):
        pixels = values[result.segments == segment]
        np.testing.assert_allclose(result.mean_spectra[segment], pixels.mean(axis=0), atol=1e-12)
        np.testing.assert_allclose(result.std_spectra[segment], pixels.std(axis=0), atol=1e-10)


def test_resident_feature_statistics_independent_retransform(source):
    registry, identifier, _, _ = source
    dataset, _ = registry.readable(identifier, raw=False)
    feature = pca_features(dataset, 5, 32)
    chunks = []  # Tiny TEST feature maps only; never original production spectra.
    for l0, l1 in ((0, 32), (32, 40)):
        chunks.append(feature.pca.transform(dataset.read_region(l0, l1, 0, 48).reshape(-1, 6)).astype(np.float32))
    transformed = np.concatenate(chunks)
    np.testing.assert_allclose(feature.mean, transformed.mean(axis=0, dtype=np.float64), atol=1e-6)
    np.testing.assert_allclose(feature.std, transformed.std(axis=0, dtype=np.float64), atol=1e-6)
    expected = transformed.reshape(40, 48, 5).copy()
    for i in range(5):
        expected[:, :, i] -= feature.mean[i]
        expected[:, :, i] /= feature.std[i]
    np.testing.assert_array_equal(feature.zscore, expected)
    np.testing.assert_array_equal(feature.normalized, (np.clip(expected, -3, 3)+3)/6)
    assert feature.pca.batch_size == 32*48


@pytest.mark.parametrize("components", [3, 5])
def test_lab_forced_false_and_connectivity_all_slic_calls(source, monkeypatch, components):
    import spectrumagent.annotation.engines.superpixels as module
    original = module.slic
    calls = []
    def checked(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs["convert2lab"] is False and kwargs["enforce_connectivity"] is True
        assert kwargs["channel_axis"] == 2 and kwargs["start_label"] == 0
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "slic", checked)
    registry, identifier, _, _ = source
    result = SuperpixelEngine(registry).generate(identifier, Parameters(n_segments=64, pca_components=components))
    assert calls and result.features.normalized.shape == (40, 48, components)
    assert result.reference_zscore5.shape == (40, 48, 5)


def test_refinement_preserves_neighbours_and_records_parent_children():
    rng = np.random.default_rng(1)
    feature = rng.random((12, 12, 5), dtype=np.float32)
    original = np.zeros((12, 12), dtype=np.int32)
    original[2:10, 2:10] = 1
    original[4:8, 4:8] = 2  # Neighbour embedded inside the parent's bounding box.
    counts = np.bincount(original.ravel())
    result, triggers, children = refine(feature, original, counts, np.array([0., 1., 0.]), .5, Parameters(n_segments=32))
    assert triggers == [1]
    for neighbour in (0, 2):
        np.testing.assert_array_equal(result[original == neighbour], original[original == neighbour])
        ids = np.unique(result[original == neighbour])
        assert len(ids) == 1
        np.testing.assert_array_equal(result == ids[0], original == neighbour)
    np.testing.assert_array_equal(np.isin(result, children[1]), original == 1)


def test_ratio_is_mean_ratio_with_fixed_pca5_reference():
    values = np.arange(3*7*5, dtype=np.float32).reshape(3, 7, 5)
    segments = np.zeros((3, 7), dtype=np.int32)
    segments[:, -1] = 1
    report = boundary_ratio(values, segments)
    expected = (report["boundary_sum"]/report["boundary_pairs"])/(report["internal_sum"]/report["internal_pairs"])
    assert report["R"] == expected and not np.isclose(report["R"], report["sum_ratio_diagnostic"])
    with pytest.raises(ValueError, match="PCA-5"):
        boundary_ratio(values[:, :, :3], segments)


def test_cache_force_and_source_change(source):
    registry, identifier, header, _ = source
    engine = SuperpixelEngine(registry)
    params = Parameters(n_segments=64)
    first = engine.generate(identifier, params)
    assert engine.generate(identifier, params) is first
    forced = engine.generate(identifier, params, force=True)
    assert forced is not first
    np.testing.assert_array_equal(first.segments, forced.segments)
    header.write_text(header.read_text("utf-8").replace("interleave=bil", "interleave=bip"), "utf-8")
    with pytest.raises(DataError) as error:
        engine.generate(identifier, params)
    assert error.value.code == "SOURCE_CHANGED"


@pytest.mark.parametrize("kwargs", [{"n_segments": 0}, {"compactness": 0}, {"compactness": float("nan")}, {"pca_components": 0}, {"pca_components": 7}, {"block_size": 0}, {"k": 0}])
def test_engine_invalid_parameters(source, kwargs):
    registry, identifier, _, _ = source
    with pytest.raises(DataError):
        SuperpixelEngine(registry).generate(identifier, Parameters(**kwargs))


def test_superpixel_http_report_and_no_scene(label_api, source):
    client, paths, _ = label_api
    _, _, header, _ = source
    imported = client.post("/api/v1/datasets/import", json={"path": str(header), "raw": True})
    identifier = imported.json()["datasets"][0]["id"]
    response = client.post(f"/api/v1/datasets/{identifier}/superpixels", json={"n_segments": 64, "compactness": .5, "pca_components": 3})
    assert response.status_code == 200
    report = response.json()
    assert report["feature_bytes"] == 40*48*3*4
    assert report["params"]["k"] == 3 and report["params"]["block_size"] == 32
    assert report["n_after"] == report["superpixel_count"]
    assert report["subdivided_ids"] == [i for i,d in enumerate(report["d_s"]) if d > report["tau"] and (client.app.state.superpixel_engine.cache[identifier][1].initial_segments == i).sum() >= 8]
    image = Image.open(BytesIO(base64.b64decode(report["overlay"]["png_base64"])))
    assert image.format == "PNG" and max(image.size) <= 512
    assert "segments" not in report and "mean_spectra" not in report
    assert report["peak_rss_bytes"] >= report["baseline_rss_bytes"] > 0
    with connect_database(paths.database) as db:
        assert db.execute("SELECT count(*) FROM annotation WHERE granularity='scene'").fetchone()[0] == 0


@pytest.mark.parametrize("body", [{"convert2lab": True}, {"enforce_connectivity": False}, {"n_segments": 0}, {"compactness": -1}, {"pca_components": True}, {"force": "true"}])
def test_http_parameters_reject_unexposed_or_invalid(label_api, source, body):
    client, _, _ = label_api
    _, _, header, _ = source
    identifier = client.post("/api/v1/datasets/import", json={"path": str(header)}).json()["datasets"][0]["id"]
    response = client.post(f"/api/v1/datasets/{identifier}/superpixels", json=body)
    assert response.status_code == 400 and response.json()["error"] == "INVALID_REQUEST"


@pytest.mark.parametrize("components", [3, 5])
def test_real_baseline_default_parameters(tmp_path, components):
    registry = DatasetRegistry(tmp_path / "registry.sqlite3")
    header = Path("E:/高光谱数据集/plastic/pe/20260804205214_64.hdr")
    identifier = registry.import_path(str(header)).datasets[0].id
    result = SuperpixelEngine(registry).generate(identifier, Parameters(pca_components=components))
    report = result.report
    assert 689 <= report["n_before"] <= 842
    assert report["area_cv"] >= .10 and report["R"] >= 1.5
    assert len(report["subdivided_ids"]) >= 1
    assert report["feature_bytes"] == 231*640*components*4
    assert report["normalized_min"] == 0 and report["normalized_max"] == 1
    assert all(.45 <= mean <= .55 for mean in report["normalized_mean"])
    assert all(0 < std <= 1/6 for std in report["normalized_std"])
    spec = importlib.util.spec_from_file_location("calibration_independent", Path(__file__).parents[3] / "milestone04/evidence/calibration/calibrate.py")
    calibration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calibration)
    ratio, sum_ratio = calibration.independent_ratio(result.reference_zscore5, result.initial_segments)
    assert ratio == pytest.approx(report["R"], rel=1e-12)
    assert sum_ratio == pytest.approx(report["sum_ratio_diagnostic"], rel=1e-12)
