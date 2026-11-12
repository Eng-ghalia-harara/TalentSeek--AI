from __future__ import annotations

import re
import time
from typing import Any, Callable

from src.config import (
    DEFAULT_TOP_K,
    MAX_EVIDENCE_PER_CANDIDATE,
    RETRIEVAL_FETCH_K,
)
from src.database import get_candidate_contact_texts, retrieve_chunks
from src.embeddings import GeminiService
from src.generation import generate_json
from src.prompts import build_search_prompt
from src.candidate_matching import group_chunks_by_candidate
from src.cv_sanitization import sanitize_cv_text
from src.experience import add_experience_estimates
from src.safety import (
    redact_personal_contact_data,
    extract_personal_contact_data,
    can_access_candidate_contact_data,
    requests_candidate_contact_data,
    requests_personal_contact_data,
)
from src.timing import timed


def _redact_candidate_evidence(candidates: list[dict[str, Any]]) -> None:
    """Keep contact coordinates out of model context and UI unless explicitly requested."""
    for candidate in candidates:
        for evidence in candidate.get("evidence", []):
            evidence["content"] = redact_personal_contact_data(
                str(evidence.get("content", ""))
            )


def _sanitize_candidate_metadata_and_evidence(candidates: list[dict[str, Any]]) -> None:
    """Remove unsafe extracted text from both new and previously indexed CV evidence."""
    retained: list[dict[str, Any]] = []
    for candidate in candidates:
        for field in ("candidate_label", "file_name"):
            candidate[field] = sanitize_cv_text(str(candidate.get(field, ""))).strip()
        candidate["candidate_label"] = candidate["candidate_label"] or f"CV {candidate['document_id']}"
        candidate["file_name"] = candidate["file_name"] or f"cv_{candidate['document_id']}.pdf"
        evidence = []
        for item in candidate.get("evidence", []):
            content = sanitize_cv_text(str(item.get("content", ""))).strip()
            if content:
                evidence.append({**item, "content": content})
        candidate["evidence"] = evidence
        if candidate["evidence"]:
            scores = sorted(
                (float(item.get("rrf_score") or 0) for item in evidence),
                reverse=True,
            )
            candidate["score"] = (scores[0] if scores else 0.0) + 0.25 * sum(scores[1:3])
            retained.append(candidate)
    candidates[:] = sorted(retained, key=lambda item: item["score"], reverse=True)


def _attach_contact_details(
    candidates: list[dict[str, Any]],
    eligible_document_ids: set[int],
    texts_by_document: dict[int, list[str]],
) -> None:
    for candidate in candidates:
        document_id = int(candidate["document_id"])
        if document_id not in eligible_document_ids:
            continue
        details = extract_personal_contact_data(texts_by_document.get(document_id, []))
        if details["emails"] or details["phones"]:
            candidate["contact_details"] = details


def _search_mode(question: str) -> str:
    """Classify whether the recruiter wants a shortlist, a ranked list, or an exhaustive filter."""
    text = question.casefold()
    ranking_terms = (
        r"\b(best|top|recommend|recommendation|hire|select|choose)\b",
        r"أفضل|الافضل|رش[ّ ]?ح|أوظف|اوظف|اختار|اختيار|توظيف",
    )
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in ranking_terms):
        return "rank"
    filter_patterns = (
        r"^\s*(?:find|show|list)?\s*(?:all\s+)?candidates?\s+(?:(?:located|based)\s+)?(?:in|with|having|who|that)\b",
        r"\b(which|who)\s+(?:are\s+)?(?:the\s+)?candidates?\b",
        r"\bwho\s+(?:has|have)\b",
        r"\b(all|each)\s+candidates?\b",
        r"مين\s+(?:هم\s+)?(?:المرشحين|المرشحون|المرشحات)",
        r"مين\s+(?:عنده|عندها|عندهم|لديه|لديها)",
        r"من\s+(?:هم\s+)?(?:المرشحين|المرشحون|المرشحات)",
        r"من\s+(?:عنده|عندها|عندهم|لديه|لديها)",
        r"(?:كل|جميع)\s+(?:ال)?مرشحين",
    )
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in filter_patterns):
        return "filter"
    return "shortlist"


