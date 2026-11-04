from __future__ import annotations

import time
from functools import lru_cache

from src.config import GENERATION_MODEL, TOKEN_COUNT_MODEL
from src.gemini_client import call_with_gemini_key


@lru_cache(maxsize=8192)
def count_gemini_tokens(text: str) -> int:
    """Count tokens through Google's count_tokens API; cached per exact text."""
    if not text or not text.strip():
        return 0
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = call_with_gemini_key(
                lambda client: client.models.count_tokens(
                    model=TOKEN_COUNT_MODEL or GENERATION_MODEL,
                    contents=text,
                )
            )
            return int(response.total_tokens)
        except Exception as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"Gemini token counting failed: {last_error}") from last_error
