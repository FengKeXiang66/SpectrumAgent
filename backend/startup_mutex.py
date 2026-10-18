"""Session-local serialization of the engine's handshake startup transaction."""

import ctypes
from ctypes import wintypes

import structlog

MUTEX_NAME = r"Local\SpectrumAgent.EngineHandshake.Startup.v1"
log = structlog.get_logger("engine.startup_mutex")


class StartupMutexError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _kernel():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateMutexW.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    for name in ("ReleaseMutex", "CloseHandle"):
        function = getattr(api, name)
        function.argtypes = [wintypes.HANDLE]
        function.restype = wintypes.BOOL
    return api


class StartupMutex:
    def __init__(self, *, timeout_ms: int = 30_000, kernel=None):
        self.kernel = kernel if kernel is not None else _kernel()
        self.timeout_ms = timeout_ms
        self.handle = None
        self.acquired = False

    def __enter__(self):
        self.handle = self.kernel.CreateMutexW(None, False, MUTEX_NAME)
        if not self.handle:
            log.error("startup_mutex_failed", error="STARTUP_MUTEX_CREATE_FAILED")
            raise StartupMutexError("STARTUP_MUTEX_CREATE_FAILED")
        try:
            result = self.kernel.WaitForSingleObject(self.handle, self.timeout_ms)
            if result in (0, 0x80):
                self.acquired = True
                if result == 0x80:
                    log.warning("startup_mutex_abandoned", action="reread_handshake_under_lock")
                return self
            code = "STARTUP_MUTEX_TIMEOUT" if result == 0x102 else "STARTUP_MUTEX_WAIT_FAILED"
            log.error("startup_mutex_failed", error=code, wait_result=result)
            raise StartupMutexError(code)
        except BaseException:
            self._release_and_close()
            raise

    def _release_and_close(self):
        release_ok = True
        if self.acquired:
            self.acquired = False  # Attempt ReleaseMutex exactly once, even on failure.
            release_ok = bool(self.kernel.ReleaseMutex(self.handle))
        close_ok = True
        if self.handle is not None:
            handle, self.handle = self.handle, None
            close_ok = bool(self.kernel.CloseHandle(handle))
        if not release_ok or not close_ok:
            log.error("startup_mutex_release_failed", release_ok=release_ok, close_ok=close_ok)
            raise StartupMutexError("STARTUP_MUTEX_RELEASE_FAILED")

    def __exit__(self, exc_type, exc, traceback):
        self._release_and_close()
