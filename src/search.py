from __future__ import annotations

import re
import time
from typing import Any, Callable

from src.config import DEFAULT_TOP_K, RETRIEVAL_FETCH_K
from src.database import retrieve_chunks
from src.embeddings import GeminiService
from src.generation import generate_json
from src.prompts import build_search_prompt
from src.candidate_matching import group_chunks_by_candidate
from src.experience import add_experience_estimates
from src.safety import redact_personal_contact_data, requests_personal_contact_data
from src.timing import timed


def _fallback_requested_count(question: str) -> int:
    plural_terms = (
        r"\b(engineers|candidates|developers|managers|designers|people)\b",
        r"مرشحين|مرشحون|المهندسين|مهندسين|مهندسون|مهندسات|المطورين|مطوريْن|المرشحين",
    )
    return 3 if any(re.search(pattern, question, re.IGNORECASE) for pattern in plural_terms) else 1


def search_candidates(
    question: str,
    top_k: int = DEFAULT_TOP_K,
    section: str | None = None,
    candidate_ids: list[int] | None = None,
    job_field: str | None = None,
    on_summary_update: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    request_started = time.perf_counter()
    stage_timings: dict[str, float] = {}
    with timed("Search total"):
        question = question.strip()
        if not question:
            raise ValueError("Please enter a search question.")
        if requests_personal_contact_data(question):  # Block personal-contact requests before CV retrieval.
            arabic = bool(re.search(r"[\u0600-\u06FF]", question))
            return {
                "candidates": [],
                "summary": (
                    "لا أستطيع كشف أرقام الهواتف أو عناوين البريد الشخصية للمرشحين. "
                    "يمكنني مساعدتك في مقارنة المرشحين حسب متطلبات الوظيفة."
                    if arabic else
                    "I can’t disclose candidates’ personal phone numbers or email addresses. "
                    "I can compare candidates using job-related criteria instead."
                ),
                "clarification_questions": [],
                "privacy_blocked": True,
            }

        stage_started = time.perf_counter()
        with timed("Create Gemini service and load embedding cache"):
            service = GeminiService()
        stage_timings["embedding_service_setup_seconds"] = round(time.perf_counter() - stage_started, 3)
        stage_started = time.perf_counter()
        with timed("Embed query"):
            query_vector = service.embed_query(question)
        stage_timings["query_embedding_seconds"] = round(time.perf_counter() - stage_started, 3)
        embedding_usage = dict(service.last_embedding_usage)
        stage_started = time.perf_counter()
        with timed("PostgreSQL retrieval (semantic + keyword)"):
            rows = retrieve_chunks(
                query_vector=query_vector,
                query_text=question,
                top_k=max(RETRIEVAL_FETCH_K, top_k * 8),
                section=section,
                candidate_ids=candidate_ids,
                job_field=job_field,
            )
        stage_timings["database_retrieval_seconds"] = round(time.perf_counter() - stage_started, 3)
        stage_started = time.perf_counter()
        with timed("Group and rank candidates"):
            candidates = group_chunks_by_candidate(rows, top_k=top_k)
        stage_timings["candidate_grouping_seconds"] = round(time.perf_counter() - stage_started, 3)
        if not candidates:
            stage_timings["total_seconds"] = round(time.perf_counter() - request_started, 3)
            return {
                "candidates": [],
                "summary": "No matching CV evidence was found.",
                "clarification_questions": [],
                "stage_timings": stage_timings,
                "retrieved_chunk_count": len(rows),
                "embedding_usage": embedding_usage,
            }

        retrieval_trace = [
            {
                "document_id": candidate["document_id"],
                "candidate": candidate["candidate_label"],
                "file_name": candidate["file_name"],
                "retrieval_score": candidate["score"],
                "evidence": [
                    {
                        "chunk_id": item["chunk_id"],
                        "section": item.get("section"),
                        "page_numbers": item.get("page_nums") or [item.get("page_num")],
                        "text": redact_personal_contact_data(str(item.get("content", ""))),
                    }
                    for item in candidate.get("evidence", [])
                ],
            }
            for candidate in candidates
        ]

        as_of = add_experience_estimates(candidates)  # Calculate work duration against today's date.
        with timed("Build generation prompt"):
            prompt = build_search_prompt(question, candidates, as_of=as_of)
        stage_started = time.perf_counter()
        try:
            with timed("Gemini response generation"):
                generated = generate_json(prompt, on_summary_update=on_summary_update)
            stage_timings["generation_seconds"] = round(time.perf_counter() - stage_started, 3)
        except Exception as exc:
            stage_timings["generation_seconds"] = round(time.perf_counter() - stage_started, 3)
            stage_timings["total_seconds"] = round(time.perf_counter() - request_started, 3)
            # Keep search useful when the generation service hits its deadline.
            fallback_candidate_ids = [
                int(candidate["document_id"]) for candidate in candidates
            ]
            requested_count = min(_fallback_requested_count(question), len(candidates))
            return {
                "candidates": candidates,
                "requested_count": requested_count,
                "candidate_assessments": {},
                "recommended_candidate_id": fallback_candidate_ids[0],
                "candidate_pool_ids": fallback_candidate_ids,
                "summary": (
                    "Gemini could not complete its assessment. The first candidate "
                    "below is the highest-ranked retrieval match; review the cited "
                    "CV evidence before drawing a conclusion."
                ),
                "clarification_questions": [],
                "generation_warning": True,
                "generation_error": f"{type(exc).__name__}: {exc}",
                "retrieval_trace": retrieval_trace,
                "retrieved_chunk_count": len(rows),
                "stage_timings": stage_timings,
                "generation_usage": {},
                "embedding_usage": embedding_usage,
            }
        candidate_ids_in_pool = [int(candidate["document_id"]) for candidate in candidates]
        assessments: dict[int, dict[str, str]] = {}
        ranked_ids: list[int] = []
        ranked_candidates = generated.get("ranked_candidates")
        if not isinstance(ranked_candidates, list):
            ranked_candidates = []
        for item in ranked_candidates:
            try:
                document_id = int(item.get("document_id"))
            except (AttributeError, TypeError, ValueError):
                continue
            status = str(item.get("fit_status") or "unclear")
            if document_id not in candidate_ids_in_pool or status not in {
                "meets", "partial", "unclear", "does_not_meet",
            }:
                continue
            assessments[document_id] = {
                "fit_status": status,
                "reason": redact_personal_contact_data(str(item.get("reason") or "")),
            }
            ranked_ids.append(document_id)
        ranked_ids.extend(
            document_id
            for document_id in candidate_ids_in_pool
            if document_id not in ranked_ids
        )
        rank_order = {document_id: index for index, document_id in enumerate(ranked_ids)}
        candidates.sort(key=lambda candidate: rank_order[int(candidate["document_id"])])
        try:
            requested_count = int(generated.get("requested_count", 1))
        except (TypeError, ValueError):
            requested_count = _fallback_requested_count(question)
        requested_count = max(1, min(requested_count, len(candidates), 3))
        recommended_candidate_id = int(candidates[0]["document_id"])
        usage = generated.get("_usage") if isinstance(generated.get("_usage"), dict) else {}
        stage_timings["total_seconds"] = round(time.perf_counter() - request_started, 3)
        return {
            "candidates": candidates,
            "requested_count": requested_count,
            "candidate_assessments": assessments,
            "recommended_candidate_id": recommended_candidate_id,
            "candidate_pool_ids": candidate_ids_in_pool,
            "summary": redact_personal_contact_data(str(generated.get("summary", ""))),
            "clarification_questions": [
                str(q) for q in (generated.get("clarification_questions") or [])[:3]
            ],
            "retrieval_trace": retrieval_trace,
            "retrieved_chunk_count": len(rows),
            "stage_timings": stage_timings,
            "generation_usage": usage,
            "embedding_usage": embedding_usage,
        }
