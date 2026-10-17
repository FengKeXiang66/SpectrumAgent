"""Source and frozen entry point; keep worker dispatch ahead of engine imports."""

import multiprocessing
import sys


if __name__ == "__main__":
    multiprocessing.freeze_support()

    from backend.paths import AppPaths
    from backend.logging_config import configure_logging

    paths = AppPaths.from_environment()
    configure_logging(paths.logs)

    import structlog

    logger = structlog.get_logger("engine")
    logger.info("engine_boot")
    try:
        if sys.argv[1:] == ["--selfcheck-geotiff"]:
            from backend.diagnostics import check_geotiff

            check_geotiff(paths)
        elif sys.argv[1:] == ["--selfcheck-worker"]:
            from backend.diagnostics import check_worker

            check_worker(paths)
        elif sys.argv[1:]:
            raise ValueError("未知的引擎命令行参数。")
        else:
            from backend.engine import main

            main(paths)
    except Exception:
        logger.exception("engine_failed")
        raise
