"""Numerical oracles, input boundaries, artifact round trips and real HTTP wiring."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.cross_decomposition import PLSRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src-python")]

from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.data import DataError
from spectrumagent.experiments.inputs import load_input, mapping_weights
from spectrumagent.experiments.schema import ExperimentConfig, ImageInput
from spectrumagent.experiments.service import ExperimentService
from spectrumagent.storage import guard


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    temp = tmp_path / "system-temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    monkeypatch.setattr(guard, "_guards", {})
    monkeypatch.setattr(guard, "_current", None)
    paths = AppPaths(tmp_path / "app")
    paths.create_directories()
    yield paths
    for instance in guard._guards.values():
        instance.close()


def config_for(tmp_path):
    waves = np.arange(1100, 1145, 5, dtype=float)
    rng = np.random.default_rng(43)
    inputs = {}
    for role, count, offset in (("train", 36, 0), ("test", 18, 20)):
        X = rng.normal(size=(count, len(waves))) + offset
        y = np.tile([1, 2], count // 2)
        path = tmp_path / (role + ".npz")
        np.savez(path, X=X, y=y, wavelengths_nm=waves)
        inputs[role] = {"kind": "npz", "paths": [str(path)], "spectra_key": "X", "input_stage": "spectra",
                        "neighborhood": 1, "evaluation_unit": "spectrum"}
    return {"name": "explicit numerical check", **inputs, "wavelengths_nm": waves.tolist(),
            "classes": {1: "A", 2: "B"}, "preprocessing": [{"op": "standard_scale"}],
            "model": {"n_components": 2, "scale": False, "max_iter": 1000},
            "additional_metrics": ["kappa", "weighted_f1"], "test_usage": "independent_test"}


def test_train_only_fit_matches_sklearn_and_artifacts_survive_reload(tmp_path, workspace):
    config = ExperimentConfig.model_validate(config_for(tmp_path))
    service = ExperimentService(workspace)
    result = service.run(config)
    with np.load(config.train.paths[0]) as archive:
        train = {key: archive[key].copy() for key in archive.files}
    with np.load(config.test.paths[0]) as archive:
        test = {key: archive[key].copy() for key in archive.files}
    scaler = StandardScaler().fit(train["X"])
    estimator = PLSRegression(n_components=2, scale=False, max_iter=1000).fit(
        scaler.transform(train["X"]), (train["y"][:, None] == [1, 2]).astype(float))
    expected = estimator.predict(scaler.transform(test["X"]))
    folder = service.folder(result["experiment_id"])
    with np.load(folder / "test_predictions.npz") as archive:
        actual = {key: archive[key].copy() for key in archive.files}
    np.testing.assert_allclose(actual["responses"], expected, rtol=1e-12, atol=1e-12)
    model = joblib.load(service.artifact(result["experiment_id"], "model.joblib"))
    np.testing.assert_allclose(model.pipeline.fitted[0].mean_, train["X"].mean(axis=0))
    np.testing.assert_array_equal(model.predict(test["X"], config.wavelengths_nm), actual["prediction"])
    assert result["metrics"]["train"]["purpose"] == "training_fit"
    assert result["metrics"]["test"]["purpose"] == "independent_test"
    assert "weighted_f1" in result["metrics"]["test"]
    assert ExperimentService(workspace).get(result["experiment_id"]) == result
    curves = json.loads((folder / "curves.json").read_text("utf-8"))
    np.testing.assert_allclose(curves["test_input"]["classes"][0]["mean"], test["X"][test["y"] == 1].mean(axis=0))
    (folder / "report.html").write_text("modified", encoding="utf-8")
    with pytest.raises(DataError) as caught:
        service.artifact(result["experiment_id"], "report.html")
    assert caught.value.code == "EXPERIMENT_ARTIFACT_CHANGED"


@pytest.mark.parametrize("overlap", ["same_file", "copied_file", "identical_spectra", "same_sample_id"])
def test_overlapping_train_test_inputs_can_train(overlap, tmp_path, workspace, monkeypatch):
    body = config_for(tmp_path)
    if overlap == 'same_file':
        body['test'] = copy.deepcopy(body['train'])
    elif overlap == 'copied_file':
        Path(body['test']['paths'][0]).write_bytes(Path(body['train']['paths'][0]).read_bytes())
    elif overlap == 'identical_spectra':
        with np.load(body['train']['paths'][0]) as train, np.load(body['test']['paths'][0]) as test:
            values = {key: test[key].copy() for key in test.files}
            values['X'][0] = train['X'][0]
        np.savez(body['test']['paths'][0], **values)
    else:
        from spectrumagent.experiments import service
        load = service.load_input

        def with_shared_sample(*args, **kwargs):
            data = load(*args, **kwargs)
            for row in data.origins:
                row['sample_id'] = 'shared-sample'
            return data

        monkeypatch.setattr(service, 'load_input', with_shared_sample)
    if overlap != 'identical_spectra':
        with pytest.raises(DataError) as caught:
            ExperimentService(workspace).run(ExperimentConfig.model_validate(body))
        assert caught.value.code == 'EXPERIMENT_SPLIT_OVERLAP'
    body['test_usage'] = 'development_regression'
    result = ExperimentService(workspace).run(ExperimentConfig.model_validate(body))
    assert result['status'] == 'succeeded'
    assert result['split_checks']['status'] == 'completed'
    assert result['split_checks']['duplicate_test_spectra'] == {
        'same_file':36, 'copied_file':36, 'identical_spectra':1, 'same_sample_id':0}[overlap]
    assert result['split_checks']['physical_sample_independence'] == ('overlap' if overlap == 'same_sample_id' else 'unknown')
    assert (ExperimentService(workspace).folder(result['experiment_id']) / 'model.joblib').is_file()


@pytest.mark.parametrize("problem", ["nan", "wrong_axis", "unknown_class", "missing_class"])
def test_bad_inputs_fail_before_model_fit(problem, tmp_path, workspace, monkeypatch):
    body = config_for(tmp_path)
    path = Path(body["test"]["paths"][0])
    with np.load(path) as archive:
        values = {k: archive[k].copy() for k in archive.files}
    if problem == "nan":
        values["X"][0, 0] = np.nan
    elif problem == "wrong_axis":
        values["wavelengths_nm"] += 1
    elif problem == "unknown_class":
        values["y"][0] = 99
    else:
        path = Path(body["train"]["paths"][0])
        with np.load(path) as train:
            values = {k: train[k].copy() for k in train.files}
        values["y"][:] = 1
    np.savez(path, **values)
    def forbidden(*args):
        pytest.fail("invalid input reached model fitting")
    monkeypatch.setattr("spectrumagent.experiments.service.ExperimentModel.fit", forbidden)
    with pytest.raises(DataError) as caught:
        ExperimentService(workspace).run(ExperimentConfig.model_validate(body))
    identifier = caught.value.payload.context["experiment_id"]
    assert ExperimentService(workspace).get(identifier)["status"] == "failed"


def test_roi_halo_geometry_quality_and_explicit_centers(tmp_path):
    # Centers straddle a 32-line block boundary. Two touching same-class ROIs
    # must stay separate, and one bad DN invalidates all surrounding centers.
    h, w, bands = 68, 10, 9
    waves = np.arange(1100, 1145, 5, dtype=float)
    row, col, band = np.indices((h, w, bands))
    raw = (5000 + row * 10 + col * 2 + band * 100).astype(np.uint16)
    raw[20, 2, 4] = 65535
    header = tmp_path / "cube.hdr"
    header.with_suffix(".img").write_bytes(raw.tobytes())
    header.write_text("ENVI\nlines=68\nsamples=10\nbands=9\ndata type=12\ninterleave=bip\nbyte order=0\n"
                      "reflectance scale factor=10000\nwavelength units=nm\nwavelength={" +
                      ",".join(map(str, waves)) + "}\n", encoding="utf-8")
    regions = np.ones((h, w), np.int32)
    regions[:, 5:] = 2
    roi = tmp_path / "roi.npz"
    np.savez(roi, region_map=regions, label_map=np.ones((h, w), np.int32))
    centers = [(31, 2), (32, 2), (20, 2), (31, 4), (0, 2)]
    center_path = tmp_path / "centers.csv"
    center_path.write_text("row,col\n" + "\n".join(f"{r},{c}" for r, c in centers), encoding="utf-8")
    spec = ImageInput.model_validate({"kind": "roi_images", "members": [{"header_path": str(header),
        "roi_path": str(roi), "centers_path": str(center_path), "sample_id": "sample-a"}], "neighborhood": 3,
        "wavelength_unit": "nm", "mapping_window_nm": 5., "nearest_tolerance_nm": 5.,
        "quality": {"min_mean": .02, "min_std": .002, "max_zero_fraction": .05, "saturation": 65535.}})
    data = load_input(spec, waves, {1: "A", 2: "B"})
    expected = np.stack([(raw[r-1:r+2, c-1:c+2].astype(float)/10000).mean(axis=(0, 1)) for r, c in centers[:2]])
    np.testing.assert_allclose(data.X, expected.astype(np.float32), rtol=0, atol=0)
    assert [(r["row"], r["col"]) for r in data.origins] == centers[:2]
    assert data.excluded == 3
    # Half-open bins differ from interpolating the same target grid.
    weights = mapping_weights([1100., 1101., 1104., 1106.], [1100., 1105.], 5., 5.)
    np.testing.assert_array_equal(weights[:, 0], [.5, .5, 0, 0])


def test_http_entry_auth_validation_and_artifact_links(tmp_path, workspace):
    from spectrumagent.app import create_app
    identity = EngineIdentity()
    app = create_app(workspace, identity)
    with TestClient(app) as client:
        assert client.get("/api/v1/experiments/schema").status_code == 401
        client.headers["Authorization"] = "Bearer " + identity.token
        assert client.get("/api/v1/experiments/schema").status_code == 200
        response = client.post("/api/v1/experiments/run", json=config_for(tmp_path))
        assert response.status_code == 200, response.text
        assert response.headers["X-SpectrumAgent-Boot-Id"] == identity.boot_id
        result = response.json()
        base = "/api/v1/experiments/" + result["experiment_id"]
        assert client.get(base).json() == result
        assert client.get(base + "/artifacts/train_input.png").content.startswith(b"\x89PNG")
        assert client.get(base + "/artifacts/report.html").status_code == 200
        assert client.post("/api/v1/experiments/run", json={}).status_code == 400


def test_raw_json_rois_complete_train_test_run(tmp_path, workspace):
    body = config_for(tmp_path)
    rng = np.random.default_rng(84)
    for role in ("train", "test"):
        header = tmp_path / (role + ".hdr")
        raw = rng.integers(3000, 12000, (9, 10, 9), dtype=np.uint16)
        header.with_suffix(".img").write_bytes(raw.tobytes())
        header.write_text("ENVI\nlines=9\nsamples=10\nbands=9\ndata type=12\ninterleave=bip\nbyte order=0\n"
                          "reflectance scale factor=10000\nwavelength units=nm\nwavelength={" +
                          ",".join(map(str, body["wavelengths_nm"])) + "}\n", encoding="utf-8")
        roi = tmp_path / (role + ".json")
        roi.write_text(json.dumps({"imageHeight": 9, "imageWidth": 10, "material_confirmed": True,
            "source_signature": {"hdr_sha256": hashlib.sha256(header.read_bytes()).hexdigest()}, "shapes": [
                {"label": "A", "shape_type": "rectangle", "points": [[0, 0], [4, 8]]},
                {"label": "B", "shape_type": "polygon", "points": [[5, 0], [9, 0], [9, 8], [5, 8]]}]}), encoding="utf-8")
        body[role] = {"kind": "roi_images", "members": [{"header_path": str(header), "roi_path": str(roi), "sample_id": role}],
                      "neighborhood": 3, "wavelength_unit": "nm", "mapping_window_nm": 5., "nearest_tolerance_nm": 5.,
                      "quality": {"min_mean": .02, "min_std": .002, "max_zero_fraction": .05, "saturation": 65535.}}
    config = ExperimentConfig.model_validate(body)
    result = ExperimentService(workspace).run(config)
    for role in ("train", "test"):
        assert result["datasets"][role]["observations"] == 42
        assert result["datasets"][role]["excluded_centers"] == 48
        assert result["metrics"][role]["evaluation_unit"] == "center_pixel"


def test_changed_source_cannot_publish_success(tmp_path, workspace, monkeypatch):
    from spectrumagent.experiments.service import ExperimentModel
    body = config_for(tmp_path)
    original_fit = ExperimentModel.fit
    def change_after_fit(model, X, y):
        features = original_fit(model, X, y)
        with Path(body["test"]["paths"][0]).open("ab") as stream:
            stream.write(b"changed")
        return features
    monkeypatch.setattr(ExperimentModel, "fit", change_after_fit)
    with pytest.raises(DataError) as caught:
        ExperimentService(workspace).run(ExperimentConfig.model_validate(body))
    assert caught.value.code == "SOURCE_CHANGED"
    result = ExperimentService(workspace).get(caught.value.payload.context["experiment_id"])
    assert result["status"] == "failed"


@pytest.mark.skipif(not os.environ.get("SPECTRUM_FROZEN_RELEASE"), reason="explicit local frozen data path required")
def test_frozen_five_class_predictions(tmp_path, workspace, monkeypatch):
    release = Path(os.environ["SPECTRUM_FROZEN_RELEASE"])
    body = config_for(tmp_path)
    for role, filename in (("train", "训练光谱.npz"), ("test", "测试V2光谱.npz")):
        body[role].update(paths=[str(release / filename)], spectra_key="X3", input_stage="neighborhood_mean",
                          neighborhood=3, evaluation_unit="center_pixel")
    body.update(name="five-class numerical regression", wavelengths_nm=np.arange(1120, 1680, 5, dtype=float).tolist(),
                classes={1: "PE", 2: "PP", 3: "PET", 4: "EPS", 5: "纸"},
                preprocessing=[{"op": "savgol", "window": 15, "polyorder": 2, "derivative": 2, "delta_nm": 5.},
                               {"op": "l2"}, {"op": "center"}],
                model={"n_components": 12, "scale": False, "max_iter": 1000}, test_usage="development_regression")
    files = [release / name for name in ("训练光谱.npz", "测试V2光谱.npz", "model.joblib")]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    config = ExperimentConfig.model_validate(body)
    service = ExperimentService(workspace)
    result = service.run(config)
    folder = service.folder(result["experiment_id"])
    with np.load(release / "测试V2光谱.npz") as test, np.load(folder / "test_predictions.npz") as actual:
        np.testing.assert_array_equal(actual["prediction"], test["prediction"])
        assert len(actual["prediction"]) == 51025
    monkeypatch.syspath_prepend(str(release.parents[1]))
    reference = joblib.load(release / "model.joblib")["model"]
    with np.load(release / "训练光谱.npz") as train, np.load(folder / "train_predictions.npz") as actual:
        np.testing.assert_array_equal(actual["prediction"], reference.predict(train["X3"]))
        assert len(actual["prediction"]) == 6000
    assert result["metrics"]["train"]["correct"] == 5746
    assert result["metrics"]["test"]["correct"] == 47683
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files} == before
    print("FROZEN_RESULT_DIR=" + str(folder))
