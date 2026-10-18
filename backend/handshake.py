"""Fail-closed startup ownership checks and best-effort generation cleanup."""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import structlog

from backend.identity import process_created_at_for_pid

log = structlog.get_logger("engine.handshake")
FIELDS = {"boot_id", "pid", "process_created_at", "port", "token", "protocol", "version", "started_at"}


class HandshakeError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Snapshot:
    raw: bytes
    payload: dict


def _fail(code: str, *, phase: str, payload: dict | None = None):
    metadata = owner_metadata(payload) if payload is not None else {}
    log.error("handshake_error", error=code, phase=phase, **metadata)
    raise HandshakeError(code)


def owner_metadata(payload: dict) -> dict:
    return {f"old_{key}": payload[key] for key in ("boot_id", "pid", "process_created_at", "port")}


def _valid_time(value) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
        return True
    except ValueError:
        return False


def read_snapshot(path: Path, *, phase: str) -> Snapshot | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        _fail("HANDSHAKE_READ_FAILED", phase=phase)
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        _fail("HANDSHAKE_INVALID_JSON", phase=phase)
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        _fail("HANDSHAKE_INVALID_FIELDS", phase=phase)
    valid = (
        isinstance(payload["boot_id"], str)
        and re.fullmatch(r"[0-9a-f]{8}", payload["boot_id"])
        and type(payload["pid"]) is int and 0 < payload["pid"] < 2**32
        and type(payload["port"]) is int and 0 < payload["port"] < 65536
        and type(payload["protocol"]) is int and payload["protocol"] == 1
        and payload["version"] == "0.1.0"
        and isinstance(payload["token"], str) and re.fullmatch(r"[0-9a-f]{32}", payload["token"])
        and _valid_time(payload["process_created_at"]) and _valid_time(payload["started_at"])
    )
    if not valid:
        _fail("HANDSHAKE_INVALID_METADATA", phase=phase)
    return Snapshot(raw, payload)


def ownership(payload: dict, *, probe=None) -> str:
    probe = process_created_at_for_pid if probe is None else probe
    try:
        actual = probe(payload["pid"])
    except OSError:
        _fail("HANDSHAKE_OWNER_UNVERIFIABLE", phase="startup", payload=payload)
    if actual is None:
        return "dead_pid"
    if actual != payload["process_created_at"]:
        return "pid_reused"
    return "live_owner"


def _delete_unchanged(path: Path, snapshot: Snapshot, *, phase: str) -> None:
    try:
        reread = path.read_bytes()
    except OSError:
        _fail("HANDSHAKE_CHANGED_BEFORE_DELETE", phase=phase, payload=snapshot.payload)
    if reread != snapshot.raw:
        _fail("HANDSHAKE_CHANGED_BEFORE_DELETE", phase=phase, payload=snapshot.payload)
    try:
        path.unlink()
    except OSError:
        _fail("HANDSHAKE_DELETE_FAILED", phase=phase, payload=snapshot.payload)


def sweep_stale(path: Path, *, probe=None) -> None:
    """Caller holds the session startup mutex through this call and publication."""
    snapshot = read_snapshot(path, phase="startup")
    if snapshot is None:
        return
    state = ownership(snapshot.payload, probe=probe)
    if state == "live_owner":
        _fail("HANDSHAKE_OWNER_ALIVE", phase="startup", payload=snapshot.payload)
    _delete_unchanged(path, snapshot, phase="startup")
    log.info("stale_handshake_removed", reason=state, **owner_metadata(snapshot.payload))


def publish(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def remove_if_owned(path: Path, boot_id: str, *, phase: str = "finally") -> bool:
    snapshot = read_snapshot(path, phase=phase)
    if snapshot is None or snapshot.payload["boot_id"] != boot_id:
        return False
    _delete_unchanged(path, snapshot, phase=phase)
    log.info("engine_stopped", boot_id=boot_id, cleanup_phase=phase)
    return True
