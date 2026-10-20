"""R14: six acceptance cases; readers/import classification remain unchanged."""
from uuid import uuid4

import numpy as np
import pytest

from spectrumagent.api.registry import DatasetRegistry, read_header
from spectrumagent.annotation.engines.superpixels import Parameters, SuperpixelEngine
from spectrumagent.data import DataError


@pytest.fixture
def registered_source(tmp_path):
    values = np.random.default_rng(14).integers(0, 65535, (16, 24, 6), dtype=np.uint16)
    binary = tmp_path / "source.img"
    binary.write_bytes(values.transpose(0, 2, 1).tobytes())
    header = tmp_path / "source.hdr"
    header.write_text("ENVI\nsamples=24\nlines=16\nbands=6\ndata type=12\ninterleave=bil\nbyte order=0\nreflectance scale factor=65535\n", "utf-8")
    registry = DatasetRegistry(tmp_path / "registry.sqlite3")
    identifier = registry.import_path(str(header)).datasets[0].id
    return registry, identifier, header, binary


def assert_missing_source(error, header):
    assert error.code == "SOURCE_CHANGED"
    assert error.payload.context["source_error"] == "FILE_NOT_FOUND"
    assert error.payload.context["path"] == str(header.resolve())
    assert error.payload.context["source_detail"] == error.__cause__.payload.detail
    assert isinstance(error.__cause__, DataError)


def test_r14_01_deleted_hdr_preserves_source_context(registered_source, monkeypatch):
    registry, identifier, header, _ = registered_source
    header.unlink()
    with pytest.raises(DataError) as caught:
        registry.readable(identifier)
    assert_missing_source(caught.value, header)
    # Import classification stays FILE_NOT_FOUND, outside readable's wrapper.
    with pytest.raises(DataError) as imported:
        registry.import_path(str(header))
    assert imported.value.code == "FILE_NOT_FOUND"
    # Reserved context fields cannot collide with wrapper-owned fields.
    original = DataError("HEADER_INVALID", "原始失败", path=str(header),
                         source_error="stale", source_detail="stale")
    def failing_reader(*args, **kwargs):
        raise original
    monkeypatch.setattr("spectrumagent.api.registry.read_header", failing_reader)
    with pytest.raises(DataError) as collision:
        registry.readable(identifier)
    assert collision.value.payload.context == {"path": str(header), "source_error": "HEADER_INVALID", "source_detail": "原始失败"}
    assert collision.value.__cause__ is original


def test_r14_02_renamed_hdr_is_source_changed(registered_source):
    registry, identifier, header, _ = registered_source
    header.rename(header.with_name("moved.hdr"))
    with pytest.raises(DataError) as caught:
        registry.readable(identifier)
    assert_missing_source(caught.value, header)


def test_r14_03_smaller_binary_preserves_observed_reader_code(registered_source):
    registry, identifier, header, binary = registered_source
    binary.write_bytes(b"\0\0")
    with pytest.raises(DataError) as reader:
        read_header(header, binary)
    print(f"R14 smaller binary observed reader code: {reader.value.code}")
    assert reader.value.code == "SIZE_MISMATCH"  # Observed by the standalone E:-drive probe.
    with pytest.raises(DataError) as caught:
        registry.readable(identifier)
    assert caught.value.code == "SOURCE_CHANGED"
    assert caught.value.payload.context["source_error"] == reader.value.code
    assert caught.value.payload.context["source_detail"] == reader.value.payload.detail
    assert caught.value.payload.context["path"] == str(binary.resolve())
    assert caught.value.__cause__.code == reader.value.code


def test_r14_04_unknown_id_remains_not_found_404(registered_source, label_api):
    registry, _, _, _ = registered_source
    unknown = uuid4()
    with pytest.raises(DataError) as caught:
        registry.readable(unknown)
    assert caught.value.code == "DATASET_NOT_FOUND"
    assert caught.value.__cause__ is None
    client, _, _ = label_api
    for method, path, body in (
        ("GET", f"/api/v1/datasets/{unknown}", None),
        ("GET", f"/api/v1/datasets/{unknown}/preview", None),
        ("POST", f"/api/v1/datasets/{unknown}/superpixels", {}),
    ):
        response = client.request(method, path, **({"json": body} if body is not None else {}))
        assert response.status_code == 404 and response.json()["error"] == "DATASET_NOT_FOUND"


def test_r14_05_cached_engine_revalidates_deleted_source_without_force(registered_source):
    registry, identifier, header, _ = registered_source
    engine = SuperpixelEngine(registry)
    params = Parameters(n_segments=16)
    first = engine.generate(identifier, params)
    assert engine.generate(identifier, params) is first
    header.unlink()
    with pytest.raises(DataError) as caught:
        engine.generate(identifier, params)
    assert_missing_source(caught.value, header)


def test_r14_06_http_preview_and_superpixels_return_source_changed_400(registered_source, label_api):
    _, _, header, _ = registered_source
    client, _, _ = label_api
    identifier = client.post("/api/v1/datasets/import", json={"path": str(header)}).json()["datasets"][0]["id"]
    header.unlink()
    for method, suffix, body in (("GET", "preview", None), ("POST", "superpixels", {}),
                                 ("POST", "band/0", {"l1": 1, "s1": 1}),
                                 ("POST", "region", {"l1": 1, "s1": 1})):
        response = client.request(method, f"/api/v1/datasets/{identifier}/{suffix}",
                                  **({"json": body} if body is not None else {}))
        assert response.status_code == 400 and response.json()["error"] == "SOURCE_CHANGED"
        assert response.json()["context"]["source_error"] == "FILE_NOT_FOUND"
    assert client.get(f"/api/v1/datasets/{identifier}").status_code == 200
