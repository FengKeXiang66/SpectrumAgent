"""Authenticated smoke headers preserve the sealed JSON and public health contract."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from backend.smoke import SmokeResult

BOOT = "X-SpectrumAgent-Boot-Id"
PID = "X-SpectrumAgent-Pid"
METRICS = {
    "nan_ratio": 0.0, "reflectance_range": [-1.0, 1.0], "bands": 8,
    "shape": [8, 8, 8], "elapsed_ms": 1.0,
}


@pytest.mark.parametrize("status", [200, 409, 500, 422])
def test_authenticated_smoke_identity_and_unchanged_body(tmp_path, monkeypatch, status):
    identity = EngineIdentity()
    result = SmokeResult(METRICS, 1, 8, status == 409)

    async def controlled_smoke(*args):
        if status == 500:
            raise ValueError("controlled smoke failure")
        return result

    monkeypatch.setattr("backend.app.run_smoke", controlled_smoke)
    app = create_app(AppPaths(tmp_path), identity)
    assert [m.kwargs["dispatch"].__name__ for m in app.user_middleware] == [
        "authenticate", "inject_smoke_identity",
    ]
    with TestClient(app) as client:
        response = client.get(
            "/smoke?blocks=0" if status == 422 else "/smoke?blocks=8",
            headers={"Authorization": f"Bearer {identity.token}"},
        )
        assert response.status_code == status
        assert response.headers[BOOT] == identity.boot_id
        assert response.headers[PID] == str(identity.pid)
        assert all(identity.token not in value for value in response.headers.values())
        if status == 200:
            expected = METRICS
        elif status == 409:
            expected = result.cancelled_payload()
        elif status == 500:
            expected = {"error": "SMOKE_FAILED", "detail": "ENVI/SNV 冒烟失败，请查看引擎日志。"}
        else:
            assert set(response.json()) == {"error", "detail"}
            assert response.json()["error"] == "INVALID_REQUEST"
            return
        # Same JSONResponse serialization as before the amendment; no identity in body.
        assert response.content == json.dumps(
            expected, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")


@pytest.mark.parametrize("path,authenticated,status", [
    ("/smoke", False, 401), ("/smoke?blocks=0", False, 401),
    ("/health", False, 200), ("/health", True, 200),
    ("/not-a-route", True, 404), ("/not-a-route", False, 401),
    ("/smokeX", True, 404), ("/smoke/", True, 307),
])
def test_other_responses_do_not_expose_identity(tmp_path, path, authenticated, status):
    identity = EngineIdentity()
    with TestClient(create_app(AppPaths(tmp_path), identity), follow_redirects=False) as client:
        response = client.get(path, headers=(
            {"Authorization": f"Bearer {identity.token}"} if authenticated else {}
        ))
        assert response.status_code == status
        assert BOOT not in response.headers and PID not in response.headers
        assert all(identity.token not in value for value in response.headers.values())
        if path == "/health":
            assert set(response.json()) == {"status", "boot_id", "pid", "version", "uptime_s"}
            assert set(response.headers) == {"content-length", "content-type"}
            assert response.headers["content-type"] == "application/json"
