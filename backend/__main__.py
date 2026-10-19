"""Dispatch diagnostics before engine boot; dispatch frozen workers before both."""

import multiprocessing
import os
import sys
from pathlib import Path

# Source execution needs the same package root that PyInstaller's pathex uses.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src-python"))


def main(argv=None) -> int:
    from backend.paths import AppPaths
    from backend.logging_config import configure_logging

    import structlog

    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) == 2 and arguments[0] == "--data-root":
        root = Path(arguments[1])
        if not root.is_absolute() or "\0" in arguments[1]:
            print("--data-root 必须是有效绝对路径", file=sys.stderr)
            return 2
        paths = AppPaths(root)
        arguments = []
    else:
        paths = AppPaths.from_environment()
    configure_logging(paths.logs)
    logger = structlog.get_logger("engine")
    try:
        if arguments == ["--selfcheck-geotiff"]:
            from backend.diagnostics import check_geotiff

            logger.info("diagnostic_started", diagnostic="geotiff", pid=os.getpid())
            check_geotiff(paths)
        elif arguments == ["--selfcheck-worker"]:
            from backend.diagnostics import check_worker

            logger.info("diagnostic_started", diagnostic="worker", pid=os.getpid())
            check_worker(paths)
        elif arguments:
            logger.error("command_rejected", error="UNKNOWN_ARGUMENT")
            return 2
        else:
            logger.info("engine_boot", pid=os.getpid())
            from backend.engine import main as run_engine

            run_engine(paths)
        return 0
    except Exception as exc:
        if hasattr(exc, "code"):
            logger.error("engine_start_failed", error=exc.code)
            print(f"引擎启动失败：{exc.code}；请查看 {paths.logs}", file=sys.stderr)
        else:
            logger.exception("engine_failed")
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
