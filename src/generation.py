from __future__ import annotations

import json
from typing import Any, Callable

from google import genai
from google.genai import types

from src.config import GENERATION_MODEL
from src.gemini_client import call_with_gemini_key
from src.timing import timed


def _partial_json_string(text: str, key: str) -> str | None:
    marker = f'"{key}"'
    key_start = text.find(marker)
    if key_start < 0:
        return None
    value_start = text.find(":", key_start + len(marker)) + 1
    while value_start < len(text) and text[value_start].isspace():
        value_start += 1
    if value_start >= len(text) or text[value_start] != '"':
        return None

    content_start = value_start + 1
    escaped = False
    closing_quote = None
    for index in range(content_start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            closing_quote = index
            break

    if closing_quote is not None:
        encoded = text[value_start:closing_quote + 1]
    else:
        partial = text[content_start:]
        last_escape = partial.rfind("\\")
        if last_escape >= 0:
            escape = partial[last_escape:]
            if escape == "\\" or (escape.startswith("\\u") and len(escape) < 6):
                partial = partial[:last_escape]
        encoded = '"' + partial + '"'

    try:
        value = json.loads(encoded)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, str) else None


def generate_json(
    prompt: str,
    on_summary_update: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Generate a compact JSON response with a bounded request time."""
    try:
        def generate_with_client(client: genai.Client) -> tuple[list[str], dict[str, int]]:
            response_text: list[str] = []
            last_summary = ""
            usage: dict[str, int] = {}
            stream = client.models.generate_content_stream(
                model=GENERATION_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.LOW
                    ),
                ),
            )
            for chunk in stream:
                text_chunk = getattr(chunk, "text", None) or ""
                chunk_usage = getattr(chunk, "usage_metadata", None)
                if chunk_usage is not None:
                    for source, target in (
                        ("prompt_token_count", "prompt_tokens"),
                        ("candidates_token_count", "output_tokens"),
                        ("total_token_count", "total_tokens"),
                    ):
                        value = getattr(chunk_usage, source, None)
                        if value is not None:
                            usage[target] = int(value)
                if not text_chunk:
                    continue
                response_text.append(text_chunk)
                if on_summary_update is not None:
                    summary = _partial_json_string("".join(response_text), "summary")
                    if summary is not None and summary != last_summary:
                        on_summary_update(summary)
                        last_summary = summary
            return response_text, usage

        with timed("Gemini generation API request"):
            response_text, usage = call_with_gemini_key(generate_with_client)

        text = "".join(response_text).strip()
        if not text:
            raise ValueError("Gemini returned an empty response.")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object from Gemini.")
        if usage:
            data["_usage"] = usage
        return data
    except Exception as exc:
        raise RuntimeError(f"Generation failed: {exc}") from exc
