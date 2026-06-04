# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for ORC-001: API_TOKEN must be non-empty at startup."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.core.config import Settings


@pytest.mark.unit
def test_empty_api_token_raises_at_instantiation() -> None:
    """Settings must reject an empty API_TOKEN (fail-closed on auth)."""
    with pytest.raises(ValidationError, match="API_TOKEN must be set"):
        Settings(api_token="", _env_file=None)  # type: ignore[call-arg]


@pytest.mark.unit
def test_valid_api_token_accepted() -> None:
    """A non-empty API_TOKEN must not raise."""
    s = Settings(api_token="supersecrettoken", _env_file=None)  # type: ignore[call-arg]
    assert s.api_token == "supersecrettoken"


@pytest.mark.unit
def test_empty_api_token_rejects_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Startup validation prevents the empty-token pass-through that allowed
    unauthenticated access when API_TOKEN was not set (ORC-001)."""
    # Confirm that Settings() itself raises — i.e. the server cannot start.
    monkeypatch.delenv("API_TOKEN", raising=False)
    from orchestrator.core.config import get_settings

    get_settings.cache_clear()
    try:
        with pytest.raises((ValidationError, Exception), match="API_TOKEN"):
            Settings(_env_file=None)  # type: ignore[call-arg]
    finally:
        get_settings.cache_clear()