def _fallback_requested_count(question: str) -> int:
    plural_terms = (
        r"\b(engineers|candidates|developers|managers|designers|people)\b",
        r"مرشحين|مرشحون|المهندسين|مهندسين|مهندسون|مهندسات|المطورين|مطوريْن|المرشحين",
    )
    return 3 if any(re.search(pattern, question, re.IGNORECASE) for pattern in plural_terms) else 1


def _requests_work_experience_evidence(question: str) -> bool:
    patterns = (
        r"\b(experience|experienced|worked|work history|employment|employed|training|trainer)\b",
        r"خبرة|خبرات|خبرته|خبرتها|اشتغل|يشتغل|عمل\s+(?:في|ب|مع)|العمل\s+في|"
        r"تدريب|مدرب|مدربة|درّب|يدرب|سنوات\s+العمل",
    )
    return any(re.search(pattern, question, re.IGNORECASE) for pattern in patterns)


def _required_sections_for_question(question: str) -> tuple[str, ...]:
    sections: list[str] = []
    if _requests_work_experience_evidence(question):
        sections.append("Work Experience")
    if re.search(
        r"\b(certifications?|certificates?|certified|licenses?|licences?)\b|"
        r"شهادة|شهادات|حاصل\s+على\s+شهادة|معه\s+شهادة",
        question,
        re.IGNORECASE,
    ):
        sections.append("Certifications")
    if re.search(
        r"\b(master(?:'s)?|bachelor(?:'s)?|ph\.?d|doctorate|degree|education)\b|"
        r"ماجستير|بكالوريوس|دكتوراه|مؤهل(?:ات)?\s+علمية",
        question,
        re.IGNORECASE,
    ):
        sections.append("Education")
    if re.search(
        r"\bprojects?\b|مشروع|مشاريع|المشاريع",
        question,
        re.IGNORECASE,
    ):
        sections.append("Projects")
    if re.search(
        r"\bskills?|technologies|technology|tools?|frameworks?|programming languages\b|"
        r"مهارات|تقنيات|أدوات|أطر\s+العمل",
        question,
        re.IGNORECASE,
    ):
        sections.append("Skills")
    return tuple(sections)


def _qualified_candidate_summary(
    question: str,
    candidates: list[dict[str, Any]],
    assessments: dict[int, dict[str, str]],
) -> str:
    arabic = bool(re.search(r"[\u0600-\u06FF]", question))
    if not candidates:
        return (
            "لم تُظهر الأدلة المسترجعة استيفاء أي مرشح لجميع المتطلبات أو بعضها."
            if arabic else
            "The retrieved evidence did not establish that any candidate meets all or part of the requirements."
        )

    fully_qualified = [
        candidate for candidate in candidates
        if assessments[int(candidate["document_id"])]["fit_status"] == "meets"
    ]
    if len(fully_qualified) == 1:
        best_candidate = fully_qualified[0]["candidate_label"]
        lines = [
            (
                f"أنسب مرشح مستوفٍ لجميع المتطلبات هو **{best_candidate}**."
                if arabic else
                f"The best-matching candidate who meets all requirements is **{best_candidate}**."
            ),
        ]
    elif len(fully_qualified) > 1:
        lines = [
            "المرشحون الأنسب الذين يستوفون جميع المتطلبات:"
            if arabic else
            "The best-matching candidates who meet all requirements are:"
        ]
    else:
        lines = [
            "المرشحون الذين تدعم الأدلة استيفاءهم لجميع المتطلبات أو بعضها:"
            if arabic else
            "Candidates whose evidence supports meeting all or part of the requirements:"
        ]
    for candidate in candidates:
        assessment = assessments[int(candidate["document_id"])]
        if arabic:
            verdict = (
                "يستوفي المتطلبات"
                if assessment["fit_status"] == "meets"
                else "يستوفي بعض المتطلبات"
            )
        else:
            verdict = (
                "meets the requirements"
                if assessment["fit_status"] == "meets"
                else "partially meets the requirements"
            )
        reason = assessment.get("reason", "").strip()
        line = f"- **{candidate['candidate_label']}**: {verdict}."
        if reason:
            line += f" {reason}"
        lines.append(line)
    return "\n\n".join(lines)


