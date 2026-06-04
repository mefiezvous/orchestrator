# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Bearer-token authentication dependency for the orchestrator API."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from orchestrator.core.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def require_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Validate the Bearer token; raise HTTP 401 on failure.

    ``API_TOKEN`` is **mandatory** (validated at startup by the Settings validator).
    A valid Bearer token is always required on every request.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="missing bearer token")
    if not secrets.compare_digest(credentials.credentials, settings.api_token):
        raise HTTPException(status_code=401, detail="invalid token")


__all__ = ["require_token"]
