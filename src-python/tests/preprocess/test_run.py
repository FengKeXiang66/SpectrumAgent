import hashlib
import json
from pathlib import PurePosixPath
from uuid import uuid4

import numpy as np
import pytest

from backend.database import connect_database
from backend.paths import AppPaths
from spectrumagent.data import DataError, SpectrumDataSet
from spectrumagent.preprocess.recipes import input_fingerprint
from spectrumagent.preprocess.registry import PreprocessError
from .run_fixtures import run_case, step


def test_paths_environment_derivation_no_source_output(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths = AppPaths.from_environment()
    assert paths.preprocessed == tmp_path/"SpectrumAgent"/"preprocessed"
    assert paths.preprocessed.parent == paths.snapshots.parent


def test_run_raw_scale_artifacts_hashes_lineage_and_four_state_success(run_case, monkeypatch):
    c = run_case
    recipe = c.recipe([])
    states, raw_modes = [], []
    original = c.runner._transition
    def transition(identifier, status, **kw):
        states.append(c.runner.get(identifier)["status"])
        original(identifier, status, **kw)
    monkeypatch.setattr(c.runner, "_transition", transition)
    readable = c.registry.readable
    def read(identifier, raw=None):
        raw_modes.append(raw)
        return readable(identifier, raw=raw)
    monkeypatch.setattr(c.registry, "readable", read)
    monkeypatch.setattr(SpectrumDataSet, "to_numpy", lambda *_: pytest.fail("full cube forbidden"))
    original_region = SpectrumDataSet.read_region
    def bounded(dataset, l0, l1, s0, s1):
        assert l1-l0 <= 3 and dataset._raw is True
        return original_region(dataset, l0, l1, s0, s1)
    monkeypatch.setattr(SpectrumDataSet, "read_region", bounded)
    import spectrumagent.preprocess.run as module
    digest, hashed = module.file_sha256, []
    def hash_once(path):
        hashed.append(path)
        return digest(path)
    monkeypatch.setattr(module, "file_sha256", hash_once)
    row = c.runner.run(c.cube, c.version, recipe, block_size=3)
    assert row["status"] == "succeeded", row["error"]
    assert states == ["pending"] and row["finished_at"] and set(raw_modes) == {True}
    assert row["b01_branch"] == "scale" and row["annotation_version_id"] == c.version
    assert hashed.count(c.header) == hashed.count(c.header.with_suffix(".bil")) == 1
    spectra = c.spectra(row)
    for index in (0, 1, 2):
        expected = c.values[c.label_map == index].astype(float)/65535
        np.testing.assert_allclose(spectra[f"mean_{index}"], expected.mean(axis=0), atol=1e-12)
        np.testing.assert_allclose(spectra[f"std_{index}"], expected.std(axis=0), atol=1e-12)
    assert {item["kind"] for item in row["artifacts"]} == {"sample_spectra", "report"}
    for item in row["artifacts"]:
        relative = PurePosixPath(item["relative_path"])
        assert not relative.is_absolute() and ".." not in relative.parts and "\\" not in str(relative)
        assert item["sha256"] == hashlib.sha256((c.paths.preprocessed/item["relative_path"]).read_bytes()).hexdigest()
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT COUNT(*) FROM preprocess_run r JOIN annotation_version a ON a.id=r.annotation_version_id "
                          "JOIN preprocess_recipe_version v ON v.id=r.recipe_version_id JOIN preprocess_artifact f ON f.run_id=r.id "
                          "WHERE r.id=? AND a.cube_id=r.cube_id", (row["id"],)).fetchone()[0] == 2


@pytest.mark.parametrize("steps", [
    [step("standardize", method="standard")], [step("standardize", method="minmax")],
    [step("pca", n_components=3)], [step("mnf", n_components=3)], [step("ica", n_components=3)],
    [step("standardize", method="standard"), step("pca", n_components=3)],
    [step("snv"), step("ica", n_components=3)]])
