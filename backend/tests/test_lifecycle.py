import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.handshake import HandshakeError, ownership, publish, remove_if_owned, sweep_stale
from backend.identity import EngineIdentity, process_created_at_for_pid
from backend.paths import AppPaths
from backend.startup_mutex import StartupMutex, StartupMutexError


class Recorder:
    def __init__(self):
        self.events = []

    def info(self, event, **fields):
        self.events.append((event, fields))

    error = warning = exception = info


@pytest.mark.parametrize("actual,expected", [(None, "dead_pid"), ("2000-01-01T00:00:00.000Z", "pid_reused"), ("same", "live_owner")])
def test_old_pid_ownership_branches(actual, expected):
    payload = EngineIdentity().handshake(50001)
    queried = []

    def probe(pid):
        queried.append(pid)
        return payload["process_created_at"] if actual == "same" else actual

    assert ownership(payload, probe=probe) == expected
    assert queried == [payload["pid"]]  # Never compare the old timestamp to the new process.


def test_real_windows_process_identity():
    identity = EngineIdentity()
    assert process_created_at_for_pid(identity.pid) == identity.process_created_at


@pytest.mark.parametrize("actual,reason", [(None, "dead_pid"), ("2000-01-01T00:00:00.000Z", "pid_reused")])
def test_stale_sweep_logs_old_metadata_without_token(tmp_path, monkeypatch, actual, reason):
    import backend.handshake as module

    logger = Recorder()
    monkeypatch.setattr(module, "log", logger)
    path = tmp_path / "handshake.json"
    payload = EngineIdentity().handshake(50001)
    publish(path, payload)
    sweep_stale(path, probe=lambda pid: actual)
    assert not path.exists()
    assert logger.events == [("stale_handshake_removed", {
        "reason": reason, "old_boot_id": payload["boot_id"], "old_pid": payload["pid"],
        "old_process_created_at": payload["process_created_at"], "old_port": payload["port"],
    })]
    assert payload["token"] not in repr(logger.events)


def test_live_owner_and_access_denied_fail_closed(tmp_path):
    path = tmp_path / "handshake.json"
    payload = EngineIdentity().handshake(50001)
    publish(path, payload)
    before = path.read_bytes()
    with pytest.raises(HandshakeError, match="HANDSHAKE_OWNER_ALIVE"):
        sweep_stale(path, probe=lambda pid: payload["process_created_at"])
    assert path.read_bytes() == before

    def denied(pid):
        raise PermissionError("not inspectable")

    with pytest.raises(HandshakeError, match="HANDSHAKE_OWNER_UNVERIFIABLE"):
        sweep_stale(path, probe=denied)
    assert path.read_bytes() == before


@pytest.mark.parametrize("bad", [b"not JSON", b"{}", b'{"token":"do-not-log-this"}', "invalid_time"])
def test_invalid_handshake_fail_closed(tmp_path, monkeypatch, bad):
    import backend.handshake as module

    path = tmp_path / "handshake.json"
    if bad == "invalid_time":
        payload = EngineIdentity().handshake(50001)
        payload["process_created_at"] = "bad-time"
        bad = json.dumps(payload).encode()
    path.write_bytes(bad)
    logger = Recorder()
    monkeypatch.setattr(module, "log", logger)
    with pytest.raises(HandshakeError):
        sweep_stale(path, probe=lambda pid: None)
    assert path.read_bytes() == bad
    assert "do-not-log-this" not in repr(logger.events)


def test_replaced_after_ownership_check_is_not_deleted(tmp_path):
    path = tmp_path / "handshake.json"
    publish(path, EngineIdentity().handshake(50001))
    replacement = EngineIdentity().handshake(50002)

    def replacing_probe(pid):
        publish(path, replacement)
        return None

    with pytest.raises(HandshakeError, match="HANDSHAKE_CHANGED_BEFORE_DELETE"):
        sweep_stale(path, probe=replacing_probe)
    assert json.loads(path.read_bytes()) == replacement


def test_lifespan_owned_cleanup_records_engine_stopped_once(tmp_path, monkeypatch):
    import backend.handshake as module

    logger = Recorder()
    monkeypatch.setattr(module, "log", logger)
    identity = EngineIdentity()
    paths = AppPaths(tmp_path)
    with TestClient(create_app(paths, identity)):
        publish(paths.handshake, identity.handshake(50001))
    assert not paths.handshake.exists()
    assert remove_if_owned(paths.handshake, identity.boot_id) is False
    assert logger.events == [("engine_stopped", {"boot_id": identity.boot_id, "cleanup_phase": "lifespan"})]


def test_foreign_generation_survives_cleanup_and_delete_failure_is_logged(tmp_path, monkeypatch):
    import backend.handshake as module

    path = tmp_path / "handshake.json"
    payload = EngineIdentity().handshake(50001)
    publish(path, payload)
    assert remove_if_owned(path, "00000000") is False
    logger = Recorder()
    monkeypatch.setattr(module, "log", logger)
    real_unlink = type(path).unlink

    def fail_unlink(self, *args, **kwargs):
        if self == path:
            raise PermissionError("denied")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "unlink", fail_unlink)
    with pytest.raises(HandshakeError, match="HANDSHAKE_DELETE_FAILED"):
        remove_if_owned(path, payload["boot_id"])
    assert path.exists()
    assert logger.events[0][0] == "handshake_error"
    assert all(event != "engine_stopped" for event, fields in logger.events)
    assert payload["token"] not in repr(logger.events)


