import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import struct
import sys
from threading import Barrier, Event
import zlib

from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app
from spectrumagent.api.registry import DatasetRegistry

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from cubes import cube


class SafeIdentity:
    """Do not let pytest's fixture diagnostics print a credential-bearing repr."""
    def __init__(self, identity):
        self.identity = identity

    def __getattr__(self, name):
        return getattr(self.identity, name)

    def __repr__(self):
        return "SafeIdentity(token=<redacted>)"


@pytest.fixture
def api(tmp_path):
    identity = EngineIdentity()
    paths = AppPaths(tmp_path / "app")
    app = create_app(paths, identity)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        yield client, paths, SafeIdentity(identity)


def imported(client, path, **extra):
    result = client.post("/api/v1/datasets/import", json={"path": str(path), **extra})
    assert result.status_code == 200, result.text
    return result.json()


def test_import_idempotency_raw_persistence_and_overrides(api, tmp_path):
    client, paths, _ = api
    header, _, dn = cube(tmp_path / "source")
    first = imported(client, header, raw=True)
    assert set(first) == {"datasets", "summary"}
    assert first["summary"] == {"total": 1, "imported": 1, "existing": 0}
    record = first["datasets"][0]
    assert set(record) == {"id", "dataset", "existing"}
    again = imported(client, header.parent / "." / header.name, raw=True)
    assert again["datasets"][0]["id"] == record["id"] and again["datasets"][0]["existing"]
    assert again["summary"] == {"total": 1, "imported": 0, "existing": 1}
    persisted, raw = DatasetRegistry(paths.database).get(record["id"])
    assert raw is True and persisted.metadata["value_mode"] == "raw_dn"
    body = {"l0": 0, "l1": 2, "s0": 0, "s1": 3}
    endpoint = f"/api/v1/datasets/{record['id']}/band/2"
    response = client.post(endpoint, json=body)
    assert response.json()["raw"] is True
    np.testing.assert_array_equal(response.json()["values"], dn[:, :, 2])
    response = client.post(endpoint, json=dict(body, raw=False))
    assert response.json()["raw"] is False
    np.testing.assert_array_equal(response.json()["values"], dn[:, :, 2].astype(np.float64) / 65535)
    scaled = imported(client, header, raw=False)
    assert scaled["datasets"][0]["id"] != record["id"]
    region = client.post(f"/api/v1/datasets/{record['id']}/region", json=dict(body, raw=False))
    assert region.json()["shape"] == [2, 3, 4]
    np.testing.assert_array_equal(region.json()["values"], dn.astype(np.float64)/65535)


def test_directory_atomic_all_errors_and_no_source_write(api, tmp_path, monkeypatch):
    client, paths, _ = api
    source = tmp_path / "source"
    good, data, _ = cube(source / "good")
    bad, _, _ = cube(source / "bad")
    bad.write_text("ENVI\nbands=4", "utf-8")
    other = source / "broken.hdr"; other.write_text("bad", "utf-8")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.rglob("*") if p.is_file()}
    response = client.post("/api/v1/datasets/import", json={"path": str(source)})
    assert response.status_code == 400
    assert response.json()["error"] == "IMPORT_BATCH_INVALID"
    assert len(response.json()["context"]["items"]) == 2
    with sqlite3.connect(paths.database) as db:
        assert db.execute("SELECT count(*) FROM dataset_registry").fetchone()[0] == 0
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.rglob("*") if p.is_file()}


def test_directory_names_unrelated_text_and_metadata_only(api, tmp_path, monkeypatch):
    client, _, _ = api
    source = tmp_path / "source"
    cube(source / "a"); cube(source / "b")
    (source / "README.txt").write_text("unrelated readme", "utf-8")
    monkeypatch.setattr("spectral.io.bilfile.BilFile.asarray", lambda *_a, **_k: pytest.fail("import read data values"))
    result = imported(client, source)
    assert result["summary"]["imported"] == 2
    assert {r["dataset"]["name"] for r in result["datasets"]} == {"a/sample.hdr", "b/sample.hdr"}


def test_existing_entries_also_get_unambiguous_directory_names(api, tmp_path):
    client, _, _ = api
    first = cube(tmp_path / "source/a")[0]
    second = cube(tmp_path / "source/b")[0]
    ids = {imported(client, path)["datasets"][0]["id"] for path in (first, second)}
    batch = imported(client, tmp_path / "source")
    assert batch["summary"] == {"total": 2, "imported": 0, "existing": 2}
    assert {r["id"] for r in batch["datasets"]} == ids
    assert len({r["dataset"]["name"] for r in batch["datasets"]}) == 2