def test_global_fit_independent_of_disk_block_size(run_case, steps):
    c = run_case
    recipe = c.recipe(steps)
    first = c.runner.run(c.cube, c.version, recipe, block_size=1)
    second = c.runner.run(c.cube, c.version, recipe, block_size=7)
    assert first["status"] == second["status"] == "succeeded", (first["error"], second["error"])
    a, b = c.spectra(first), c.spectra(second)
    for key in a:
        np.testing.assert_array_equal(a[key], b[key])
    assert first["metrics"] == second["metrics"]
    assert c.report(first)["steps"] == c.report(second)["steps"]
    for a_step, b_step in zip(c.report(first)["steps"], c.report(second)["steps"]):
        if "loadings" in a_step["meta"]:
            # Compare actual score transforms, beyond aggregate/shape assertions.
            x = c.values[c.label_map >= 0].astype(float)/65535
            a_scores = (x-np.array(a_step["meta"]["mean"])) @ np.array(a_step["meta"]["loadings"])
            b_scores = (x-np.array(b_step["meta"]["mean"])) @ np.array(b_step["meta"]["loadings"])
            np.testing.assert_array_equal(a_scores, b_scores)
    assert c.report(second)["input_fingerprint_matches_previous"] is True
    if steps[0]["op"] == "standardize":
        assert first["scaler_params"] == second["scaler_params"]
        assert len(first["scaler_params"]) == 8


def test_standard_fitted_matches_global_pixel_formula_and_not_block_fit(run_case):
    c = run_case
    row = c.runner.run(c.cube, c.version, c.recipe([step("standardize", method="standard")]), block_size=2)
    x = c.values[c.label_map >= 0].astype(float)/65535
    fitted = row["scaler_params"]
    np.testing.assert_allclose([item["mean"] for item in fitted], x.mean(axis=0), atol=1e-12)
    np.testing.assert_allclose([item["std"] for item in fitted], x.std(axis=0), atol=1e-12)
    expected = (x-x.mean(axis=0))/x.std(axis=0)
    np.testing.assert_allclose(c.spectra(row)["mean_0"], expected[:40].mean(axis=0), atol=1e-12)


@pytest.mark.parametrize("op", ["pca", "ica"])
def test_failed_after_running_records_error_and_no_half_artifact(run_case, op):
    c = run_case
    row = c.runner.run(c.cube, c.version, c.recipe([step(op, n_components=9)]))
    assert row["status"] == "failed" and row["finished_at"]
    assert row["error"]["error"] == "INVALID_OPERATOR_PARAMS"
    assert row["artifacts"] == [] and not (c.paths.preprocessed/c.cube/row["id"]).exists()


def test_stale_really_triggered_before_pending_and_other_version_works(run_case):
    c = run_case
    recipe = c.recipe([step("pca", n_components=2)])
    entry = c.runner.operators.entries["pca"].pop(1)
    with pytest.raises(DataError) as caught:
        c.runner.run(c.cube, c.version, recipe)
    assert caught.value.code == "OPERATOR_VERSION_STALE" and caught.value.status_code == 409
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT COUNT(*) FROM preprocess_run").fetchone()[0] == 0
    c.runner.operators.register("pca", 2, entry.model, entry.impl)
    recipe2 = c.recipe([{**step("pca", n_components=2), "version": 2}])
    assert c.runner.run(c.cube, c.version, recipe2)["status"] == "succeeded"


@pytest.mark.parametrize("failure", ["source", "annotation", "recipe", "traversal"])
def test_preflight_failures_leave_no_run(run_case, failure):
    c = run_case
    recipe, version = c.recipe([]), c.version
    if failure == "source":
        c.header.unlink()
    elif failure == "annotation":
        version = str(uuid4())
    elif failure == "recipe":
        recipe = str(uuid4())
    else:
        with connect_database(c.paths.database) as db:
            db.execute("UPDATE annotation_version SET snapshot_ref='../outside' WHERE id=?", (version,))
    with pytest.raises(DataError):
        c.runner.run(c.cube, version, recipe)
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT COUNT(*) FROM preprocess_run").fetchone()[0] == 0


def test_actual_content_hash_and_annotation_version_change_fingerprint(run_case):
    c = run_case
    recipe = c.recipe([])
    first = c.runner.run(c.cube, c.version, recipe)
    report = c.report(first)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (c.header, c.header.with_suffix(".bil"))}
    assert report["source_hashes"] == hashes
    assert first["input_fingerprint"] == input_fingerprint(c.cube, hashes, c.version, 110)
    path = c.header.with_suffix(".bil")
    contents = bytearray(path.read_bytes())
    contents[0] ^= 1
    path.write_bytes(contents)
    changed = c.runner.run(c.cube, c.version, recipe)
    assert changed["input_fingerprint"] != first["input_fingerprint"]
    assert c.report(changed)["input_fingerprint_matches_previous"] is False


