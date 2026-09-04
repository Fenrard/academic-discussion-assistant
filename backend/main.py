"""
FastAPI entry point — the API tier only. Deliberately loads no ML
models: that used to happen here (CLAUDE.md's "loaded once, passed in"
rule), but every route that needs inference now enqueues a Celery task
instead of running pipeline code inline — see backend/worker/celery_app.py
for where "loaded once" now actually happens (once per worker process).
This keeps the API process lightweight and, critically, means it's
never blocked by CPU-bound work — the bug that started this rearchitecture.

Run with: uvicorn backend.main:app --reload
Worker (separate process): celery -A backend.worker.celery_app worker --loglevel=info
"""

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.api import auth, minutes, sessions, teacher, transcribe
from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger
from backend.core.rate_limit import MaxUploadSizeMiddleware, limiter
from backend.core.request_context import RequestContextMiddleware
from backend.database.db import init_db

configure_logging(settings.log_level)
_logger = get_logger("scaitale.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.environment == "production" and not os.environ.get("JWT_SECRET_KEY"):
        # Fail loudly at startup, not on the first login attempt — a production
        # deployment with no signing key is misconfigured, not merely degraded.
        _logger.error("JWT_SECRET_KEY is not set in a production environment. Refusing to start.")
        sys.exit(1)

    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, traces_sample_rate=0.1)
        _logger.info("Sentry initialized.")

    init_db()
    _logger.info(f"Scaitale API starting up (environment={settings.environment}).")
    yield
    _logger.info("Scaitale API shutting down.")


app = FastAPI(title="Scaitale API", version="0.2.0", lifespan=lifespan)

# --- Rate limiting (backend/core/rate_limit.py) ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Middleware (order matters: outermost first) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(MaxUploadSizeMiddleware)

# --- Observability ---
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# --- Routes, versioned ---
API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(transcribe.router, prefix=API_PREFIX)
app.include_router(sessions.router, prefix=API_PREFIX)
app.include_router(teacher.router, prefix=API_PREFIX)
app.include_router(minutes.router, prefix=API_PREFIX)


@app.get("/health")
def health_check(request: Request):
    """Liveness only — doesn't touch the DB or worker tier, matching the /health convention most orchestrators expect."""
    return {"status": "ok", "environment": settings.environment}
