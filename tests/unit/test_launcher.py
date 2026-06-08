# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for orchestrator.launcher.

All external I/O (subprocess, httpx, webbrowser, time.sleep) is mocked so
that the suite runs without Docker and without network access.
"""

from __future__ import annotations

import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(returncode: int = 0, stderr: str = "") -> CompletedProcess[str]:
    """Build a fake CompletedProcess."""
    return CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


# ---------------------------------------------------------------------------
# up()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUp:
    def test_nominal(self) -> None:
        """up() calls docker compose up -d and returns normally on success."""
        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            from orchestrator.launcher import up

            up()

        mock_run.assert_called_once()
        cmd: list[str] = mock_run.call_args[0][0]
        assert "docker" in cmd
        assert "up" in cmd
        assert "-d" in cmd

    def test_docker_not_found_exits(self) -> None:
        """up() calls sys.exit(1) when Docker is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError("docker not found")):
            from orchestrator.launcher import up

            with pytest.raises(SystemExit) as exc_info:
                up()

        assert exc_info.value.code == 1

    def test_nonzero_returncode_exits(self) -> None:
        """up() calls sys.exit(1) when compose returns non-zero."""
        with patch(
            "subprocess.run",
            return_value=_completed(1, stderr="some compose error"),
        ):
            from orchestrator.launcher import up

            with pytest.raises(SystemExit) as exc_info:
                up()

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# down()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDown:
    def test_nominal(self) -> None:
        """down() calls docker compose down and returns normally on success."""
        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            from orchestrator.launcher import down

            down()

        mock_run.assert_called_once()
        cmd: list[str] = mock_run.call_args[0][0]
        assert "docker" in cmd
        assert "down" in cmd

    def test_docker_not_found_exits(self) -> None:
        """down() calls sys.exit(1) when Docker is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            from orchestrator.launcher import down

            with pytest.raises(SystemExit) as exc_info:
                down()

        assert exc_info.value.code == 1

    def test_nonzero_returncode_exits(self) -> None:
        """down() calls sys.exit(1) when compose returns non-zero."""
        with patch("subprocess.run", return_value=_completed(2, stderr="error")):
            from orchestrator.launcher import down

            with pytest.raises(SystemExit) as exc_info:
                down()

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# wait_healthy()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWaitHealthy:
    def test_healthy_on_first_attempt(self) -> None:
        """wait_healthy() returns immediately when the first poll succeeds."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with (
            patch("httpx.get", return_value=mock_resp) as mock_get,
            patch("time.sleep") as mock_sleep,
        ):
            from orchestrator.launcher import wait_healthy

            wait_healthy(timeout=30)

        mock_get.assert_called_once()
        mock_sleep.assert_not_called()

    def test_retries_then_succeeds(self) -> None:
        """wait_healthy() retries on failure and returns when it eventually gets 200."""
        fail_resp = MagicMock()
        fail_resp.status_code = 503
        ok_resp = MagicMock()
        ok_resp.status_code = 200

        with (
            patch("httpx.get", side_effect=[fail_resp, fail_resp, ok_resp]),
            patch("time.sleep"),
            patch("time.monotonic", side_effect=[0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 100.0]),
        ):
            from orchestrator.launcher import wait_healthy

            wait_healthy(timeout=60)

    def test_timeout_exits(self) -> None:
        """wait_healthy() calls sys.exit(1) after timeout is exceeded."""
        import httpx as _httpx

        with (
            patch(
                "httpx.get",
                side_effect=_httpx.TransportError("connection refused"),
            ),
            patch("time.sleep"),
            # Simulate time advancing past the deadline after one iteration.
            patch(
                "time.monotonic",
                side_effect=[0.0, 0.0, 0.5, 999.0, 999.0],
            ),
            # Suppress the compose log dump attempt during timeout handling.
            patch("subprocess.run", return_value=_completed(0)),
        ):
            from orchestrator.launcher import wait_healthy

            with pytest.raises(SystemExit) as exc_info:
                wait_healthy(timeout=1)

        assert exc_info.value.code == 1

    def test_non_200_status_eventually_times_out(self) -> None:
        """wait_healthy() exits(1) when API consistently returns non-200."""
        bad_resp = MagicMock()
        bad_resp.status_code = 503

        # Enough monotonic values to exhaust the loop and hit the deadline.
        monotonic_values = [float(i) for i in range(20)]

        with (
            patch("httpx.get", return_value=bad_resp),
            patch("time.sleep"),
            patch("time.monotonic", side_effect=monotonic_values),
            patch("subprocess.run", return_value=_completed(0)),
        ):
            from orchestrator.launcher import wait_healthy

            with pytest.raises(SystemExit) as exc_info:
                wait_healthy(timeout=1)

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# open_browser()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpenBrowser:
    def test_opens_spa_when_frontend_present(self, tmp_path: Path) -> None:
        """open_browser() targets / when frontend/dist/index.html exists."""
        # Patch _FRONTEND_MARKER to point at a real file in tmp_path.
        marker = tmp_path / "index.html"
        marker.touch()

        with (
            patch("orchestrator.launcher._FRONTEND_MARKER", marker),
            patch("webbrowser.open") as mock_open,
        ):
            from orchestrator.launcher import open_browser

            open_browser()

        mock_open.assert_called_once_with("http://127.0.0.1:8000/")

    def test_opens_api_docs_when_no_frontend(self, tmp_path: Path) -> None:
        """open_browser() targets /api/docs when the frontend bundle is absent."""
        missing_marker = tmp_path / "does_not_exist" / "index.html"

        with (
            patch("orchestrator.launcher._FRONTEND_MARKER", missing_marker),
            patch("webbrowser.open") as mock_open,
        ):
            from orchestrator.launcher import open_browser

            open_browser()

        mock_open.assert_called_once_with("http://127.0.0.1:8000/api/docs")

    def test_explicit_url_overrides_detection(self) -> None:
        """open_browser(url=...) opens the given URL regardless of frontend presence."""
        with patch("webbrowser.open") as mock_open:
            from orchestrator.launcher import open_browser

            open_browser(url="http://custom.local:9000/")

        mock_open.assert_called_once_with("http://custom.local:9000/")


