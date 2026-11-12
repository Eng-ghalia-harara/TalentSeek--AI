from src.safety import (
    can_access_candidate_contact_data,
    extract_personal_contact_data,
    redact_personal_contact_data,
    requests_candidate_contact_data,
    requests_personal_contact_data,
)
from src.search import _attach_contact_details


def test_contact_request_detection_supports_english_and_arabic():
    assert requests_candidate_contact_data(
        "Show email addresses and phone numbers for matching candidates"
    )
    assert requests_candidate_contact_data("بدي ايميل ورقم جوال للمرشحين المطابقين")


def test_admin_and_recruiter_can_access_candidate_contact_data():
    assert can_access_candidate_contact_data("admin")
    assert can_access_candidate_contact_data("recruiter")
    assert not can_access_candidate_contact_data(None)
    assert not can_access_candidate_contact_data("unknown")


def test_bulk_contact_guard_distinguishes_matching_candidates_from_database_export():
    assert requests_personal_contact_data("List email addresses for all candidates")
    assert not requests_personal_contact_data(
        "List email addresses for all matching candidates"
    )


def test_contact_extraction_deduplicates_and_does_not_treat_dates_as_phones():
    contacts = extract_personal_contact_data([
        "Experience: 2018-2024. Email: person@example.com. Phone: +1 (415) 555-0132",
        "person@example.com, +1 (415) 555-0132",
    ])

    assert contacts == {
        "emails": ["person@example.com"],
        "phones": ["+1 (415) 555-0132"],
    }


def test_attaches_contacts_only_to_eligible_candidates():
    candidates = [
        {"document_id": 1},
        {"document_id": 2},
    ]

    _attach_contact_details(
        candidates,
        {1},
        {
            1: ["person@example.com"],
            2: ["other@example.com"],
        },
    )

    assert candidates[0]["contact_details"]["emails"] == ["person@example.com"]
    assert "contact_details" not in candidates[1]


def test_redaction_removes_contact_coordinates():
    assert redact_personal_contact_data(
        "Email person@example.com, phone +1 (415) 555-0132"
    ) == "Email [contact information hidden], phone [contact information hidden]"
