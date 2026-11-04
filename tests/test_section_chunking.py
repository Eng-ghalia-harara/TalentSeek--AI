from src.chunking import detect_heading, count_recognized_sections, _collect_sections


def test_core_skills_heading_is_recognized():
    assert detect_heading("CORE SKILLS") == "Skills"


def test_english_and_arabic_sections_are_detected():
    pages = [{
        "page_number": 1,
        "text": "PROFESSIONAL SUMMARY\nExperienced engineer\nCORE SKILLS\nPython, SQL\nالخبرات العملية\nBackend developer",
    }]
    found = count_recognized_sections(pages)
    assert "Professional Summary" in found
    assert "Skills" in found
    assert "Work Experience" in found


def test_section_parser_keeps_page_numbers_and_sections():
    pages = [
        {"page_number": 1, "text": "CORE SKILLS\nPython\nSQL"},
        {"page_number": 2, "text": "SQL\nWORK EXPERIENCE\nBuilt APIs"},
    ]
    sections = _collect_sections(pages)
    assert len(sections) == 2
    assert sections[0]["section"] == "Skills"
    assert {page for page, _ in sections[0]["lines"]} == {1, 2}
    assert sections[1]["section"] == "Work Experience"
