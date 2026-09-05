from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine = None
_SessionLocal: sessionmaker | None = None


class ScalarResult:
    def __init__(self, items: list[Any]):
        self._items = items

    def all(self) -> list[Any]:
        return list(self._items)

    def first(self) -> Any | None:
        return self._items[0] if self._items else None


class Result:
    def __init__(self, items: list[Any]):
        self._items = items

    def scalars(self) -> ScalarResult:
        return ScalarResult(self._items)

    def all(self) -> list[Any]:
        return list(self._items)


class InMemoryStore:
    """Thread-safe in-memory store used when DATABASE_URL is not configured.
    
    Allows the frontend and backend to run fully offline without requiring a remote
    Neon PostgreSQL instance with PostGIS.
    """

    def __init__(self) -> None:
        self.orthophotos: dict[int, Any] = {}
        self.features: dict[int, Any] = {}
        self._next_ox_id = 1
        self._next_feat_id = 1
        self._lock = threading.Lock()

    def add(self, obj: Any) -> None:
        import threading
        from datetime import datetime, timezone

        with self._lock:
            cname = obj.__class__.__name__
            if cname == "Orthophoto":
                if not getattr(obj, "id", None):
                    obj.id = self._next_ox_id
                    self._next_ox_id += 1
                if not getattr(obj, "created_at", None):
                    obj.created_at = datetime.now(timezone.utc)
                self.orthophotos[obj.id] = obj
            elif cname == "Feature":
                if not getattr(obj, "id", None):
                    obj.id = self._next_feat_id
                    self._next_feat_id += 1
                if not getattr(obj, "created_at", None):
                    obj.created_at = datetime.now(timezone.utc)
                self.features[obj.id] = obj

    def get(self, model: Any, ident: Any) -> Any | None:
        with self._lock:
            mname = getattr(model, "__name__", "")
            if mname == "Orthophoto":
                return self.orthophotos.get(int(ident))
            elif mname == "Feature":
                return self.features.get(int(ident))
            return None

    def execute(self, stmt: Any) -> Result:
        with self._lock:
            res = list(self.features.values())
            for c in getattr(stmt, "_where_criteria", []):
                col = getattr(getattr(c, "left", None), "name", None)
                op = getattr(getattr(c, "operator", None), "__name__", None)
                val = getattr(getattr(c, "right", None), "value", None)
                if col and op:
                    if op in ("eq", "equal"):
                        res = [f for f in res if getattr(f, col, None) == val]
                    elif op in ("ne", "not_equal", "ne_operator"):
                        res = [f for f in res if getattr(f, col, None) != val]
            sorted_res = sorted(res, key=lambda f: getattr(f, "id", 0))
            return Result(sorted_res)


class InMemorySession:
    def __init__(self, store: InMemoryStore):
        self.store = store

    def __enter__(self) -> InMemorySession:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    def add(self, obj: Any) -> None:
        self.store.add(obj)

    def commit(self) -> None:
        pass

    def refresh(self, obj: Any) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass

    def get(self, model: Any, ident: Any) -> Any | None:
        return self.store.get(model, ident)

    def execute(self, stmt: Any) -> Result:
        return self.store.execute(stmt)


class InMemorySessionMaker:
    def __init__(self, store: InMemoryStore):
        self.store = store

    def __call__(self) -> InMemorySession:
        return InMemorySession(self.store)


_memory_store = InMemoryStore()
_in_memory_sessionmaker = InMemorySessionMaker(_memory_store)


def _make_engine_url() -> str:
    url = settings.resolve_database_url()
    if not url:
        return ""
    return url


def get_engine():
    global _engine
    url = _make_engine_url()
    if not url:
        return None
    if _engine is None:
        _engine = create_engine(
            url,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker():
    global _SessionLocal
    if settings.database_url:
        try:
            engine = get_engine()
            if engine is not None and _SessionLocal is None:
                _SessionLocal = sessionmaker(
                    bind=engine,
                    autoflush=False,
                    expire_on_commit=False,
                )
            if _SessionLocal is not None:
                return _SessionLocal
        except Exception as e:
            print(f"Warning: Failed to connect to DATABASE_URL: {e}. Falling back to in-memory store.")
    return _in_memory_sessionmaker


@contextmanager
def session_scope() -> Iterator[Any]:
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
    """Create tables and enable PostGIS extension on the DB if configured."""
    if not settings.database_url:
        return
    try:
        from . import models  # noqa: F401  (ensure models are registered)
        engine = get_engine()
        if engine is None:
            return

        # First enable PostGIS extension
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

        # Then create tables
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Warning: Database init failed ({e}). VectorEye will use in-memory store.")


def get_db() -> Iterator[Any]:
    """FastAPI dependency that yields a scoped DB session."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()