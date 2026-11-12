from src.search import _search_mode


def test_candidate_criteria_phrase_is_an_exhaustive_filter() -> None:
    assert _search_mode(
        "Candidates in Cairo with more than 3 years of experience."
    ) == "filter"


def test_explicit_recommendation_remains_ranked() -> None:
    assert _search_mode("Recommend the best candidates in Cairo.") == "rank"


def test_question_about_which_candidates_is_an_exhaustive_filter() -> None:
    assert _search_mode("Which candidates have more than 3 years of experience?") == "filter"
