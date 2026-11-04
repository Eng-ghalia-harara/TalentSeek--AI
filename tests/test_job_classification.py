from src.job_classification import classify_job_chunks, classify_job_profile


def test_classifies_multiple_fields_from_header_and_experience() -> None:
    profile = classify_job_profile({
        "Header": ["Senior Software Engineer"],
        "Work Experience": ["Previously worked as a Data Analyst"],
        "Skills": ["Accountant"],
    })

    assert profile["job_fields"] == ["Data & AI", "Software & IT"]
    assert profile["job_titles"] == ["Data Analyst", "Software Engineer"]
    assert profile["job_classification_sources"] == ["Header", "Work Experience"]


def test_classifies_arabic_job_titles() -> None:
    profile = classify_job_profile({
        "Header": ["محاسب أول"],
        "Work Experience": ["مهندس أمن سيبراني"],
    })

    assert profile["job_fields"] == ["Accounting & Finance", "Cybersecurity"]


def test_unrecognized_titles_are_kept_unclassified() -> None:
    profile = classify_job_profile({
        "Header": ["Candidate Name"],
        "Work Experience": ["Worked on reports and stakeholder communication"],
    })

    assert profile["job_fields"] == ["Unclassified"]
    assert profile["job_titles"] == []


def test_chunk_classifier_uses_section_metadata_not_skills() -> None:
    profile = classify_job_chunks([
        {
            "text": "Section: Header\nMarketing Manager",
            "metadata": {"section": "Header"},
        },
        {
            "text": "Section: Skills\nAccountant",
            "metadata": {"section": "Skills"},
        },
    ])

    assert profile["job_fields"] == ["Marketing"]
