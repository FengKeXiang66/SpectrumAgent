"""TASK-32 acceptance: real reports, independent pixel arithmetic and bounded IO."""
from copy import deepcopy
from hashlib import sha256
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from backend.database import connect_database
from backend.paths import AppPaths
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.data import DataError, SpectrumDataSet
from spectrumagent.data.readers.envi import EnviReader
from spectrumagent.data.readers.header import classic, key_name, KNOWN
from spectrumagent.preprocess import builtin_registry
from spectrumagent.preprocess.export import ReportReplay, export_run, replay_from_report
from spectrumagent.preprocess.registry import PreprocessError
from spectrumagent.preprocess.run import RunEngine, file_sha256
from .run_fixtures import run_case, step
from .test_routes import preprocess_api


AXIS = list(map(float, range(1, 9)))
VARIANTS = [[], [step("pca", n_components=3)], [step("mnf", n_components=3)],
            [step("ica", n_components=3)], [step("snv")],
            *[[step("standardize", method=method)] for method in ("standard", "minmax", "area", "vector")],
            *[[step("continuum", method=method)] for method in ("convex_hull", "linear")],
            [step("sg_smooth", window=5, polyorder=2)],
            [step("sg_derivative", window=5, polyorder=2, order=1)],
            [step("crop", source=AXIS, range=[2., 6.])],
            [step("resample", source=AXIS, target=[1., 2.5, 4., 6., 8.], method="linear")]]


def inventory(directory):
    return {file.name: (sha256(file.read_bytes()).hexdigest(), file.stat().st_mtime_ns)
            for file in directory.iterdir() if file.is_file()}


def report_path(c, row):
    return c.paths.artifact_root/next(item["relative_path"] for item in row["artifacts"] if item["kind"] == "report")


def straight_pixel(report, raw):
    """Independent direct arithmetic; never calls replay_from_report / ReportReplay."""
    params = report["b01"]["params"]
    # This real fixture's B01 criterion is scale=65535, checked against the report.
    assert float(params["hdr"]["reflectance scale factor"]) == 65535
    x = raw.astype(np.float64)[None, :]/65535.
    registry = builtin_registry()
    for saved in report["steps"]:
        op, meta, params = saved["op"], saved["meta"], saved["params"]
        if op == "standardize" and params["method"] in ("standard", "minmax"):
            if params["method"] == "standard":
                offset = np.array([row["mean"] for row in meta["fitted"]])
                scale = np.array([row["std"] for row in meta["fitted"]])
            else:
                offset = np.array([row["min"] for row in meta["fitted"]])
                scale = np.array([row["max"]-row["min"] for row in meta["fitted"]])
            x = (x-offset)/scale
        elif op in ("pca", "mnf", "ica"):
            x = (x-np.asarray(meta["mean"])) @ np.asarray(meta["loadings"])
        else:
            result = registry.resolve(op, saved["version"]).impl(x, deepcopy(params))
            x = result[0] if isinstance(result, tuple) else result
    return x[0]


