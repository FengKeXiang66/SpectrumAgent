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


def process_created_at_for_pid(pid: int) -> str | None:
    """Query the *old* PID's OS identity; None means that process is dead."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
        ctypes.POINTER(wintypes.FILETIME)
    ] * 4
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER for a PID that no longer exists
            return None
        raise ctypes.WinError(error)  # Access denied is ambiguous: caller fails closed.
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        if exit_code.value != 259:  # STILL_ACTIVE
            return None
        creation, exit_time, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        created = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)
        return created.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    finally:
        kernel32.CloseHandle(handle)


def process_created_at() -> str:
    created = process_created_at_for_pid(os.getpid())
    if created is None:
        raise RuntimeError("Current process identity is unavailable")
    return created


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
