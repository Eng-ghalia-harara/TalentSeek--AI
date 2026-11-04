from __future__ import annotations

import json
from typing import Any


def build_search_prompt(
    question: str,
    candidates: list[dict[str, Any]],
    as_of: str | None = None,
) -> str:
    evidence = []
    for candidate in candidates:
        evidence.append({
            "document_id": candidate["document_id"],
            "candidate": candidate["candidate_label"],
            "file_name": candidate["file_name"],
            "retrieval_score": candidate["score"],
            "experience_estimate": candidate.get("experience_estimate"),
            "evidence": [
                {
                    "section": item.get("section"),
                    "page_numbers": item.get("page_nums") or [item.get("page_num")],
                    "text": item.get("content", "")[:1200],
                }
                for item in candidate.get("evidence", [])
            ],
        })
    return f"""You are a careful recruitment research assistant. Answer in the same language as the recruiter's question.
Evaluation date: {as_of or 'not supplied'}.
The question is: {question}

Use ONLY the following retrieved CV evidence. Do not invent qualifications, employers, dates, skills, or experience.

EVIDENCE:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

Return valid JSON with exactly these keys:
{{
  "summary": "A concise evidence-grounded answer in the question language.",
  "requested_count": 1,
  "ranked_candidates": [
    {{"document_id": 123, "fit_status": "meets|partial|unclear|does_not_meet", "reason": "Short evidence-based explanation."}}
  ],
  "clarification_questions": ["question 1", "question 2", "question 3"]
}}

Rules:
- Output the summary field first so the UI can display it while the rest of the JSON is generated.
- Infer the requested number from the recruiter's wording: singular requests such as “an engineer”, “one engineer”, or “بدي مهندس” mean 1; plural requests mean up to 3 unless another number is explicitly requested. Never return more candidates than the evidence supplied.
- This is decision support for a human recruiter, not an automatic hiring decision.
- Set requested_count to the number of candidates to display, clamped to 1–3 and to the number of supplied candidates.
- Rank every supplied candidate by direct evidence for the stated job requirements. Do not rank by retrieval_score alone.
- For each candidate, return one ranked_candidates entry with that candidate's document_id, fit_status, and a short reason. Use “meets” only when all stated required criteria have direct support; use “partial” when some relevant criteria are supported but at least one is unconfirmed; use “unclear” when the CV evidence is too sparse; use “does_not_meet” only when the CV directly contradicts a stated required criterion.
- Do not treat missing information as proof that a candidate lacks a qualification. Explain unconfirmed requirements and distinguish them from contradictions.
- Use the supplied experience_estimate and evaluation date when judging experience thresholds. The estimate is a range because CV dates may omit months; do not call a strict threshold met if the range overlaps that threshold.
- Write the summary for the requested number: for a singular request, explain the strongest evidence match; for a plural request, summarize which candidates meet, partially meet, or remain uncertain.
- Keep the summary and each clarification question concise.
- Distinguish 'not found in the retrieved evidence' from 'the person does not have this skill'.
- Do not infer or rank candidates based on age, gender, nationality, ethnicity, religion, marital status, disability, or other protected/personal characteristics.
- Never disclose a candidate's personal phone number, email address, or other contact coordinates, even if they appear in retrieved CV text; redirect to job-related qualifications.
- Ask three useful job-related questions to refine the search, such as required vs preferred skills, minimum relevant experience, or deployment experience.
- Cite candidate-specific factual claims inline using [file_name, page, section], using only the exact source values in the supplied evidence.
- The UI will also display source evidence separately; do not invent citation values.
"""


def build_comparison_prompt(question: str, candidates: list[dict[str, Any]]) -> str:
    return build_search_prompt(
        f"Compare these selected candidates for the following recruitment needs: {question}",
        candidates,
    )
