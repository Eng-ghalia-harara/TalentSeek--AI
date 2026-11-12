from src.prompts import _evidence_excerpt, build_search_prompt


def test_evidence_excerpt_includes_late_company_mention() -> None:
    text = (
        "Machine Learning Trainer\n"
        + ("Delivered training to teams. " * 70)
        + "\nGaza Sky Geeks - Mercy Corps - Gaza, Palestine\n"
        + "Artificial Intelligence & Data Science Trainer"
    )

    excerpt = _evidence_excerpt(
        text,
        "بدي مهندس عنده خبرة بتدريب الفرق واشتغل مع شركة gaza sky geeks",
    )

    assert "Machine Learning Trainer" in excerpt
    assert "Gaza Sky Geeks - Mercy Corps" in excerpt
    assert len(excerpt) <= 1200


def test_evidence_excerpt_keeps_existing_prefix_when_no_query_phrase_matches() -> None:
    text = "Relevant training experience. " + ("Other work experience. " * 100)

    assert _evidence_excerpt(text, "gaza sky geeks") == text[:1200]


def test_search_prompt_prioritizes_explicit_duration_over_date_estimate() -> None:
    prompt = build_search_prompt("Find candidates with Python and 3 years of experience.", [])

    assert "Interpret \"N years of experience\" as at least N years" in prompt
    assert "An explicit CV statement of total years takes precedence over a date-derived estimate" in prompt
