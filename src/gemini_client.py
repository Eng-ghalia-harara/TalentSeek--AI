from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, TypeVar

from google import genai
from google.genai import errors, types


_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")
_KEY_COOLDOWN_SECONDS = 30.0
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
_MAX_SERVICE_FAILURE_ATTEMPTS = 2


def _configured_api_keys() -> list[str]:
    keys: list[str] = []
    key_list = os.getenv("GEMINI_API_KEYS", "")
    keys.extend(key.strip() for key in re.split(r"[,;\r\n]", key_list) if key.strip())

    single_key = os.getenv("GEMINI_API_KEY", "").strip()
    if single_key:
        keys.append(single_key)

    numbered_keys = sorted(
        (
            (int(match.group(1)), value.strip())
            for name, value in os.environ.items()
            if (match := re.fullmatch(r"GEMINI_API_KEY_?(\d+)", name))
            and value.strip()
        ),
        key=lambda item: item[0],
    )
    keys.extend(value for _, value in numbered_keys)
    return list(dict.fromkeys(keys))


@dataclass
class _KeyState:
    client: genai.Client
    disabled: bool = False
    cooldown_until: float = 0.0


class GeminiKeyPool:
    def __init__(
        self,
        api_keys: list[str],
        client_factory: Callable[[str], genai.Client] | None = None,
        cooldown_seconds: float = _KEY_COOLDOWN_SECONDS,
    ) -> None:
        unique_keys = list(dict.fromkeys(key.strip() for key in api_keys if key.strip()))
        if not unique_keys:
            raise RuntimeError(
                "No Gemini API keys are configured. Set GEMINI_API_KEY or GEMINI_API_KEY1."
            )
        factory = client_factory or self._create_client
        self._states = [_KeyState(factory(key)) for key in unique_keys]
        self._cooldown_seconds = cooldown_seconds
        self._next_index = 0
        self._lock = threading.Lock()

    @staticmethod
    def _create_client(api_key: str) -> genai.Client:
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=60_000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def _next_available(self, attempted: set[int]) -> tuple[int, genai.Client] | None:
        with self._lock:
            now = time.monotonic()
            for offset in range(len(self._states)):
                index = (self._next_index + offset) % len(self._states)
                state = self._states[index]
                if index not in attempted and not state.disabled and now >= state.cooldown_until:
                    self._next_index = (index + 1) % len(self._states)
                    return index, state.client
        return None

    def call(self, operation: Callable[[genai.Client], _T]) -> _T:
        attempted: set[int] = set()
        last_error: Exception | None = None
        service_failure_attempts = 0

        while True:
            selected = self._next_available(attempted)
            if selected is None:
                if last_error is not None:
                    raise last_error
                raise RuntimeError("All configured Gemini API keys are disabled or cooling down.")

            index, client = selected
            attempted.add(index)
            try:
                return operation(client)
            except errors.APIError as exc:
                status_code = int(exc.code)
                if status_code in {401, 403}:
                    with self._lock:
                        self._states[index].disabled = True
                elif status_code == 429:
                    with self._lock:
                        self._states[index].cooldown_until = (
                            time.monotonic() + self._cooldown_seconds
                        )
                elif status_code not in _RETRYABLE_STATUS_CODES:
                    raise
                else:
                    service_failure_attempts += 1
                    if service_failure_attempts >= _MAX_SERVICE_FAILURE_ATTEMPTS:
                        _LOGGER.warning(
                            "Gemini request still failed with HTTP %s after %s attempts.",
                            status_code,
                            service_failure_attempts,
                        )
                        raise

                last_error = exc
                if status_code in {401, 403, 429} or status_code in _RETRYABLE_STATUS_CODES:
                    _LOGGER.warning(
                        "Gemini request failed with HTTP %s using key slot %s; trying another key.",
                        status_code,
                        index + 1,
                    )


@lru_cache(maxsize=1)
def get_gemini_key_pool() -> GeminiKeyPool:
    return GeminiKeyPool(_configured_api_keys())


def call_with_gemini_key(operation: Callable[[genai.Client], _T]) -> _T:
    return get_gemini_key_pool().call(operation)
