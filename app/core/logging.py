"""Configuração centralizada de logs (texto estruturado ou JSON) com Request ID."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.core.context import get_request_id

LOGGER_NAME = "taskflow_api"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", get_request_id()),
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)s | %(name)s | req=%(request_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def configure_logging(level: str, log_format: str = "text") -> None:
    root = logging.getLogger(LOGGER_NAME)
    root.setLevel(level)
    root.propagate = True

    formatter: logging.Formatter = JsonFormatter() if log_format == "json" else TextFormatter()
    if not root.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.addFilter(RequestIdFilter())
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)
    else:
        for existing in root.handlers:
            existing.setFormatter(formatter)


def get_logger(suffix: str | None = None) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{suffix}" if suffix else LOGGER_NAME)
