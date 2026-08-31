"""
SQLAlchemy engine/session setup. DATABASE_URL decides the backend:
Postgres in any real deployment (see backend/database/migrations/ +
deployment/docker-compose.yml), SQLite by default so local dev and
`pytest` need no infrastructure at all. `get_db()` is the FastAPI
dependency every route uses to get a session.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """
    Creates any tables schema migrations haven't already created.
    checkfirst=True (SQLAlchemy's default) makes this a safe no-op
    against a Postgres DB Alembic already migrated — it only fills in
    for SQLite dev/test, where running a full `alembic upgrade head`
    for every test run would be needless overhead. Postgres deployments
    should still run `alembic upgrade head` as the source of truth for
    schema changes (see backend/database/migrations/).
    """
    import backend.models.session  # noqa: F401  (registers models on Base.metadata)
    import backend.models.teacher  # noqa: F401
    import backend.models.user  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