def search_candidates(
    question: str,
    top_k: int = DEFAULT_TOP_K,
    section: str | None = None,
    candidate_ids: list[int] | None = None,
    job_field: str | None = None,
    on_summary_update: Callable[[str], None] | None = None,
    user_role: str | None = None,
) -> dict[str, Any]:
    request_started = time.perf_counter()
    stage_timings: dict[str, float] = {}
    with timed("Search total"):
        question = question.strip()
        if not question:
            raise ValueError("Please enter a search question.")
        search_mode = _search_mode(question)
        contact_requested = requests_candidate_contact_data(question)
        allow_contact_disclosure = (
            contact_requested and can_access_candidate_contact_data(user_role)
        )
        if requests_personal_contact_data(question):  # Block bulk contact requests before CV retrieval.
            arabic = bool(re.search(r"[\u0600-\u06FF]", question))
            return {
                "candidates": [],
                "summary": (
                    "أستطيع عرض بيانات التواصل للمرشحين المطابقين بعد تحديد معايير البحث، "
                    "لكن لا أستخرج بيانات جميع المرشحين من قاعدة البيانات."
                    if arabic else
                    "I can show contact details for candidates matching job-related search "
                    "criteria, but I can’t export contacts for the entire database."
                ),
                "follow_up_suggestions": [],
                "privacy_blocked": True,
            }
        contact_disclosure_denied = (
            contact_requested and not can_access_candidate_contact_data(user_role)
        )

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

        candidate_limit = (
            max(top_k, RETRIEVAL_FETCH_K) if search_mode == "filter"
            else max(top_k, 5) if search_mode == "rank"
            else top_k
        )
        initial_candidates = group_chunks_by_candidate(rows, top_k=candidate_limit)
        required_sections = (
            _required_sections_for_question(question) if section is None else ()
        )
        if required_sections and initial_candidates:
            required_section_candidate_ids = [
                int(candidate["document_id"]) for candidate in initial_candidates
            ]
            stage_started = time.perf_counter()
            with timed("Targeted required-section retrieval"):
                experience_rows = []
                for required_section in required_sections:
                    experience_rows.extend(
                        retrieve_chunks(
                            query_vector=query_vector,
                            query_text=question,
                            top_k=(
                                len(required_section_candidate_ids)
                                * MAX_EVIDENCE_PER_CANDIDATE
                            ),
                            section=required_section,
                            candidate_ids=required_section_candidate_ids,
                            job_field=job_field,
                            per_candidate_limit=MAX_EVIDENCE_PER_CANDIDATE,
                        )
                    )
            stage_timings["required_section_retrieval_seconds"] = round(
                time.perf_counter() - stage_started, 3
            )
            rows.extend(experience_rows)

        stage_started = time.perf_counter()
        with timed("Group and rank candidates"):
            candidates = group_chunks_by_candidate(
                rows,
                top_k=candidate_limit,
                required_sections=required_sections,
                required_section_limit=MAX_EVIDENCE_PER_CANDIDATE,
            )
            _sanitize_candidate_metadata_and_evidence(candidates)
        stage_timings["candidate_grouping_seconds"] = round(time.perf_counter() - stage_started, 3)
        if not candidates:
            stage_timings["total_seconds"] = round(time.perf_counter() - request_started, 3)
            return {
                "candidates": [],
                "search_mode": search_mode,
                "summary": "No matching CV evidence was found.",
                "follow_up_suggestions": [],
                "stage_timings": stage_timings,
                "retrieved_chunk_count": len(rows),
                "embedding_usage": embedding_usage,
                "contact_disclosure_denied": contact_disclosure_denied,
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

        _redact_candidate_evidence(candidates)

        as_of = add_experience_estimates(candidates)  # Calculate work duration against today's date.
        with timed("Build generation prompt"):
            prompt = build_search_prompt(
                question,
                candidates,
                as_of=as_of,
                search_mode=search_mode,
            )
        if on_summary_update is not None:
            on_summary_update(
                "جارٍ تقييم الأدلة وتحديد المرشحين المناسبين..."
                if re.search(r"[\u0600-\u06FF]", question)
                else "Assessing the evidence and identifying relevant candidates..."
            )
        stage_started = time.perf_counter()
        try:
            with timed("AI response generation"):
                generated = generate_json(prompt)
            stage_timings["generation_seconds"] = round(time.perf_counter() - stage_started, 3)
        except Exception as exc:
            stage_timings["generation_seconds"] = round(time.perf_counter() - stage_started, 3)
            stage_timings["total_seconds"] = round(time.perf_counter() - request_started, 3)
            # Keep search useful when the generation service hits its deadline.
            fallback_candidate_ids = [
                int(candidate["document_id"]) for candidate in candidates
            ]
            requested_count = (
                len(candidates) if search_mode == "filter"
                else min(_fallback_requested_count(question), len(candidates))
            )
            return {
                "candidates": candidates,
                "search_mode": search_mode,
                "requested_count": requested_count,
                "candidate_assessments": {},
                "recommended_candidate_id": fallback_candidate_ids[0],
                "candidate_pool_ids": fallback_candidate_ids,
                "summary": (
                    "The AI model could not complete its assessment. The first candidate "
                    "below is the highest-ranked retrieval match; review the cited "
                    "CV evidence before drawing a conclusion."
                ),
                "follow_up_suggestions": [],
                "generation_warning": True,
                "generation_error": f"{type(exc).__name__}: {exc}",
                "contact_disclosure_denied": contact_disclosure_denied,
                "retrieval_trace": retrieval_trace,
                "retrieved_chunk_count": len(rows),
                "stage_timings": stage_timings,
                "generation_usage": {},
                "embedding_usage": embedding_usage,
            }
        retrieved_candidate_ids = [int(candidate["document_id"]) for candidate in candidates]
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
            if document_id not in retrieved_candidate_ids or status not in {
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
            for document_id in retrieved_candidate_ids
            if document_id not in ranked_ids
        )
        rank_order = {document_id: index for index, document_id in enumerate(ranked_ids)}
        candidates.sort(key=lambda candidate: rank_order[int(candidate["document_id"])])
        excluded_candidate_labels = [
            str(candidate["candidate_label"])
            for candidate in candidates
            if assessments.get(int(candidate["document_id"]), {}).get("fit_status")
            not in {"meets", "partial"}
        ]
        candidates = [
            candidate for candidate in candidates
            if assessments.get(int(candidate["document_id"]), {}).get("fit_status")
            in {"meets", "partial"}
        ]
        assessments = {
            int(candidate["document_id"]): assessments[int(candidate["document_id"])]
            for candidate in candidates
        }
        candidate_ids_in_pool = [int(candidate["document_id"]) for candidate in candidates]
        requested_count = len(candidates)
        summary = str(generated.get("summary") or "").strip()
        if not summary or any(
            label.casefold() in summary.casefold()
            for label in excluded_candidate_labels
            if label
        ):
            summary = _qualified_candidate_summary(question, candidates, assessments)
        eligible_contact_ids: set[int] = set()
        if allow_contact_disclosure:
            eligible_contact_ids = {
                int(candidate["document_id"])
                for candidate in candidates[:requested_count]
                if assessments.get(int(candidate["document_id"]), {}).get("fit_status") == "meets"
            }
            if eligible_contact_ids:
                contact_texts = get_candidate_contact_texts(sorted(eligible_contact_ids))
                _attach_contact_details(candidates, eligible_contact_ids, contact_texts)
        recommended_candidate_id = int(candidates[0]["document_id"]) if candidates else None
        usage = generated.get("_usage") if isinstance(generated.get("_usage"), dict) else {}
        stage_timings["total_seconds"] = round(time.perf_counter() - request_started, 3)
        return {
            "candidates": candidates,
            "search_mode": search_mode,
            "requested_count": requested_count,
            "candidate_assessments": assessments,
            "recommended_candidate_id": recommended_candidate_id,
            "candidate_pool_ids": candidate_ids_in_pool,
            "summary": redact_personal_contact_data(summary),
            "follow_up_suggestions": [
                str(q) for q in (generated.get("follow_up_suggestions") or [])[:3]
            ],
            "retrieval_trace": retrieval_trace,
            "retrieved_chunk_count": len(rows),
            "stage_timings": stage_timings,
            "generation_usage": usage,
            "embedding_usage": embedding_usage,
            "contact_disclosure_denied": contact_disclosure_denied,
        }
