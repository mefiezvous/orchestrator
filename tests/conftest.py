# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Shared pytest fixtures for all test layers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from orchestrator.core.config import Settings, get_settings
from orchestrator.db.models import Base, Run, create_run

# ---------------------------------------------------------------------------
# Filesystem
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory with a logs sub-directory."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings_override(monkeypatch: pytest.MonkeyPatch, tmp_data_dir: Path) -> Settings:
    """Override Settings with an in-process SQLite database and test values.

    Clears the lru_cache on ``get_settings`` so every test starts fresh.
    """
    db_path = tmp_data_dir / "runs.db"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DATA_DIR", str(tmp_data_dir))
    monkeypatch.setenv("API_TOKEN", "test-token")

    # Clear lru_cache so get_settings() picks up the monkeypatched env.
    get_settings.cache_clear()

    settings = get_settings()
    yield settings  # type: ignore[misc]

    # Restore cache state after test.
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine(settings_override: Settings) -> Iterator[Engine]:
    """Create an in-memory (per-test) SQLAlchemy Engine and build the schema."""
    eng = create_engine(
        settings_override.database_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Yield a Session that is rolled back after each test."""
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session: Session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ---------------------------------------------------------------------------
# Run factory
# ---------------------------------------------------------------------------


@pytest.fixture()
def run_factory(db_session: Session) -> Any:
    """Return a callable that creates a Run with sensible defaults."""

    def _factory(
        *,
        job_type: str = "train",
        argv: list[str] | None = None,
        request_body: dict[str, Any] | None = None,
        workspace_cwd: str = "/workspace",
        **overrides: Any,
    ) -> Run:
        run = create_run(
            db_session,
            job_type=job_type,
            argv=argv if argv is not None else ["python", "train.py"],
            request_body=request_body if request_body is not None else {"dataset": "default"},
            workspace_cwd=workspace_cwd,
        )
        for key, value in overrides.items():
            setattr(run, key, value)
        db_session.flush()
        return run

    return _factory
