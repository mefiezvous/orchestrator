# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the root-level bootstrap.py setup script.

bootstrap.py lives outside the orchestrator package (it must run before the
package is installed), so it's loaded here by file path. Only the pure-logic
helper (ensure_env_token) is exercised — the docker/health/browser steps are
orchestrator.launcher's responsibility and are already covered by
test_launcher.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_bootstrap() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "bootstrap_under_test", _REPO_ROOT / "bootstrap.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load bootstrap.py with _REPO_ROOT/_ENV_PATH/_EXAMPLE_PATH redirected to tmp_path."""
    mod = _load_bootstrap()
    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(mod, "_EXAMPLE_PATH", tmp_path / ".env.example")
    return mod


_EXAMPLE_CONTENT = "API_TOKEN=\nAPI_HOST=127.0.0.1\nAPI_PORT=8000\n"


@pytest.mark.unit
class TestEnsureEnvToken:
    def test_seeds_env_from_example_and_fills_token(
        self, bootstrap: ModuleType, tmp_path: Path
    ) -> None:
        """First run: .env doesn't exist yet, gets created from .env.example with a token."""
        (tmp_path / ".env.example").write_text(_EXAMPLE_CONTENT, encoding="utf-8")

        bootstrap.ensure_env_token()

        env_path = tmp_path / ".env"
        assert env_path.is_file()
        text = env_path.read_text(encoding="utf-8")
        assert "API_TOKEN=" in text
        assert "API_TOKEN=\n" not in text  # placeholder line was replaced
        assert "API_HOST=127.0.0.1" in text  # rest of the template preserved

    def test_existing_token_left_untouched(
        self, bootstrap: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Re-running on an .env that already has a token is a no-op (idempotent)."""
        (tmp_path / ".env").write_text(
            "API_TOKEN=already-set-value\nAPI_HOST=127.0.0.1\n", encoding="utf-8"
        )

        bootstrap.ensure_env_token()

        text = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "API_TOKEN=already-set-value" in text
        assert "already set" in capsys.readouterr().out

    def test_appends_token_line_when_missing_from_template(
        self, bootstrap: ModuleType, tmp_path: Path
    ) -> None:
        """If the template has no API_TOKEN= line at all, one is appended."""
        (tmp_path / ".env.example").write_text("API_HOST=127.0.0.1\n", encoding="utf-8")

        bootstrap.ensure_env_token()

        text = (tmp_path / ".env").read_text(encoding="utf-8")
        assert text.count("API_TOKEN=") == 1
        assert "API_HOST=127.0.0.1" in text

    def test_generated_tokens_are_unique(self, bootstrap: ModuleType, tmp_path: Path) -> None:
        """Two fresh setups produce different tokens (secrets.token_urlsafe, not a fixture)."""
        (tmp_path / ".env.example").write_text(_EXAMPLE_CONTENT, encoding="utf-8")
        bootstrap.ensure_env_token()
        first = (tmp_path / ".env").read_text(encoding="utf-8")

        (tmp_path / ".env").unlink()
        bootstrap.ensure_env_token()
        second = (tmp_path / ".env").read_text(encoding="utf-8")

        assert first != second
