"""
Structured JSON logging + a request-ID contextvar, using stdlib
`logging` only — no new dependency for this half of observability.
Every log line during a request carries the same request_id, and every
response echoes it back as X-Request-ID so client-side error reports
and server logs can be correlated.
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _request_id_ctx.get(),
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


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID (or reuses an inbound one), logs method/path/status/duration, echoes it back."""

    def __init__(self, app, logger_name: str = "scaitale.request"):
        super().__init__(app)
        self._logger = get_logger(logger_name)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        token = _request_id_ctx.set(request_id)
        start_time = time.perf_counter()

        try:
            try:
                response = await call_next(request)
            except Exception:
                self._logger.exception(f"{request.method} {request.url.path} raised an unhandled exception")
                raise

            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            self._logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({elapsed_ms}ms)")
            return response
        finally:
            # Reset only after every log line above has used the context — resetting first
            # would make the success-path log line lose its request_id.
            _request_id_ctx.reset(token)
