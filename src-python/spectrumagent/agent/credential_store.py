"""Per-user encrypted-at-rest storage for the LLM API key.

2026-11-12 ruling (supersedes TASK-07 §10-1): a saved key must survive an
engine restart without ever being written to disk in plaintext. On Windows,
DPAPI ``CryptProtectData`` binds the ciphertext to the current OS user account;
only that opaque blob is stored, as one file under the per-user application
data root. The plaintext never enters SQLite, logs, artifacts, exports,
stdout or the filesystem.

Non-Windows platforms have no DPAPI. There the store degrades to no
persistence (``save`` returns False, ``load`` returns None) and the engine
keeps the former process-memory-only behaviour, rather than silently writing
an unencrypted credential.

The in-memory container in ``llm.py`` remains the only runtime holder:
restoring a key is an explicit startup action in ``api/settings.py``.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys

MAGIC = b"SPECTRUMAGENT-LLM-KEY-v1\0"
DIRECTORY = "credentials"
FILENAME = "llm_api_key.bin"
_DESCRIPTION = "SpectrumAgent LLM API key"
_UI_FORBIDDEN = 0x01


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _api():
    """Bind the DPAPI entry points once, or return None off Windows."""
    if sys.platform != "win32":
        return None
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    signature = [ctypes.POINTER(_DataBlob), wintypes.LPCWSTR,
                 ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                 wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    for name in ("CryptProtectData", "CryptUnprotectData"):
        function = getattr(crypt32, name)
        function.argtypes = signature
        function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


_API = _api()


def available() -> bool:
    """Whether this platform can persist a credential without plaintext."""
    return _API is not None


def credential_path(root: Path) -> Path:
    return Path(root) / DIRECTORY / FILENAME


def _blob(data: bytes):
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _transform(name: str, data: bytes) -> bytes:
    crypt32, kernel32 = _API
    # A local reference keeps the input buffer alive until the OS call returns;
    # DPAPI copies it synchronously and allocates its own output blob.
    source, _keepalive = _blob(data)
    target = _DataBlob()
    function = getattr(crypt32, name)
    if not function(ctypes.byref(source), _DESCRIPTION, None, None, None,
                    _UI_FORBIDDEN, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))


def save(root: Path, key: str) -> bool:
    """Encrypt and atomically persist ``key``. False means no OS crypto available.

    A failed write leaves any previous file intact and propagates the error:
    the caller must not report a key as configured for future restarts when it
    was not actually saved.
    """
    if _API is None or not key:
        return False
    cipher = _transform("CryptProtectData", key.encode("utf-8"))
    path = credential_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with open(temporary, "wb") as handle:
            handle.write(MAGIC)
            handle.write(cipher)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return True


def load(root: Path) -> str | None:
    """Return the restored key, or None when absent, corrupt or undecryptable.

    A DPAPI blob cannot be decrypted by another OS user or after a credential
    reset. That is a legitimate "not configured" state, never a startup crash.
    No error text (which could carry provider detail) is logged or returned.
    """
    if _API is None:
        return None
    try:
        raw = credential_path(root).read_bytes()
    except OSError:
        return None
    if not raw.startswith(MAGIC) or len(raw) == len(MAGIC):
        return None
    try:
        plain = _transform("CryptUnprotectData", raw[len(MAGIC):]).decode("utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return plain or None


def clear(root: Path) -> None:
    """Remove the saved blob so an empty key cannot be resurrected on restart."""
    credential_path(root).unlink(missing_ok=True)
