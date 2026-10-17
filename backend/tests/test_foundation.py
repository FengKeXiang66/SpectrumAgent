import asyncio
import json
from threading import Event

import numpy as np
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.handshake import publish, remove_if_owned
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from backend.smoke import ensure_sample, run_smoke


def test_http_contract_and_real_envi_snv(tmp_path):
    identity = EngineIdentity()
    with TestClient(create_app(AppPaths(tmp_path), identity)) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert set(health.json()) == {"status", "boot_id", "pid", "version", "uptime_s"}
        assert health.json()["boot_id"] == identity.boot_id
        for path in ("/smoke", "/not-a-route", "/docs"):
            response = client.get(path)
            assert response.status_code == 401
            assert set(response.json()) == {"error", "detail"}
        assert client.get("/smoke", headers={"Authorization": "Bearer wrong"}).status_code == 401
        headers = {"Authorization": f"Bearer {identity.token}"}
        response = client.get("/smoke", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert set(data) == {"nan_ratio", "reflectance_range", "bands", "shape", "elapsed_ms"}
        assert data["shape"] == [8, 8, 8] and data["bands"] == 8
        assert data["nan_ratio"] == 0
        assert np.allclose(data["reflectance_range"], [-1.527525, 1.527525], atol=1e-4)
        chunked = client.get("/smoke?blocks=8", headers=headers)
        assert chunked.status_code == 200
        assert np.allclose(chunked.json()["reflectance_range"], data["reflectance_range"])
        invalid = client.get("/smoke?blocks=0", headers=headers)
        assert invalid.status_code == 422
        assert set(invalid.json()) == {"error", "detail"}


def test_atomic_handshake_and_owner_cleanup(tmp_path, monkeypatch):
    import backend.handshake as handshake

    path = tmp_path / "handshake.json"
    old = {"boot_id": "old"}
    path.write_text(json.dumps(old), encoding="utf-8")
    identity = EngineIdentity()
    payload = identity.handshake(54321)
    assert len(payload["token"]) == 32
    assert set(payload) == {
        "boot_id", "pid", "process_created_at", "port", "token", "protocol", "version", "started_at"
    }
    replace = handshake.os.replace

    def inspect_before_replace(source, destination):
        assert json.loads(path.read_text()) == old
        assert json.loads(source.read_text()) == payload
        replace(source, destination)

    monkeypatch.setattr(handshake.os, "replace", inspect_before_replace)
    publish(path, payload)
    assert json.loads(path.read_text()) == payload
    assert not path.with_suffix(".json.tmp").exists()
    remove_if_owned(path, "another-generation")
    assert path.exists()
    remove_if_owned(path, identity.boot_id)
    assert not path.exists()


def test_cancel_after_first_running_block_keeps_partial_metrics(tmp_path, monkeypatch):
    """Signal while an actual SNV block is running, then forbid the next block."""
    import backend.smoke as smoke

    sample = ensure_sample(tmp_path)
    flag = Event()
    real_to_thread = asyncio.to_thread
    submitted_computations = []

    async def instrumented_to_thread(function, *args, **kwargs):
        result = await real_to_thread(function, *args, **kwargs)
        if function.__name__ == "compute":
            submitted_computations.append(function.__name__)
            flag.set()
        return result

    monkeypatch.setattr(smoke.asyncio, "to_thread", instrumented_to_thread)
    result = asyncio.run(run_smoke(sample, blocks=8, cancel=flag))
    assert submitted_computations == ["compute"]
    assert result.completed_blocks == 1 and result.cancelled
    payload = result.cancelled_payload()
    assert payload["status"] == "cancelled"
    assert payload["metrics_complete"] is False
    assert payload["partial_metrics"]["nan_ratio"] == 0


def test_failed_envi_returns_contract_error(tmp_path):
    identity = EngineIdentity()
    with TestClient(create_app(AppPaths(tmp_path), identity)) as client:
        client.app.state.sample.unlink()
        response = client.get("/smoke", headers={"Authorization": f"Bearer {identity.token}"})
        assert response.status_code == 500
        assert response.json()["error"] == "SMOKE_FAILED"
        assert set(response.json()) == {"error", "detail"}
