# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""SQLAlchemy engine, session factory, and lifecycle helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from loguru import logger
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from orchestrator.core.config import get_settings

# ---------------------------------------------------------------------------
# Engine (module-level singleton, lazily initialised)
# ---------------------------------------------------------------------------

_engine: Engine | None = None


def _get_engine() -> Engine:
    """Return the singleton Engine, creating it on first call."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        logger.debug("SQLAlchemy engine created for {}", settings.database_url)
    return _engine


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

# sessionmaker is configured lazily via get_session(); bind=None here.
SessionLocal: sessionmaker[Session] = sessionmaker(
    autoflush=False,
    autocommit=False,
)


def get_session() -> Iterator[Session]:
    """Yield a SQLAlchemy Session; usable as a FastAPI ``Depends`` dependency.

    Commits on clean exit, rolls back on any exception, always closes.
    """
    eng = _get_engine()
    session: Session = SessionLocal(bind=eng)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# WAL pragma listener
# ---------------------------------------------------------------------------


def _enable_wal(dbapi_conn: object, _connection_record: object) -> None:
    """Enable WAL journal mode for better concurrent read performance on SQLite."""
    if isinstance(dbapi_conn, sqlite3.Connection):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        logger.debug("SQLite WAL mode enabled")


# ---------------------------------------------------------------------------
# init_db — safety net for tests (production uses alembic upgrade head)
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create schema and data directories.

    This is a **test safety net** — production should rely on ``alembic upgrade head``.
    Enables the WAL pragma on SQLite and calls ``Base.metadata.create_all``.
    """
    from orchestrator.db.models import Base

    settings = get_settings()
    logs_dir = settings.data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("Ensured logs dir at {}", logs_dir)

    eng = _get_engine()
    event.listen(eng, "connect", _enable_wal)
    Base.metadata.create_all(eng)
    logger.info("Database schema initialised via create_all")


# ---------------------------------------------------------------------------
# dispose_engine
# ---------------------------------------------------------------------------


def dispose_engine() -> None:
    """Dispose the engine connection pool (useful for tests / graceful shutdown)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        logger.debug("SQLAlchemy engine disposed")
        _engine = None