def test_ica_temp_bytes_peak_rss_and_finally_cleanup(run_case, monkeypatch):
    c = run_case
    recipe = c.recipe([step("ica", n_components=3)])
    first = c.runner.run(c.cube, c.version, recipe)
    second = c.runner.run(c.cube, c.version, recipe)
    assert first["status"] == second["status"] == "succeeded"
    for key, value in c.spectra(first).items():
        np.testing.assert_allclose(value, c.spectra(second)[key], rtol=0, atol=1e-12)
    report = c.report(first)
    assert report["temporary_bytes"] == 110*8*8 and report["peak_rss_bytes"] > 0
    assert not list(c.paths.preprocessed.rglob(".tmp")) and not list(c.paths.preprocessed.rglob("*.dat"))
    import spectrumagent.preprocess.run as module
    monkeypatch.setattr(module, "fit_ica", lambda *_a, **_k: (_ for _ in ()).throw(PreprocessError("INJECTED", "fit failed")))
    failed = c.runner.run(c.cube, c.version, recipe)
    assert failed["error"]["error"] == "INJECTED" and not list(c.paths.preprocessed.rglob(".tmp"))


def test_publication_failure_rolls_back_both_artifacts(run_case, monkeypatch):
    c = run_case
    import spectrumagent.preprocess.run as module
    replace, calls = module.os.replace, []
    def fail_second(source, destination):
        calls.append(destination)
        if len(calls) == 2:
            raise OSError("injected second publication failure")
        replace(source, destination)
    monkeypatch.setattr(module.os, "replace", fail_second)
    row = c.runner.run(c.cube, c.version, c.recipe([]))
    assert row["status"] == "failed" and row["error"]["error"] == "PREPROCESS_RUN_FAILED"
    assert row["artifacts"] == [] and not (c.paths.preprocessed/c.cube/row["id"]).exists()


def test_artifact_db_insert_failure_rolls_back_rows_and_files(run_case, monkeypatch):
    from contextlib import contextmanager
    import sqlite3
    import spectrumagent.preprocess.run as module
    c = run_case
    original = module.connect_database
    @contextmanager
    def guarded(*args, **kwargs):
        with original(*args, **kwargs) as db:
            db.set_authorizer(lambda action, table, *_:
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and table == "preprocess_artifact"
                else sqlite3.SQLITE_OK)
            yield db
    monkeypatch.setattr(module, "connect_database", guarded)
    row = c.runner.run(c.cube, c.version, c.recipe([]))
    assert row["status"] == "failed" and row["artifacts"] == []
    assert not (c.paths.preprocessed/c.cube/row["id"]).exists()


def test_running_state_is_committed_and_failure_error_is_as_dict(run_case):
    from spectrumagent.preprocess.schema import SnvParams
    c = run_case
    expected = PreprocessError("INJECTED_OPERATOR", "failed in running", original="context")
    def fail(x, params):
        with connect_database(c.paths.database) as db:
            assert db.execute("SELECT status FROM preprocess_run").fetchall() == [("running",)]
        raise expected
    c.runner.operators.register("failure", 1, SnvParams, fail)
    row = c.runner.run(c.cube, c.version, c.recipe([step("failure")]))
    assert row["status"] == "failed" and row["error"] == expected.as_dict()


def test_run_version_dispatch_preserves_new_impl_not_builtin_name(run_case):
    c = run_case
    model = c.runner.operators.resolve("pca", 1).model
    c.runner.operators.register("pca", 2, model, lambda x, p: (x[:, :p["n_components"]]*2, {"axis": None}))
    recipe = c.recipe([{**step("pca", n_components=2), "version": 2}])
    row = c.runner.run(c.cube, c.version, recipe)
    assert row["status"] == "succeeded"
    expected = c.values[c.label_map == 0, :2].mean(axis=0)/65535*2
    np.testing.assert_allclose(c.spectra(row)["mean_0"], expected, atol=1e-12)


def test_reference_missing_resolved_spectra_preflight_no_run(run_case):
    c = run_case
    text = c.header.read_text().replace("reflectance scale factor=65535\n", "")
    c.header.write_text(text+"white reference=white.hdr\ndark reference=dark.hdr\n", "utf-8")
    with pytest.raises(DataError) as caught:
        c.runner.run(c.cube, c.version, c.recipe([]))
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT COUNT(*) FROM preprocess_run").fetchone()[0] == 0


