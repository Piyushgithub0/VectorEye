from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine = None
_SessionLocal: sessionmaker | None = None


def _make_engine_url() -> str:
    url = settings.resolve_database_url()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Create a backend/.env file (see .env.example)."
        )
    return url


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            _make_engine_url(),
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables (schema only). PostGIS extension must be enabled on the DB."""
    from . import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=get_engine())


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a scoped DB session."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()