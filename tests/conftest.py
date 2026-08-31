import os
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Must be set before any `backend.*` module is imported (backend/database/db.py reads
# DATABASE_URL at import time to build its engine) — isolates the test run from the
# dev-facing backend/database/scaitale.db file, and from needing Postgres at all.
#
# A real temp *file*, not sqlite:///:memory: — SQLAlchemy's connection pool would hand
# out a fresh, empty in-memory DB per connection (each :memory: DB is per-connection),
# so a create_all() on one connection wouldn't be visible to a query on another. A file
# path sidesteps that entirely and is what get_db()'s per-request session pattern is
# meant to be tested against anyway.
_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"scaitale_test_{uuid.uuid4().hex}.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB_PATH.as_posix()}")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-do-not-use-in-production")
# No CELERY_BROKER_URL -> task_always_eager (see backend/worker/celery_app.py) — tests
# never need a real Redis/Celery worker running.
