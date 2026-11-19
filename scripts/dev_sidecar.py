r"""DEV ONLY: source sidecar for milestone02; never used by release resources.

Interpreter: E:\AI_Agent\.venv\Scripts\python.exe (CPython3.12.13).
The Rust supervisor supplies --data-root and still owns suspended launch/Job.
"""
import argparse
import multiprocessing
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src-python"), str(ROOT)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    if not args.data_root.is_absolute():
        parser.error("--data-root must be absolute")
    from backend.paths import AppPaths
    from backend.logging_config import configure_logging
    import structlog
    paths = AppPaths(args.data_root)
    paths.create_directories()
    configure_logging(paths.logs)
    log = structlog.get_logger("engine")
    try:
        if sys.version_info[:3] != (3, 12, 13):
            log.error("dev_python_version_rejected", version=list(sys.version_info[:3]))
            return 1
        import uvicorn
        from backend.engine import HandshakeServer
        from backend.handshake import HandshakeError, remove_if_owned
        from backend.identity import EngineIdentity
        from spectrumagent.app import create_app
        identity = EngineIdentity()
        structlog.contextvars.bind_contextvars(boot_id=identity.boot_id, pid=identity.pid)
        log.info("engine_boot", runtime="dev_python", python=sys.version.split()[0])
        server = HandshakeServer(uvicorn.Config(create_app(paths, identity), host="127.0.0.1", port=0, workers=1, log_config=None, access_log=True, timeout_graceful_shutdown=5), paths, identity)
        try:
            server.run()
        finally:
            try:
                remove_if_owned(paths.handshake, identity.boot_id, phase="finally")
            except HandshakeError as error:
                log.error("engine_final_cleanup_failed", error=error.code)
        return 0
    except Exception as error:
        if hasattr(error, "code"):
            log.error("engine_start_failed", error=error.code)
        else:
            log.exception("dev_engine_failed")
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
