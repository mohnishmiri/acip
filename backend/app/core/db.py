from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_batch_mode = False


def use_batch_mode() -> None:
    """Call before the first DB access in batch processes (worker, CLI) to use the longer
    statement timeout appropriate for ingestion and aggregate rebuilds."""
    global _batch_mode
    if _engine is not None and not _batch_mode:
        reset_engine()
    _batch_mode = True


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            future=True,
        )
        timeout = settings.db_batch_statement_timeout_ms if _batch_mode else settings.db_statement_timeout_ms

        @event.listens_for(_engine, "connect")
        def _on_connect(dbapi_conn, _record):  # pragma: no cover - driver hook
            with dbapi_conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {int(timeout)}")
                cur.execute("SET TIME ZONE 'UTC'")

        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def reset_engine() -> None:
    """Dispose the engine (used by tests that switch databases)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and the worker."""
    db = session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
