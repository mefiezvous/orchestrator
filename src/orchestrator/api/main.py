# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory and entry point."""

from __future__ import annotations

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from orchestrator import __version__
from orchestrator.api.limiter import limiter
from orchestrator.core.config import get_settings
from orchestrator.core.logging import configure_logging


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="orchestrator",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    # ORC-010: attach the rate-limiter state and middleware.
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )
    app.add_middleware(SlowAPIMiddleware)

    # No CORS by default — frontend must be reverse-proxied or same-origin.
    # CORS opt-in could be added later via env var.

    from orchestrator.api.routes import artifacts, configs, runs, streams, system

    app.include_router(system.router)
    app.include_router(runs.router)
    app.include_router(configs.router)
    app.include_router(artifacts.router)
    app.include_router(streams.router)

    return app


__all__ = ["app", "limiter"]


app = create_app()


def main() -> None:
    """Entry point for `python -m orchestrator.api.main`."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "orchestrator.api.main:app",
        host=settings.bind_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
