"""One JSON formatter for structlog, uvicorn and standard-library logging."""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import structlog


class DailyJsonFile(logging.Handler):
    """Reopen the named daily file at midnight without renaming previous logs."""

    def __init__(self, directory: Path) -> None:
        super().__init__()
        self.stream = None
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.day = ""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            day = datetime.now().strftime("%Y%m%d")
            if self.stream is None or day != self.day:
                if self.stream is not None:
                    self.stream.close()
                self.stream = (self.directory / f"engine-{day}.jsonl").open(
                    "a", encoding="utf-8"
                )
                self.day = day
            self.stream.write(self.format(record) + "\n")
            self.stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        super().close()


def configure_logging(directory: Path) -> None:
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(
                serializer=json.dumps, ensure_ascii=False, allow_nan=False
            ),
        ],
    )
    handlers: list[logging.Handler] = [DailyJsonFile(directory)]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    root = logging.getLogger()
    for old in root.handlers[:]:
        root.removeHandler(old)
        old.close()
    root.setLevel(logging.INFO)
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
