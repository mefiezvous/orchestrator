# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for _sanitize_secret in streams router."""

from __future__ import annotations

import pytest

from orchestrator.api.routes.streams import _sanitize_secret


@pytest.mark.unit
def test_sanitize_bearer_token() -> None:
    line = "Authorization: Bearer abc123xyz"
    result = _sanitize_secret(line)
    assert "abc123xyz" not in result
    assert "Bearer ***" in result


@pytest.mark.unit
def test_sanitize_bearer_token_case_insensitive() -> None:
    line = "auth: bearer MYSECRETTOKEN"
    result = _sanitize_secret(line)
    assert "MYSECRETTOKEN" not in result
    assert "***" in result


@pytest.mark.unit
def test_sanitize_hf_token() -> None:
    line = "HF_TOKEN=hf_abcdefghij123456"
    result = _sanitize_secret(line)
    assert "hf_abcdefghij123456" not in result
    assert "HF_TOKEN=***" in result


@pytest.mark.unit
def test_sanitize_api_token() -> None:
    line = "API_TOKEN=supersecretvalue"
    result = _sanitize_secret(line)
    assert "supersecretvalue" not in result
    assert "API_TOKEN=***" in result


@pytest.mark.unit
def test_sanitize_wandb_api_key() -> None:
    line = "WANDB_API_KEY=abcd1234efgh5678"
    result = _sanitize_secret(line)
    assert "abcd1234efgh5678" not in result
    assert "WANDB_API_KEY=***" in result


@pytest.mark.unit
def test_sanitize_no_secrets_unchanged() -> None:
    line = "Training epoch 1/100, loss=0.42"
    result = _sanitize_secret(line)
    assert result == line


@pytest.mark.unit
def test_sanitize_multiple_secrets_in_one_line() -> None:
    line = "HF_TOKEN=tok1 WANDB_API_KEY=key2 some text"
    result = _sanitize_secret(line)
    assert "tok1" not in result
    assert "key2" not in result
    assert "HF_TOKEN=***" in result
    assert "WANDB_API_KEY=***" in result
