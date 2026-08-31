"""
FastAPI dependencies, re-exported from one place so routers only need
one import line. Note there is no get_models() here anymore — the API
process doesn't load any ML models at all now (that's the whole point
of the worker split in backend/worker/); routes that need inference
enqueue a Celery task instead. See backend/worker/celery_app.py for
where models actually live.
"""

from backend.core.security import get_current_user  # noqa: F401
from backend.database.db import get_db  # noqa: F401