class FakeKernel:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def CreateMutexW(self, attrs, initial_owner, name):
        self.calls.append(("create", initial_owner, name))
        return 123

    def WaitForSingleObject(self, handle, timeout):
        self.calls.append(("wait", handle, timeout))
        return self.result

    def ReleaseMutex(self, handle):
        self.calls.append(("release", handle))
        return True

    def CloseHandle(self, handle):
        self.calls.append(("close", handle))
        return True


@pytest.mark.parametrize("result,owned", [(0, True), (0x80, True), (0x102, False), (0xFFFFFFFF, False)])
def test_mutex_status_and_exact_release_close(result, owned):
    kernel = FakeKernel(result)
    if owned:
        with pytest.raises(RuntimeError, match="startup failed"):
            with StartupMutex(kernel=kernel):
                raise RuntimeError("startup failed")
    else:
        with pytest.raises(StartupMutexError):
            with StartupMutex(kernel=kernel):
                pytest.fail("must not enter without ownership")
    assert kernel.calls[0][1] is False
    assert kernel.calls[0][2].startswith("Local\\")
    assert kernel.calls[1] == ("wait", 123, 30000)
    assert sum(call[0] == "release" for call in kernel.calls) == int(owned)
    assert sum(call[0] == "close" for call in kernel.calls) == 1
    assert kernel.calls[-1] == ("close", 123)


@pytest.mark.parametrize("argument,target", [("--selfcheck-geotiff", "check_geotiff"), ("--selfcheck-worker", "check_worker")])
def test_diagnostics_dispatch_never_imports_engine_or_records_boot(tmp_path, monkeypatch, argument, target):
    import backend.__main__ as entry
    import backend.diagnostics as diagnostics
    import backend.logging_config as logging_config
    import structlog

    logger = Recorder()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(logging_config, "configure_logging", lambda path: None)
    monkeypatch.setattr(structlog, "get_logger", lambda *args: logger)
    monkeypatch.setitem(sys.modules, "backend.engine", None)
    calls = []
    monkeypatch.setattr(diagnostics, target, lambda paths: calls.append(paths.root))
    assert entry.main([argument]) == 0
    assert calls == [tmp_path / "SpectrumAgent"]
    assert [event for event, fields in logger.events] == ["diagnostic_started"]


def test_live_owner_fails_before_uvicorn_startup(tmp_path, monkeypatch):
    import backend.engine as engine

    paths = AppPaths(tmp_path)
    identity = EngineIdentity()
    publish(paths.handshake, identity.handshake(50001))
    reached = []

    async def forbidden_bind(self, sockets=None):
        reached.append("bound")

    monkeypatch.setattr(engine.uvicorn.Server, "startup", forbidden_bind)
    server = engine.HandshakeServer(engine.uvicorn.Config(create_app(paths, identity)), paths, EngineIdentity())
    with pytest.raises(HandshakeError, match="HANDSHAKE_OWNER_ALIVE"):
        asyncio.run(server.startup())
    assert reached == []


def test_acceptance_preflight_cannot_delete_a_live_owners_handshake(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "artifacts/step2/lifecycle_regression.py"
    spec = importlib.util.spec_from_file_location("acceptance_controller_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "handshake.json"
    payload = EngineIdentity().handshake(50001)
    publish(path, payload)
    before = path.read_bytes()
    monkeypatch.setattr(module, "HANDSHAKE", path)
    suite = module.Suite(tmp_path / "evidence", rounds=5)
    assert suite.run() == 1
    assert path.read_bytes() == before
    assert not any(row.get("action") == "remove_owned_residue_after_failure" for row in suite.records)


def test_publish_immediately_releases_mutex_before_ready_log(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import backend.engine as engine

    identity = EngineIdentity()
    paths = AppPaths(tmp_path)
    events = []
    locked = False

    class Mutex:
        def __enter__(self):
            nonlocal locked
            locked = True
            events.append("acquire")

        def __exit__(self, *args):
            nonlocal locked
            locked = False
            events.append("release_and_close")

    def transaction_event(event):
        assert locked
        events.append(event)

    async def startup(self, sockets=None):
        transaction_event("bind")
        self.started = True
        sock = SimpleNamespace(getsockname=lambda: ("127.0.0.1", 50001))
        self.servers = [SimpleNamespace(sockets=[sock])]

    async def get(url):
        transaction_event("health")
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"boot_id": identity.boot_id})

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = get

    class Logger:
        def info(self, event, **fields):
            assert not locked
            events.append(event)

    monkeypatch.setattr(engine, "StartupMutex", Mutex)
    monkeypatch.setattr(engine, "sweep_stale", lambda path: transaction_event("sweep"))
    monkeypatch.setattr(engine, "publish", lambda path, payload: transaction_event("publish"))
    monkeypatch.setattr(engine, "log", Logger())
    monkeypatch.setattr(engine.uvicorn.Server, "startup", startup)
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda **kwargs: client)
    server = engine.HandshakeServer(engine.uvicorn.Config(create_app(paths, identity)), paths, identity)
    asyncio.run(server.startup())
    assert events == ["acquire", "sweep", "bind", "health", "publish", "release_and_close", "engine_ready"]