# ---------------------------------------------------------------------------
# __main__ CLI integration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMainCLI:
    """Test the __main__ entry point argument parsing and dispatch."""

    def _make_mocks(self) -> dict[str, MagicMock]:
        return {
            "up": MagicMock(),
            "wait_healthy": MagicMock(),
            "open_browser": MagicMock(),
            "down": MagicMock(),
        }

    def _run_main(self, argv: list[str]) -> dict[str, MagicMock]:
        """Invoke ``orchestrator.launcher.__main__.main`` with the given argv."""
        import orchestrator.launcher.__main__ as launcher_main

        mocks = self._make_mocks()
        with (
            patch.object(launcher_main, "up", mocks["up"]),
            patch.object(launcher_main, "wait_healthy", mocks["wait_healthy"]),
            patch.object(launcher_main, "open_browser", mocks["open_browser"]),
            patch.object(launcher_main, "down", mocks["down"]),
            patch.object(sys, "argv", ["orchestrator.launcher", *argv]),
        ):
            launcher_main.main()

        return mocks

    def test_default_start_flow(self) -> None:
        """Default invocation calls up → wait_healthy → open_browser."""
        mocks = self._run_main([])
        mocks["up"].assert_called_once()
        mocks["wait_healthy"].assert_called_once()
        mocks["open_browser"].assert_called_once()
        mocks["down"].assert_not_called()

    def test_no_browser_skips_open(self) -> None:
        """``--no-browser`` skips the webbrowser call."""
        mocks = self._run_main(["--no-browser"])
        mocks["open_browser"].assert_not_called()
        mocks["up"].assert_called_once()

    def test_down_flag(self) -> None:
        """``--down`` calls down() and exits without calling up or open_browser."""
        import orchestrator.launcher.__main__ as launcher_main

        mocks = self._make_mocks()
        with (
            patch.object(launcher_main, "up", mocks["up"]),
            patch.object(launcher_main, "wait_healthy", mocks["wait_healthy"]),
            patch.object(launcher_main, "open_browser", mocks["open_browser"]),
            patch.object(launcher_main, "down", mocks["down"]),
            patch.object(sys, "argv", ["orchestrator.launcher", "--down"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            launcher_main.main()

        assert exc_info.value.code == 0
        mocks["down"].assert_called_once()
        mocks["up"].assert_not_called()
        mocks["open_browser"].assert_not_called()

    def test_timeout_passed_to_wait_healthy(self) -> None:
        """``--timeout 90`` passes 90 to wait_healthy."""
        mocks = self._run_main(["--timeout", "90"])
        mocks["wait_healthy"].assert_called_once_with(timeout=90)
