"""
Abuse controls: slowapi (a Flask-limiter-style rate limiter for FastAPI/
Starlette) on the endpoints worth protecting, plus a small middleware
rejecting oversized uploads before they're read into memory/disk at all.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.core.config import settings

limiter = Limiter(key_func=get_remote_address)


class MaxUploadSizeMiddleware(BaseHTTPMiddleware):
    """Rejects a request up front via Content-Length, before FastAPI reads the body."""

    def __init__(self, app, max_bytes: int = settings.max_upload_bytes):
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            # A well-behaved client always sends a base-10 integer here; a
            # malformed value (garbage, empty string, whitespace) used to
            # blow up int() with an uncaught ValueError, turning a request
            # this middleware couldn't even evaluate into a raw 500 instead
            # of a clean 4xx. Treated as a bad request, not silently ignored
            # — a genuine client never produces this, so only a
            # malformed/hand-crafted request would hit this path.
            try:
                declared_bytes = int(content_length)
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Malformed Content-Length header."})
            if declared_bytes > self._max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Upload exceeds the {self._max_bytes} byte limit."},
                )
        return await call_next(request)
