"""
Structured JSON logging, using stdlib `logging` only — no new dependency
for this half of observability. Deliberately has NO starlette/FastAPI
import: both the API tier (backend/main.py) and the worker tier
(backend/worker/celery_app.py) use configure_logging()/get_logger() from
here, and the worker's requirements-worker.txt never installs FastAPI's
dependency tree — importing starlette from this module would silently
break the worker image the moment it was actually built. The
request-ID-aware HTTP middleware that layers on top of this (API-only,
genuinely needs starlette) lives in backend/core/request_context.py
instead, kept deliberately separate for exactly that reason.
"""

import json
import logging
import sys
from contextvars import ContextVar

# Exported (not underscore-prefixed) because backend/core/request_context.py sets
# it per-request — the JSON formatter below and that middleware share this state
# across the module boundary deliberately, not as a private leak.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(log_level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())

    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
