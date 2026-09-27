"""JSON-lines logging to `data/logs/hoctap.log` and the console (stdlib `logging`)."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path

_MARKER = "_hoctap_handler"

# Attributes present on every LogRecord; anything else was passed via `extra=`.
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def __init__(self, ensure_ascii: bool = False) -> None:
        super().__init__()
        self.ensure_ascii = ensure_ascii

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=self.ensure_ascii, default=str)


def configure_logging(logs_dir: Path, level: str = "INFO") -> Path:
    """Install the file + console handlers on the root logger (idempotent)."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "hoctap.log"

    root = logging.getLogger()
    shutdown_logging()

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter(ensure_ascii=False))
    # ASCII-escaped on the console so a Windows cp1252 console never fails on Vietnamese.
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(JsonFormatter(ensure_ascii=True))
    for handler in (file_handler, console):
        setattr(handler, _MARKER, True)
        root.addHandler(handler)
    root.setLevel(level)
    return log_file


def shutdown_logging() -> None:
    """Remove and close the handlers installed by `configure_logging` (releases the file)."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _MARKER, False):
            root.removeHandler(handler)
            handler.close()
