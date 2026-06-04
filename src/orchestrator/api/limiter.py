# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""ORC-010: Shared SlowAPI rate-limiter instance.

Defined in its own module to avoid circular imports between main.py and routes/.
Import ``limiter`` wherever you need ``@limiter.limit(...)`` decorators.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# 60 requests/minute global default; individual routes may add stricter limits.
limiter: Limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

__all__ = ["limiter"]
