from src import candidate_matching


def test_group_chunks_keeps_up_to_four_highest_ranked_evidence(monkeypatch) -> None:
    monkeypatch.setattr(candidate_matching, "MAX_EVIDENCE_PER_CANDIDATE", 4)
    rows = [
        {
            "document_id": 1,
            "chunk_id": chunk_id,
            "content": f"Evidence {chunk_id}",
            "rrf_score": score,
        }
        for chunk_id, score in enumerate([0.01, 0.05, 0.02, 0.04, 0.03], start=1)
    ]

    candidates = candidate_matching.group_chunks_by_candidate(rows)

    assert len(candidates) == 1
    assert [item["chunk_id"] for item in candidates[0]["evidence"]] == [2, 4, 5, 3]


def test_group_chunks_expands_limit_for_multiple_required_section_chunks(monkeypatch) -> None:
    monkeypatch.setattr(candidate_matching, "MAX_EVIDENCE_PER_CANDIDATE", 4)
    rows = [
        {
            "document_id": 1,
            "chunk_id": chunk_id,
            "content": f"Education evidence {chunk_id}",
            "metadata": {"section": "Education"},
            "rrf_score": score,
        }
        for chunk_id, score in enumerate([0.08, 0.07, 0.06, 0.05], start=1)
    ]
    rows.extend(
        {
            "document_id": 1,
            "chunk_id": chunk_id,
            "content": f"Work evidence {chunk_id}",
            "metadata": {"section": "Work Experience"},
            "rrf_score": 0.01 / chunk_id,
        }
        for chunk_id in range(5, 9)
    )

    candidates = candidate_matching.group_chunks_by_candidate(
        rows,
        required_sections=("Work Experience",),
        required_section_limit=4,
    )

    assert len(candidates[0]["evidence"]) == 8
    assert [item["section"] for item in candidates[0]["evidence"][:4]] == [
        "Work Experience",
    ] * 4
    assert [item["section"] for item in candidates[0]["evidence"][4:]] == [
        "Education",
    ] * 4
