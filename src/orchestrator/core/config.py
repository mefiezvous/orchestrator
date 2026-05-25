# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Centralized settings — all env access goes through this module."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    api_token: str = Field(default="", description="Bearer token for API auth")
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)
    allow_lan: bool = Field(default=False)

    workspace_root: Path = Field(default=Path("/workspace"))
    lerobot_repo: Path = Field(default=Path("/workspace/lerobot-playground-portfolio"))

    data_dir: Path = Field(default=Path("/data"))
    database_url: str = Field(default="sqlite:////data/runs.db")
    redis_url: str = Field(default="redis://redis:6379/0")
    mlflow_tracking_uri: str = Field(default="file:///data/mlruns")

    hf_token: str = Field(default="")
    wandb_api_key: str = Field(default="")
    log_level: str = Field(default="INFO")

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def mlruns_dir(self) -> Path:
        # Strip "file://" prefix for filesystem ops
        uri = self.mlflow_tracking_uri
        if uri.startswith("file://"):
            return Path(uri[len("file://") :])
        return self.data_dir / "mlruns"

    @property
    def bind_host(self) -> str:
        return "0.0.0.0" if self.allow_lan else self.api_host


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
