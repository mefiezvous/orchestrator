# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Worker entry point — registered as console script ``orchestrator-worker``."""

from __future__ import annotations

import os

from loguru import logger
from redis import Redis
from rq import Queue, Worker

from orchestrator.core.config import get_settings
from orchestrator.core.logging import configure_logging
from orchestrator.db.engine import init_db


def main() -> None:
    """Start the RQ worker and block until interrupted."""
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()  # safety net — alembic should have run already

    conn: Redis = Redis.from_url(settings.redis_url)
    queue = Queue("orchestrator", connection=conn)
    worker_name = f"orchestrator-worker-{os.getpid()}"

    logger.info(
        "orchestrator-worker starting on queue=orchestrator redis={} name={}",
        settings.redis_url,
        worker_name,
    )

    Worker(
        [queue],
        connection=conn,
        name=worker_name,
    ).work(with_scheduler=False, burst=False)
