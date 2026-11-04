from __future__ import annotations

import os

import pytest
from google.genai import errors

from src.gemini_client import GeminiKeyPool, _configured_api_keys


def _api_error(status_code: int) -> errors.APIError:
    return errors.APIError(
        status_code,
        {"error": {"message": "test failure", "status": "UNAVAILABLE"}},
    )


def test_configured_keys_include_legacy_numbered_names(monkeypatch) -> None:
    for name in list(os.environ):
        if name.startswith("GEMINI_API_KEY"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "primary")
    monkeypatch.setenv("GEMINI_API_KEY1", "secondary")
    monkeypatch.setenv("GEMINI_API_KEY_2", "tertiary")
    monkeypatch.setenv("GEMINI_API_KEYS", "secondary, fourth")

    assert _configured_api_keys() == ["secondary", "fourth", "primary", "tertiary"]


def test_successful_calls_rotate_round_robin() -> None:
    pool = GeminiKeyPool(["first", "second"], client_factory=lambda key: key)

    assert pool.call(lambda client: client) == "first"
    assert pool.call(lambda client: client) == "second"
    assert pool.call(lambda client: client) == "first"


def test_server_error_fails_over_to_next_key() -> None:
    pool = GeminiKeyPool(["first", "second"], client_factory=lambda key: key)
    attempts: list[str] = []

    def request(client: str) -> str:
        attempts.append(client)
        if client == "first":
            raise _api_error(503)
        return "success"

    assert pool.call(request) == "success"
    assert attempts == ["first", "second"]


def test_service_unavailable_stops_after_one_failover() -> None:
    pool = GeminiKeyPool(["first", "second", "third"], client_factory=lambda key: key)
    attempts: list[str] = []

    def request(client: str) -> str:
        attempts.append(client)
        raise _api_error(503)

    with pytest.raises(errors.APIError):
        pool.call(request)

    assert attempts == ["first", "second"]


def test_invalid_key_is_disabled_after_failover() -> None:
    pool = GeminiKeyPool(["invalid", "valid"], client_factory=lambda key: key)
    attempts: list[str] = []

    def request(client: str) -> str:
        attempts.append(client)
        if client == "invalid":
            raise _api_error(403)
        return client

    assert pool.call(request) == "valid"
    assert pool.call(request) == "valid"
    assert attempts == ["invalid", "valid", "valid"]


def test_rate_limited_key_is_skipped_during_cooldown() -> None:
    pool = GeminiKeyPool(
        ["limited", "available"],
        client_factory=lambda key: key,
        cooldown_seconds=60,
    )

    def request(client: str) -> str:
        if client == "limited":
            raise _api_error(429)
        return client

    assert pool.call(request) == "available"
    assert pool.call(request) == "available"


def test_non_retryable_request_error_is_not_rotated() -> None:
    pool = GeminiKeyPool(["first", "second"], client_factory=lambda key: key)
    attempts: list[str] = []

    def request(client: str) -> str:
        attempts.append(client)
        raise _api_error(400)

    with pytest.raises(errors.APIError):
        pool.call(request)

    assert attempts == ["first"]