@pytest.mark.parametrize("later_diverges", [False, True])
def test_float_passthrough_and_later_range_disagreement(run_case, later_diverges):
    c = run_case
    values = c.values.astype(np.float32)/65535
    if later_diverges:
        values[10] = 2.
    header = c.header.with_name("float.hdr")
    header.with_suffix(".bil").write_bytes(values.transpose(0, 2, 1).tobytes())
    header.write_text("ENVI\nlines=24\nsamples=5\nbands=8\ndata type=4\ninterleave=bil\n", "utf-8")
    cube = str(c.registry.import_path(str(header), raw=True).datasets[0].id)
    with connect_database(c.paths.database) as db:
        db.execute("UPDATE annotation_version SET cube_id=? WHERE id=?", (cube, c.version))
    row = c.runner.run(cube, c.version, c.recipe([]), block_size=2)
    assert row["b01_branch"] == "passthrough"
    if later_diverges:
        assert row["status"] == "failed" and row["error"]["error"] == "UNKNOWN_REFLECTANCE_INPUT"
        assert row["artifacts"] == []
    else:
        assert row["status"] == "succeeded"
        np.testing.assert_allclose(c.spectra(row)["mean_0"], values[c.label_map == 0].mean(axis=0), atol=1e-7)


def test_annotation_version_fingerprint_and_fitted_recomputed(run_case):
    c = run_case
    recipe = c.recipe([step("standardize", method="standard")])
    original = c.runner.run(c.cube, c.version, recipe)
    version = str(uuid4())
    directory = c.paths.snapshots/c.cube/"v2"
    directory.mkdir()
    changed_map = c.label_map.copy()
    changed_map[:4] = -1
    np.savez_compressed(directory/"label_map.npz", label_map=changed_map)
    (directory/"label_index.json").write_bytes((c.paths.snapshots/c.cube/"v1"/"label_index.json").read_bytes())
    with connect_database(c.paths.database) as db:
        db.execute("INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,params,created_at) "
                   "VALUES (?,?,2,?,120,90,'{}','fixture')", (version, c.cube, f"{c.cube}/v2"))
    changed = c.runner.run(c.cube, version, recipe)
    assert changed["input_fingerprint"] != original["input_fingerprint"]
    assert changed["scaler_params"] != original["scaler_params"]
    restored = c.runner.run(c.cube, c.version, recipe)
    assert restored["input_fingerprint"] == original["input_fingerprint"]
    assert restored["scaler_params"] == original["scaler_params"]


@pytest.mark.parametrize("policy", ["zeros", "nan", "error"])
def test_global_standard_exact_constant_band_three_zero_policies(run_case, policy):
    c = run_case
    values = c.values.copy()
    values[:, :, 2] = 12345
    c.header.with_suffix(".bil").write_bytes(values.transpose(0, 2, 1).tobytes())
    row = c.runner.run(c.cube, c.version, c.recipe([step("standardize", method="standard", zero_std=policy)]))
    if policy == "error":
        assert row["status"] == "failed"
        assert row["error"]["error"] == "NORMALIZATION_DEGENERATE" and row["error"]["context"]["zero_scale_count"] == 1
    else:
        assert row["status"] == "succeeded" and row["scaler_params"][2]["std"] == 0
        if policy == "zeros":
            assert c.spectra(row)["mean_0"][2] == c.spectra(row)["std_0"][2] == 0
        else:
            assert row["metrics"]["nan_spectra_skipped"] == 110


@pytest.mark.parametrize("op", ["pca", "mnf", "ica"])
def test_b08_run_nan_fit_exclusion_and_input_provenance_count(run_case, op):
    c = run_case
    values = c.values.astype(np.float32)
    values[0, 0, 0] = np.nan
    header = c.header.with_name("nan.hdr")
    header.with_suffix(".bil").write_bytes(values.transpose(0, 2, 1).tobytes())
    header.write_text("ENVI\nlines=24\nsamples=5\nbands=8\ndata type=4\ninterleave=bil\nreflectance scale factor=65535\n", "utf-8")
    cube = str(c.registry.import_path(str(header), raw=True).datasets[0].id)
    with connect_database(c.paths.database) as db:
        db.execute("UPDATE annotation_version SET cube_id=? WHERE id=?", (cube, c.version))
    row = c.runner.run(cube, c.version, c.recipe([step(op, n_components=3)]), block_size=3)
    assert row["status"] == "succeeded", row["error"]
    report = c.report(row)
    assert report["steps"][0]["meta"]["nan_spectra"] == 1
    assert report["fitting_source"]["n_spectra"] == 110
    assert row["metrics"]["nan_spectra_skipped"] == 1
    if op == "ica":
        assert report["temporary_bytes"] == 109*8*8
