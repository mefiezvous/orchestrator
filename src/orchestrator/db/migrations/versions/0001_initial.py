# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Initial schema — create runs table.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-25

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("argv", sa.JSON(), nullable=False),
        sa.Column("request_body", sa.JSON(), nullable=False),
        sa.Column("workspace_cwd", sa.String(), nullable=False),
        sa.Column("stdout_path", sa.String(), nullable=True),
        sa.Column("stderr_path", sa.String(), nullable=True),
        sa.Column("mlflow_run_id", sa.String(), nullable=True),
        sa.Column("mlflow_tracking_uri", sa.String(), nullable=True),
        sa.Column("hf_repo_id", sa.String(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_status", "runs", ["status"], unique=False)
    op.create_index("ix_runs_job_type", "runs", ["job_type"], unique=False)
    op.create_index("ix_runs_created_at", "runs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_runs_created_at", table_name="runs")
    op.drop_index("ix_runs_job_type", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_table("runs")