@pytest.mark.parametrize("steps", VARIANTS)
def test_real_report_replay_pixels_envi_axes_methods_and_no_fit(run_case, monkeypatch, steps):
    c = run_case
    row = c.runner.run(c.cube, c.version, c.recipe(steps))
    assert row["status"] == "succeeded", row["error"]
    path = report_path(c, row)
    before = path.read_bytes()
    report = json.loads(before)
    source_before = inventory(c.header.parent)
    assert "hdr" not in report["b01"]["meta"]
    assert set(report["b01"]["params"]) == {"hdr", "branch", "white_reference", "dark_reference", "guard"}
    assert all("axis" not in saved["meta"] for saved in report["steps"])
    calls, fitted_calls = [], []
    module = importlib.import_module("spectrumagent.preprocess.export")
    original = module.reflectance
    def checked_reflectance(x, params):
        assert json.dumps(params["hdr"], ensure_ascii=False).encode() == json.dumps(report["b01"]["params"]["hdr"], ensure_ascii=False).encode()
        calls.append(len(x))
        return original(x, params)
    def forbidden_fit(*args, **kwargs):
        fitted_calls.append(True)
        pytest.fail("export must never fit")
    with monkeypatch.context() as patch:
        patch.setattr(module, "reflectance", checked_reflectance)
        patch.setattr(SpectrumDataSet, "to_numpy", lambda *_: pytest.fail("whole cube access forbidden"))
        patch.setattr("spectrumagent.api.registry.read_header", lambda *_args, **_kw: pytest.fail("source header reread forbidden"))
        for name, function in (("run", "fit_standard"), ("operators.pca", "fit_pca"),
                               ("operators.mnf", "fit_mnf"), ("operators.ica", "fit_ica")):
            patch.setattr(importlib.import_module("spectrumagent.preprocess."+name), function, forbidden_fit)
        result = export_run(c.runner, row["id"])
    assert calls and fitted_calls == []
    assert result["status"] == "succeeded" and result["scope"] == "full_cube"
    entries = {Path(item["relative_path"]).suffix: item for item in result["artifacts"]}
    hdr = c.paths.artifact_root/entries[".hdr"]["relative_path"]
    dataset = EnviReader().open(hdr, raw=True)
    output_bands = straight_pixel(report, c.values[0, 0]).shape[0]
    assert dataset.shape == (*c.values.shape[:2], output_bands)
    assert dataset.dtype == "float32" and dataset.interleave == "bsq"
    assert Path(dataset.data_path) == c.paths.artifact_root/entries[".img"]["relative_path"]
    fields = {key_name(key): value for key, value in classic(hdr.read_text("utf-8")).items()}
    assert set(fields) <= KNOWN and "fwhm" not in fields
    if report["wavelengths"]:
        assert dataset.wavelengths == report["wavelengths"] and len(dataset.wavelengths) == output_bands
    else:
        assert "wavelengths" not in fields and dataset.wavelengths == []
    # Seed=32, 24 random pixels plus both previously unlabelled/uncertain rows.
    points = np.random.default_rng(32).choice(c.values.shape[0]*c.values.shape[1], 24, replace=False).tolist()+[110, 115]
    assert any(c.label_map[index//5, index % 5] < 0 for index in points)
    for index in points:
        line, sample = divmod(index, 5)
        np.testing.assert_allclose(dataset.read_pixel(line, sample), straight_pixel(report, c.values[line, sample]), rtol=0, atol=1e-6)
    manifest = json.loads((c.paths.artifact_root/result["manifest_relative_path"]).read_text("utf-8"))
    frozen = [{"op": saved["op"], "version": saved["version"], "meta": saved["meta"]}
              for saved in report["steps"] if saved["op"] in ("pca", "mnf", "ica")
              or saved["op"] == "standardize" and saved["params"]["method"] in ("standard", "minmax")]
    expected_signature = sha256(json.dumps(frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert manifest["fit_signature"] == expected_signature
    assert manifest["b01_params_source"] == "report.b01.params"
    for saved, checked in zip(report["steps"], manifest["steps"]):
        op, meta = saved["op"], saved["meta"]
        expected_class = "B" if op in ("standardize", "continuum") else "A" if op in ("pca", "mnf", "ica", "snv") else "C"
        assert checked["method_class"] == expected_class
        assert checked["method_check"] == ("not_applicable" if expected_class == "C" else "matched")
        if "axis_len" not in meta:
            assert checked["axis_branch"] == 1
            assert checked["wavelengths_present"] is None
        elif meta["axis_len"] is None:
            assert checked["axis_branch"] == 2 and checked["axis_digest_match"] is None
            assert checked["wavelengths_present"] is False
        else:
            source = np.asarray(saved["params"]["source"], dtype=np.float64)
            axis = source[(source >= saved["params"]["range"][0]) & (source <= saved["params"]["range"][1])] if op == "crop" else np.asarray(saved["params"]["target"], dtype=np.float64)
            assert checked["axis_branch"] == 3 and checked["axis_digest_match"] is True
            assert checked["wavelengths_present"] is True
            assert checked["axis_sha256"] == sha256(np.ascontiguousarray(axis).tobytes(order="C")).hexdigest()
            assert checked["axis_len"] == len(axis) == output_bands
    assert path.read_bytes() == before and inventory(c.header.parent) == source_before
    assert {item["kind"] for item in report["outputs"]["artifacts"]} == {"report", "sample_spectra"}
    assert manifest["fitting_pixels"] == 110
    assert manifest["input_bands"] == 8 and manifest["output_bands"] == output_bands
    for key in ("run_id", "recipe_pipeline_sha256", "recipe_hash_alg", "input_fingerprint", "code_version"):
        assert manifest[key] == report[key]


@pytest.mark.parametrize("op,params,mutate", [
    ("snv", {}, lambda r: r["steps"][0]["meta"].update(method="wrong")),
    ("standardize", {"method": "standard"}, lambda r: r["steps"][0]["meta"].update(fitted=[])),
    ("standardize", {"method": "minmax"}, lambda r: r["steps"][0]["meta"].update(method="standardize")),
    ("pca", {"n_components": 3}, lambda r: r["steps"][0]["meta"].update(axis_sha256="0"*64)),
    ("crop", {"source": AXIS, "range": [2., 6.]}, lambda r: r["steps"][0]["meta"].update(axis_len=99)),
    ("resample", {"source": AXIS, "target": AXIS, "method": "linear"}, lambda r: r["steps"][0]["meta"].update(axis_sha256="0"*64)),
    ("snv", {}, lambda r: r["b01"]["meta"].update(guard="keep")),
    ("snv", {}, lambda r: r["steps"][0].update(op="unknown")),
])
def test_malformed_calibration_fails_each_axis_and_method_branch(run_case, op, params, mutate):
    c = run_case
    row = c.runner.run(c.cube, c.version, c.recipe([step(op, **params)]))
    assert row["status"] == "succeeded", row["error"]
    report = c.report(row)
    mutate(report)
    with pytest.raises(PreprocessError) as error:
        replay_from_report(report, c.values[0])
    assert error.value.code == "EXPORT_CALIBRATION_MISMATCH"


@pytest.mark.parametrize("op", ["msc", "emsc"])
def test_unreplayable_real_run_rejected_without_any_export_write(run_case, monkeypatch, op):
    c = run_case
    t = np.linspace(0., 1., 8)
    reference = np.sin(7*t)+.3*np.cos(11*t)+2
    # Same non-polynomial construction as conftest.reference, on this cube's 8 bands.
    assert np.linalg.matrix_rank(np.column_stack([reference, np.ones(8), t, t*t])) == 4
    row = c.runner.run(c.cube, c.version, c.recipe([step(op, reference=reference.tolist())]))
    assert row["status"] == "succeeded", row["error"]
    directory = report_path(c, row).parent
    before = inventory(directory)
    monkeypatch.setattr("spectrumagent.preprocess.export.storage.resolve_write", lambda *_a, **_k: pytest.fail("must reject before writing"))
    with pytest.raises(PreprocessError) as error:
        export_run(c.runner, row["id"])
    assert error.value.code == "EXPORT_OPERATOR_NOT_REPLAYABLE"
    assert inventory(directory) == before


def test_registration_audit_hashes_idempotence_and_failure_cleanup(run_case, monkeypatch):
    c = run_case
    row = c.runner.run(c.cube, c.version, c.recipe([]))
    assert row["status"] == "succeeded"
    before = report_path(c, row).read_bytes()
    first = export_run(c.runner, row["id"])
    second = export_run(c.runner, row["id"])
    assert first["artifacts"] == second["artifacts"]
    registered = [item for item in c.runner.get(row["id"])["artifacts"] if item["kind"] == "processed_cube"]
    assert len(registered) == 2
    for item in registered:
        file = c.paths.artifact_root/item["relative_path"]
        assert item["sha256"] == sha256(file.read_bytes()).hexdigest()
    with connect_database(c.registry.storage_guard.audit_database) as db:
        assert db.execute("SELECT COUNT(*) FROM write_audit WHERE action='EXPORT_CREATE' AND decision='ALLOW'").fetchone()[0] >= 2
    module = importlib.import_module("spectrumagent.preprocess.export")
    original = module.storage.replace
    def fail_header(source, target):
        if str(source).endswith(".hdr.tmp"):
            raise OSError("injected finalization failure")
        return original(source, target)
    monkeypatch.setattr(module.storage, "replace", fail_header)
    with pytest.raises(OSError, match="injected finalization"):
        export_run(c.runner, row["id"])
    directory = report_path(c, row).parent
    assert {file.name for file in directory.iterdir()} == {"report.json", "sample_spectra.npz"}
    assert not [item for item in c.runner.get(row["id"])["artifacts"] if item["kind"] == "processed_cube"]
    assert report_path(c, row).read_bytes() == before
    assert c.runner.get(row["id"])["status"] == "succeeded"


def test_source_pins_match_actual_report_contract():
    source = (Path(__file__).parents[2]/"spectrumagent/preprocess/export.py").read_text("utf-8")
    assert 'meta["axis"]' not in source and "meta['axis']" not in source
    # The constant-name comparison is guarded by A; B compares to params.method.
    assert 'if method_class == "A" and meta["method"] != op:' in source
    assert 'if method_class == "B" and meta["method"] != params["method"]:' in source
    assert 'if meta["method"] != op:' not in source


def make_cube_case(tmp_path, shape):
    """Real DN file, 20 fitted pixels, and genuine RunEngine report for G4/G6."""
    source = tmp_path/"source"
    source.mkdir()
    header = source/"pixels.hdr"
    data = header.with_suffix(".img")
    lines, samples, bands = shape
    mapped = np.memmap(data, dtype="<u2", mode="w+", shape=shape)
    pattern = np.broadcast_to(np.arange(bands, dtype=np.uint16)+1000, (min(32, lines), samples, bands))
    for l0 in range(0, lines, 32):
        mapped[l0:l0+32] = pattern[:min(32, lines-l0)]
    mapped.flush()
    mapped._mmap.close()
    header.write_text(f"ENVI\nlines={lines}\nsamples={samples}\nbands={bands}\ndata type=12\ninterleave=bip\nbyte order=0\nreflectance scale factor=65535\n", encoding="utf-8")
    paths = AppPaths(tmp_path/"app")
    registry = DatasetRegistry(paths.database)
    cube = str(registry.import_path(str(header), raw=True).datasets[0].id)
    runner = RunEngine(registry, paths)
    version = str(uuid4())
    label_map = np.full(shape[:2], -1, dtype=np.int32)
    label_map.flat[:20] = 0
    directory = paths.snapshots/cube/"v1"
    directory.mkdir(parents=True)
    np.savez_compressed(directory/"label_map.npz", label_map=label_map)
    with connect_database(paths.database) as db:
        label = db.execute("SELECT id FROM label ORDER BY sort_order,code LIMIT 1").fetchone()[0]
        db.execute("INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,params,created_at) VALUES (?,?,1,?,?,20,'{}','fixture')",
                   (version, cube, f"{cube}/v1", lines*samples))
    (directory/"label_index.json").write_text(json.dumps({"0": label}), encoding="utf-8")
    recipe = runner.recipes.create(str(uuid4()), "export fixture", None, {"steps": []})["versions"][0]["id"]
    row = runner.run(cube, version, recipe)
    assert row["status"] == "succeeded", row["error"]
    return SimpleNamespace(paths=paths, registry=registry, runner=runner, row=row, header=header, shape=shape)


def test_470mb_export_rss_is_bounded_against_half_size_and_incremental_hash(tmp_path):
    # 2400*512*200*2 = 491,520,000 bytes, 468.75 MiB of real source DN.
    script = '''import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path('src-python').resolve()))
# Match isolated_storage_policy: system temp must not contain source fixtures.
tempfile.tempdir=sys.argv[3]
from backend.paths import AppPaths
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.preprocess.run import RunEngine,peak_rss
from spectrumagent.preprocess.export import export_run
p=AppPaths(Path(sys.argv[1])); r=RunEngine(DatasetRegistry(p.database),p)
baseline=peak_rss(); result=export_run(r,sys.argv[2])
m=json.loads((p.artifact_root/result['manifest_relative_path']).read_text('utf-8'))
print(json.dumps(dict(baseline=baseline,peak=m['peak_rss_bytes'],result=result)))
'''
    readings = []
    for lines in (1200, 2400):
        directory = tmp_path/str(lines)
        directory.mkdir()
        c = make_cube_case(directory, (lines, 512, 200))
        process = subprocess.run([sys.executable, "-c", script, str(c.paths.root), c.row["id"], tempfile.gettempdir()],
                                 cwd=Path(__file__).parents[3], capture_output=True, text=True)
        assert process.returncode == 0, process.stderr
        value = json.loads(process.stdout.splitlines()[-1])
        image = c.paths.artifact_root/next(item["relative_path"] for item in value["result"]["artifacts"] if item["relative_path"].endswith(".img"))
        digest = sha256()
        with image.open("rb") as stream:
            for block in iter(lambda: stream.read(65536), b""):
                digest.update(block)
        whole_digest = file_sha256(image)
        assert digest.hexdigest() == whole_digest
        assert image.stat().st_size == lines*512*200*4
        assert c.header.with_suffix(".img").stat().st_size == lines*512*200*2
        value.update(source_bytes=lines*512*200*2, output_bytes=image.stat().st_size,
                     incremental_sha256=digest.hexdigest(), whole_file_sha256=whole_digest)
        readings.append(value)
    single_block_float64 = 32*512*200*8
    increases = [max(0, value["peak"]-value["baseline"]) for value in readings]
    (tmp_path/"rss-evidence.json").write_text(json.dumps(readings, indent=2), encoding="utf-8")
    assert max(increases) < 12*single_block_float64
    assert increases[1] < increases[0]+4*single_block_float64


def test_real_over_8mib_export_streams_in_fixed_chunks_and_legacy_guard_stays(tmp_path):
    from fastapi.testclient import TestClient
    from backend.identity import EngineIdentity
    from spectrumagent.app import create_app
    from spectrumagent.api.preprocess import MAX_ARTIFACT_BYTES, _export_chunks
    c = make_cube_case(tmp_path, (96, 128, 200))
    identity = EngineIdentity()
    app = create_app(c.paths, identity)
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer '+identity.token
        url = '/api/v1/preprocess/runs/'+c.row['id']
        result = client.post(url+'/exports')
        assert result.status_code == 200, result.text
        entry = next(item for item in result.json()['artifacts'] if item['relative_path'].endswith('.img'))
        assert entry['bytes'] == 96*128*200*4 > MAX_ARTIFACT_BYTES
        response = client.get(url+'/exports/processed_cube.img')
        assert response.status_code == 200
        assert sha256(response.content).hexdigest() == entry['sha256']
        assert 'processed_cube.img' in response.headers['content-disposition']
        blocked = client.get(url+'/artifacts/processed_cube')
        assert blocked.status_code == 400 and blocked.json()['error'] == 'ARTIFACT_TOO_LARGE'
        sizes, chunk_digest = [], sha256()
        for block in _export_chunks(c.paths.artifact_root/entry['relative_path']):
            sizes.append(len(block)); chunk_digest.update(block)
        assert max(sizes) == 1024*1024 and min(sizes) > 0
        assert sum(sizes) == entry['bytes'] and len(sizes) > 8
        assert chunk_digest.hexdigest() == entry['sha256']
