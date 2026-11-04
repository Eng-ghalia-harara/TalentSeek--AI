from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from google.genai import types

from src import config
from src.gemini_client import call_with_gemini_key
from src.timing import timed


class GeminiService:
    """Gemini Embedding 2 and Gemini Flash generation service."""

    def __init__(self) -> None:
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.cache_file = config.CACHE_DIR / "embedding_cache.jsonl"
        self.cache: dict[str, list[float]] = {}
        self.last_embedding_usage: dict[str, Any] = {}
        if self.cache_file.exists():
            with self.cache_file.open("r", encoding="utf-8") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                        if row.get("model") == config.EMBEDDING_MODEL and row.get("dimension") == config.EMBEDDING_DIM:
                            self.cache[row["key"]] = row["vector"]
                    except (ValueError, KeyError, TypeError):
                        continue

    def _cache_key(self, text: str) -> str:
        raw = f"{config.EMBEDDING_MODEL}|{config.EMBEDDING_DIM}|{text}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def embed_text(self, text: str) -> list[float]:
        key = self._cache_key(text)
        if key in self.cache:
            self.last_embedding_usage = {"cache_hit": True, "tokens": 0}
            return self.cache[key]

        last_error: Exception | None = None
        for attempt in range(5):
            try:
                with timed(f"Gemini embedding API attempt {attempt + 1}"):
                    response = call_with_gemini_key(
                        lambda client: client.models.embed_content(
                            model=config.EMBEDDING_MODEL,
                            contents=text,
                            config=types.EmbedContentConfig(
                                output_dimensionality=config.EMBEDDING_DIM
                            ),
                        )
                    )
                vector = list(response.embeddings[0].values)
                usage = getattr(response, "usage_metadata", None)
                token_count = getattr(usage, "prompt_token_count", None) if usage else None
                self.last_embedding_usage = {
                    "cache_hit": False,
                    "tokens": int(token_count) if token_count is not None else None,
                }
                if len(vector) != config.EMBEDDING_DIM:
                    raise ValueError(
                        f"Expected {config.EMBEDDING_DIM} dimensions; received {len(vector)}."
                    )
                self.cache[key] = vector
                with self.cache_file.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({
                        "key": key,
                        "model": config.EMBEDDING_MODEL,
                        "dimension": config.EMBEDDING_DIM,
                        "vector": vector,
                    }) + "\n")
                return vector
            except Exception as exc:
                last_error = exc
                if attempt < 4:
                    time.sleep(min(2 ** attempt, 12))
        raise RuntimeError(f"Embedding request failed after retries: {last_error}") from last_error

    def embed_document(self, text: str, title: str, section: str) -> list[float]:
        # Gemini Embedding 2 retrieval-document format: title + text.
        # Add the section to the title field so section context is retained.
        document_title = f"{title} — {section}"
        prepared = f"title: {document_title} | text: {text}"
        return self.embed_text(prepared)

    def embed_query(self, query: str) -> list[float]:
        prepared = f"task: search result | query: {query}"
        return self.embed_text(prepared)