def test_concurrent_retries_create_only_one_id(api, tmp_path):
    client, _, _ = api
    header = cube(tmp_path / "source")[0]
    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(lambda _: imported(client, header), range(3)))
    assert len({r["datasets"][0]["id"] for r in results}) == 1
    assert sum(r["summary"]["imported"] for r in results) == 1


def test_preview_png_pixel_orientation_and_bounds(api, tmp_path):
    client, _, _ = api
    header, _, dn = cube(tmp_path / "source")
    identifier = imported(client, header)["datasets"][0]["id"]
    preview = client.get(f"/api/v1/datasets/{identifier}/preview?band=1")
    assert preview.status_code == 200
    info = preview.json()
    assert (info["width"], info["height"]) == (3, 2)
    binary = base64.b64decode(info["png_base64"])
    assert binary[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", binary[16:24]) == (3, 2)
    offset = 8; compressed = b""
    while offset < len(binary):
        size = struct.unpack(">I", binary[offset:offset+4])[0]
        if binary[offset+4:offset+8] == b"IDAT":
            compressed += binary[offset+8:offset+8+size]
        offset += 12 + size
    rows = np.frombuffer(zlib.decompress(compressed), dtype="u1").reshape(2, 4)
    assert np.all(rows[:, 0] == 0)
    expected = (dn[:, :, 1].astype(np.float64) / 65535)
    expected = ((expected-expected.min())/(expected.max()-expected.min())*255).astype("u1")
    np.testing.assert_array_equal(rows[:, 1:], expected)
    assert client.get(f"/api/v1/datasets/{identifier}/preview?band=99").status_code == 400


@pytest.mark.parametrize("failure", ["missing", "corrupt", "undersize", "oversize", "empty"])
def test_invalid_files_http400(api, tmp_path, failure):
    client, _, _ = api
    if failure == "empty":
        source = tmp_path / "empty"; source.mkdir()
    elif failure == "missing":
        source = tmp_path / "absent.hdr"
    else:
        source, data, _ = cube(tmp_path / "source")
        if failure == "corrupt":
            source.write_text("broken", "utf-8")
        else:
            with data.open("r+b") as stream:
                stream.truncate(data.stat().st_size + (1 if failure == "oversize" else -1))
    response = client.post("/api/v1/datasets/import", json={"path": str(source)})
    assert response.status_code == 400 and set(response.json()) == {"error", "detail", "context"}


def test_three_imports_do_not_block_health(api, tmp_path, monkeypatch):
    client, _, _ = api
    import spectrumagent.api.registry as registry
    original = registry.read_header
    entered = Barrier(4); release = Event()
    def slow(*args, **kwargs):
        entered.wait(timeout=10)
        assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(registry, "read_header", slow)
    paths = [cube(tmp_path / str(i))[0] for i in range(3)]
    with ThreadPoolExecutor(3) as pool:
        futures = [pool.submit(imported, client, p) for p in paths]
        try:
            entered.wait(timeout=10)
            assert client.get("/health").status_code == 200
        finally:
            release.set()
        assert all(f.result()["summary"]["imported"] == 1 for f in futures)


def test_auth_identity_and_validation(api, tmp_path):
    client, _, identity = api
    path, _, _ = cube(tmp_path / "source")
    unauth = client.post("/api/v1/datasets/import", json={"path": str(path)}, headers={"Authorization": ""})
    assert unauth.status_code == 401 and "X-SpectrumAgent-Pid" not in unauth.headers
    result = client.post("/api/v1/datasets/import", json={"path": str(path), "raw": "true"})
    assert result.status_code == 400
    assert result.headers["X-SpectrumAgent-Boot-Id"] == identity.boot_id
    assert result.headers["X-SpectrumAgent-Pid"] == str(identity.pid)
    health = client.get("/health")
    assert set(health.json()) == {"status", "boot_id", "pid", "version", "uptime_s"}
    assert "X-SpectrumAgent-Pid" not in health.headers
    assert identity.token not in result.text and identity.token not in str(result.headers)


def test_api_schema_snapshot(api):
    client, _, _ = api
    expected = json.loads((Path(__file__).parents[2] / "spectrumagent/api/openapi.json").read_text("utf-8"))
    assert client.app.openapi() == expected
