"""Windows process identity, including the OS creation time (not import time)."""

import ctypes
import os
import secrets
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from backend import __version__


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def process_created_at() -> str:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
        ctypes.POINTER(wintypes.FILETIME)
    ] * 4
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    creation, exit_time, kernel, user = (wintypes.FILETIME() for _ in range(4))
    if not kernel32.GetProcessTimes(
        kernel32.GetCurrentProcess(),
        ctypes.byref(creation), ctypes.byref(exit_time),
        ctypes.byref(kernel), ctypes.byref(user),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    created = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)
    return created.isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class EngineIdentity:
    boot_id: str = field(default_factory=lambda: secrets.token_hex(4))
    pid: int = field(default_factory=os.getpid)
    process_created_at: str = field(default_factory=process_created_at)
    token: str = field(default_factory=lambda: secrets.token_hex(16))
    monotonic_start: float = field(default_factory=time.monotonic)

    def health(self) -> dict:
        return {
            "status": "ok", "boot_id": self.boot_id, "pid": self.pid,
            "version": __version__,
            "uptime_s": round(time.monotonic() - self.monotonic_start, 3),
        }

    def handshake(self, port: int) -> dict:
        return {
            "boot_id": self.boot_id, "pid": self.pid,
            "process_created_at": self.process_created_at,
            "port": port, "token": self.token, "protocol": 1,
            "version": __version__, "started_at": utc_now(),
        }
