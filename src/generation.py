from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from groq import Groq

from src.config import GENERATION_MODEL
from src.timing import timed


def _configured_groq_api_keys() -> list[str]:
    keys = [
        key.strip()
        for key in re.split(r"[,;\r\n]", os.getenv("GROQ_API_KEYS", ""))
        if key.strip()
    ]
    single_key = os.getenv("GROQ_API_KEY", "").strip()
    if single_key:
        keys.append(single_key)
    numbered_keys = sorted(
        (
            (int(match.group(1)), value.strip())
            for name, value in os.environ.items()
            if (match := re.fullmatch(r"GROQ_API_KEY_?(\d+)", name)) and value.strip()
        ),
        key=lambda item: item[0],
    )
    keys.extend(value for _, value in numbered_keys)
    return list(dict.fromkeys(keys))


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
        if GENERATION_MODEL.startswith("gemini-"):
            raise RuntimeError(
                f"GENERATION_MODEL={GENERATION_MODEL!r} is a Gemini model ID; "
                "Groq generation needs a Groq model ID such as 'openai/gpt-oss-120b'. "
                "Restart the app after changing .env."
            )
        api_keys = _configured_groq_api_keys()
        if not api_keys:
            raise RuntimeError("No Groq API keys are configured.")

        last_error: Exception | None = None
        for api_key in api_keys:
            try:
                response_text: list[str] = []
                last_summary = ""
                usage: dict[str, int] = {}
                with timed("Groq generation API request"):
                    stream = Groq(api_key=api_key).chat.completions.create(
                        model=GENERATION_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        stream=True,
                    )
                    for chunk in stream:
                        if chunk.usage is not None:
                            usage = {
                                "prompt_tokens": chunk.usage.prompt_tokens,
                                "output_tokens": chunk.usage.completion_tokens,
                                "total_tokens": chunk.usage.total_tokens,
                            }
                        if not chunk.choices:
                            continue
                        text_chunk = chunk.choices[0].delta.content or ""
                        if not text_chunk:
                            continue
                        response_text.append(text_chunk)
                        if on_summary_update is not None:
                            summary = _partial_json_string("".join(response_text), "summary")
                            if summary is not None and summary != last_summary:
                                on_summary_update(summary)
                                last_summary = summary

                text = "".join(response_text).strip()
                if not text:
                    raise ValueError("Groq returned an empty response.")
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object from Groq.")
                if usage:
                    data["_usage"] = usage
                return data
            except Exception as exc:
                last_error = exc

        raise RuntimeError(f"All configured Groq keys failed: {last_error}") from last_error
    except Exception as exc:
        raise RuntimeError(f"Generation failed: {exc}") from exc
