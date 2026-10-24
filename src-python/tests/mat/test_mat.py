import json
import tracemalloc

import numpy as np
import pytest
from scipy.io import loadmat

from backend.database import connect_database
from spectrumagent.agent.mat import MatStore
from spectrumagent.data import SpectrumDataSet
from spectrumagent.preprocess.recipes import input_fingerprint
from spectrumagent.preprocess.run import file_sha256


def test_raw_dn_axes_dtype_wavelengths_and_nine_metadata_values(mat_case):
    c = mat_case
    saved = c.store.save(c.cube)
    snapshot = c.store.read_version(saved["id"])
    result = MatStore(c.registry, c.paths).generate(c.cube, saved["id"], snapshot["label_map"])
    content = loadmat(c.paths.root / result["relative_path"], simplify_cells=True)
    np.testing.assert_array_equal(content["spectra"], c.values[c.mask].astype(np.float32))
    assert content["spectra"].dtype == np.float32 and content["spectra"].shape == (12, 3)
    assert content["labels"].dtype == np.int32 and set(content["labels"]) == {3}
    assert content["rows"].dtype == content["cols"].dtype == np.int32
    rr, cc = np.nonzero(c.mask)
    np.testing.assert_array_equal(content["rows"], rr)
    np.testing.assert_array_equal(content["cols"], cc)
    assert content["source_dtype"] == ">u2"
    assert json.loads(content["label_index"]) == snapshot["label_index"]
    assert bool(content["has_wavelengths"]) is c.wavelengths
    assert content["wavelengths"].dtype == np.float64
    np.testing.assert_array_equal(content["wavelengths"], [450, 550, 650] if c.wavelengths else [])
    hashes = {p.name: file_sha256(p) for p in [c.header, c.header.with_suffix(".img")]}
    fingerprint = input_fingerprint(c.cube, hashes, saved["id"], 12)
    assert content["metadata"] == {"cube_id": c.cube, "annotation_version_id": saved["id"],
        "input_fingerprint": fingerprint, "n_spectra": 12, "n_bands": 3, "n_classes": 4,
        "dtype_note": "raw_dn_pre_b01", "schema_version": 1, "created_at": result["created_at"]}
    assert result["input_fingerprint"] == fingerprint
    assert result["sha256"] == file_sha256(c.paths.root / result["relative_path"])
    assert not (c.paths.root / "exports" / c.cube / saved["id"] / ".tmp").exists()


def test_unique_rebuild_and_bounded_raw_reads_with_write_peak(mat_case, monkeypatch, record_property):
    c = mat_case
    saved = c.store.save(c.cube)
    original = SpectrumDataSet.read_region
    reads = []
    def bounded(dataset, l0, l1, s0, s1):
        assert dataset._raw is True
        assert l1 - l0 < dataset.shape[0], "full raw cube read"
        reads.append((l0, l1))
        return original(dataset, l0, l1, s0, s1)
    monkeypatch.setattr(SpectrumDataSet, "read_region", bounded)
    monkeypatch.setattr(SpectrumDataSet, "to_numpy", lambda *_: pytest.fail("full DN materialization"))
    from spectrumagent.agent import mat
    writer, write_peaks = mat.savemat, []
    def measured_write(path, content, **kwargs):
        assert kwargs == {"do_compression": False}
        assert path.parent.name == ".tmp"
        assert all(isinstance(content[key], np.memmap) for key in ("spectra", "labels", "rows", "cols"))
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        writer(path, content, **kwargs)
        _, peak = tracemalloc.get_traced_memory()
        write_peaks.append(peak - before)
    monkeypatch.setattr(mat, "savemat", measured_write)
    store = MatStore(c.registry, c.paths)
    tracemalloc.start()
    try:
        first = store.rebuild(c.cube, saved["id"])
        second = store.rebuild(c.cube, saved["id"])
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(write_peaks) == 2
    record_property("savemat_write_peak_bytes", max(write_peaks))
    print(f"savemat_write_peak_bytes={write_peaks}; pipeline_peak_bytes={peak}")
    assert reads and first["id"] == second["id"]
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM training_mat WHERE annotation_version_id=?", (saved["id"],)).fetchone()[0] == 1
        required = [r[1] for r in db.execute("PRAGMA table_info(training_mat)") if r[3]]
        db.row_factory = __import__("sqlite3").Row
        assert all(dict(db.execute("SELECT * FROM training_mat").fetchone())[key] is not None for key in required)


def test_exports_are_never_preprocess_inputs(mat_case, monkeypatch):
    from spectrumagent.preprocess.run import RunEngine
    c = mat_case
    saved = c.store.save(c.cube)
    runner = RunEngine(c.registry, c.paths)
    recipe = runner.recipes.create("exports-proof", "exports proof", None, {"steps": []})["versions"][0]["id"]
    first = runner.run(c.cube, saved["id"], recipe, block_size=1)
    assert first["status"] == "succeeded", first["error"]
    directory = c.paths.root / "exports" / c.cube / saved["id"]
    directory.mkdir(parents=True)
    (directory / "training_mat.mat").write_bytes(b"fake MAT: never a computation input")
    from pathlib import Path
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert not path.is_relative_to(c.paths.root / "exports")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    second = runner.run(c.cube, saved["id"], recipe, block_size=1)
    assert second["status"] == "succeeded", second["error"]
    assert first["input_fingerprint"] == second["input_fingerprint"]
    def spectra(row):
        artifact = next(a for a in row["artifacts"] if a["kind"] == "sample_spectra")
        with np.load(c.paths.preprocessed / artifact["relative_path"]) as archive:
            return {key: archive[key].copy() for key in archive.files}
    a, b = spectra(first), spectra(second)
    assert a.keys() == b.keys()
    for key in a:
        np.testing.assert_array_equal(a[key], b[key])
