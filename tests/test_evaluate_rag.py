from src.evaluate_rag import _count_generation_failures


def test_count_generation_failures_handles_cases_that_failed_before_generation() -> None:
    records = [
        {"generation_warning": True},
        {"generation_warning": False},
        {"status": "error"},
    ]

    assert _count_generation_failures(records) == 1
