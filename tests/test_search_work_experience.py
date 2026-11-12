from src import search


def _chunk(
    document_id: int,
    chunk_id: int,
    section: str,
    content: str,
    score: float,
) -> dict:
    return {
        "document_id": document_id,
        "chunk_id": chunk_id,
        "title": f"Candidate {document_id}",
        "file_name": f"candidate-{document_id}.pdf",
        "content": content,
        "metadata": {"section": section, "page_nums": [1]},
        "rrf_score": score,
    }


def test_work_experience_intent_is_detected_in_english_and_arabic() -> None:
    assert search._requests_work_experience_evidence(
        "Find an engineer who worked at AMIT and has training experience."
    )
    assert search._requests_work_experience_evidence(
        "بدي مهندس عنده خبرة بتدريب الفرق واشتغل بشركة AMIT"
    )
    assert not search._requests_work_experience_evidence(
        "بدي مهندس معه ماجستير في هندسة الحاسوب"
    )


def test_required_sections_include_explicit_certificate_and_degree_criteria() -> None:
    assert search._required_sections_for_question(
        "بدي مهندس عنده خبرة بتدريب الفرق ومعه شهادة AWS وماجستير"
    ) == ("Work Experience", "Certifications", "Education")


def test_summary_highlights_the_single_candidate_who_meets_all_requirements() -> None:
    candidates = [
        {"document_id": 1, "candidate_label": "Baraa Wael Abu Sallout"},
        {"document_id": 2, "candidate_label": "Ahmed Samir"},
    ]
    assessments = {
        1: {"fit_status": "meets", "reason": "Evidence cites all requirements."},
        2: {"fit_status": "partial", "reason": "Some requirements are unconfirmed."},
    }

    summary = search._qualified_candidate_summary(
        "بدي مهندس عنده خبرة وماجستير",
        candidates,
        assessments,
    )

    assert "أنسب مرشح مستوفٍ لجميع المتطلبات هو **Baraa Wael Abu Sallout**." in summary
    assert "**Ahmed Samir**: يستوفي بعض المتطلبات." in summary


def test_search_retrieves_work_experience_for_each_candidate_and_passes_it_to_assessment(
    monkeypatch,
) -> None:
    education_rows = [
        _chunk(
            document_id,
            chunk_id,
            "Education",
            f"Education record {chunk_id}.",
            score,
        )
        for document_id, start_id, scores in (
            (1, 1, [0.08, 0.07, 0.06, 0.05]),
            (2, 5, [0.04, 0.03, 0.02, 0.01]),
            (3, 9, [0.008, 0.007, 0.006, 0.005]),
            (4, 13, [0.004, 0.003, 0.002, 0.001]),
        )
        for chunk_id, score in zip(range(start_id, start_id + 4), scores)
    ]
    work_rows = [
        _chunk(1, 17, "Work Experience", "Trained engineering teams at AMIT.", 0.01),
        _chunk(2, 18, "Work Experience", "Worked as a software developer.", 0.01),
        _chunk(3, 19, "Work Experience", "Developed software systems.", 0.01),
        _chunk(4, 20, "Work Experience", "Worked on internal projects.", 0.01),
    ]
    certification_rows = [
        _chunk(1, 21, "Certifications", "AWS Certified Solutions Architect.", 0.01),
        _chunk(2, 22, "Certifications", "AWS Cloud Practitioner certification.", 0.01),
        _chunk(3, 23, "Certifications", "CompTIA Security+ certification.", 0.01),
        _chunk(4, 24, "Certifications", "Microsoft Azure certification.", 0.01),
    ]
    retrieval_calls: list[dict] = []

    class FakeGeminiService:
        last_embedding_usage = {}

        def embed_query(self, question: str) -> list[float]:
            return [0.0]

    def fake_retrieve_chunks(**kwargs):
        retrieval_calls.append(kwargs)
        if kwargs["section"] == "Work Experience":
            return work_rows
        if kwargs["section"] == "Certifications":
            return certification_rows
        return education_rows

    captured_prompt: list[str] = []

    def fake_generate_json(prompt: str, **kwargs) -> dict:
        captured_prompt.append(prompt)
        return {
            "summary": (
                "أنسب مرشح مستوفٍ لجميع المتطلبات هو **Candidate 1**.\n\n"
                "- **Candidate 1**: meets. Evidence supports all criteria.\n"
                "- **Candidate 2**: partially meets. Experience evidence reviewed."
            ),
            "requested_count": 2,
            "ranked_candidates": [
                {"document_id": 1, "fit_status": "meets", "reason": "Evidence supports all criteria."},
                {"document_id": 2, "fit_status": "partial", "reason": "Experience evidence reviewed."},
                {"document_id": 3, "fit_status": "does_not_meet", "reason": "No matching evidence."},
                {"document_id": 4, "fit_status": "unclear", "reason": "Insufficient evidence."},
            ],
            "follow_up_suggestions": [],
        }

    monkeypatch.setattr(search, "GeminiService", FakeGeminiService)
    monkeypatch.setattr(search, "retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr(search, "generate_json", fake_generate_json)

    result = search.search_candidates(
        "بدي مهندس عنده خبرة بتدريب الفرق ومعه شهادة AWS",
        top_k=4,
    )

    experience_call = retrieval_calls[1]
    assert experience_call["section"] == "Work Experience"
    assert experience_call["candidate_ids"] == [1, 2, 3, 4]
    assert experience_call["per_candidate_limit"] == 4
    certification_call = retrieval_calls[2]
    assert certification_call["section"] == "Certifications"
    assert certification_call["candidate_ids"] == [1, 2, 3, 4]
    assert certification_call["per_candidate_limit"] == 4
    assert [candidate["document_id"] for candidate in result["candidates"]] == [1, 2]
    assert result["requested_count"] == 2
    assert result["candidate_pool_ids"] == [1, 2]
    assert set(result["candidate_assessments"]) == {1, 2}
    assert "أنسب مرشح مستوفٍ لجميع المتطلبات هو **Candidate 1**." in result["summary"]
    assert "Candidate 3" not in result["summary"]
    assert "Candidate 4" not in result["summary"]
    assert "Evidence supports all criteria." in result["summary"]
    assert "Experience evidence reviewed." in result["summary"]
    assert all(
        any(item["section"] == "Work Experience" for item in candidate["evidence"])
        for candidate in result["candidates"]
    )
    assert "Trained engineering teams at AMIT." in captured_prompt[0]
    assert "Worked as a software developer." in captured_prompt[0]
    assert "AWS Certified Solutions Architect." in captured_prompt[0]
    assert len(result["retrieval_trace"]) == 4
    assert all(
        {
            "Work Experience",
            "Certifications",
        }.issubset({item["section"] for item in candidate["evidence"]})
        for candidate in result["retrieval_trace"]
    )
    assert len(result["retrieval_trace"][0]["evidence"]) > 4
