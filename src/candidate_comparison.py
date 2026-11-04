from __future__ import annotations

from typing import Any

from src.generation import generate_json
from src.prompts import build_comparison_prompt


def compare_candidates(question: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not 2 <= len(candidates) <= 5:
        raise ValueError("Select between 2 and 5 candidates to compare.")
    return generate_json(build_comparison_prompt(question, candidates))
