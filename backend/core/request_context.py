"""
The request-ID-aware HTTP middleware — split out of backend/core/logging.py
specifically because this half genuinely needs starlette, and that module
must not (see its docstring): the worker tier imports logging.py's
configure_logging()/get_logger() directly, and requirements-worker.txt
never installs FastAPI's dependency tree. This file is API-tier only.

Every log line during a request carries the same request_id, and every
response echoes it back as X-Request-ID so client-side error reports and
server logs can be correlated.
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.logging import get_logger, request_id_ctx


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID (or reuses an inbound one), logs method/path/status/duration, echoes it back."""

    def __init__(self, app, logger_name: str = "scaitale.request"):
        super().__init__(app)
        self._logger = get_logger(logger_name)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        token = request_id_ctx.set(request_id)
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
            request_id_ctx.reset(token)
