from __future__ import annotations

import re
from typing import Any


JOB_TITLE_DICTIONARY: dict[str, dict[str, tuple[str, ...]]] = {
    "Engineering": {
        "Civil Engineer": ("civil engineer", "مهندس مدني", "مهندسة مدنية"),
        "Mechanical Engineer": ("mechanical engineer", "مهندس ميكانيكي", "مهندسة ميكانيكية"),
        "Electrical Engineer": ("electrical engineer", "مهندس كهربائي", "مهندسة كهربائية"),
        "Industrial Engineer": ("industrial engineer", "مهندس صناعي", "مهندسة صناعية"),
        "Chemical Engineer": ("chemical engineer", "مهندس كيميائي", "مهندسة كيميائية"),
    },
    "Software & IT": {
        "Backend Engineer": ("backend engineer", "java backend engineer"),
        "Java Developer": ("java developer",),
        "Software Engineer": ("software engineer", "مهندس برمجيات", "مهندسة برمجيات"),
        "Software Developer": ("software developer", "مطور برمجيات", "مطورة برمجيات"),
        "Backend Developer": ("backend developer", "back-end developer", "مطور خلفي"),
        "Frontend Developer": ("frontend developer", "front-end developer", "مطور واجهات"),
        "Full Stack Developer": ("full stack developer", "full-stack developer", "مطور متكامل"),
        "DevOps Engineer": ("devops engineer", "مهندس ديف أوبس"),
        "Network Engineer": ("network engineer", "مهندس شبكات"),
        "Systems Administrator": ("systems administrator", "system administrator", "مسؤول أنظمة"),
        "IT Specialist": ("it specialist", "information technology specialist", "أخصائي تقنية المعلومات"),
        "Database Administrator": ("database administrator", "مدير قواعد بيانات"),
    },
    "Data & AI": {
        "Machine Learning & Generative AI Trainee": (
            "machine learning & generative ai trainee",
            "machine learning and generative ai trainee",
        ),
        "Data Analyst": ("data analyst", "محلل بيانات", "محللة بيانات"),
        "Data Scientist": ("data scientist", "عالم بيانات", "عالمة بيانات"),
        "Data Engineer": ("data engineer", "مهندس بيانات", "مهندسة بيانات"),
        "Machine Learning Engineer": ("machine learning engineer", "مهندس تعلم آلي", "مهندسة تعلم آلي"),
        "AI Engineer": ("artificial intelligence engineer", "ai engineer", "مهندس ذكاء اصطناعي"),
    },
    "Cybersecurity": {
        "Cybersecurity Analyst": ("cybersecurity analyst", "cyber security analyst", "محلل أمن سيبراني"),
        "Security Engineer": ("security engineer", "مهندس أمن سيبراني", "مهندس أمن معلومات"),
        "Penetration Tester": ("penetration tester", "اختبار اختراق", "مختبر اختراق"),
        "SOC Analyst": ("soc analyst", "محلل مركز عمليات الأمن"),
        "Information Security Specialist": ("information security specialist", "أخصائي أمن المعلومات"),
    },
    "Accounting & Finance": {
        "Accountant": ("accountant", "محاسب", "محاسبة"),
        "Auditor": ("auditor", "مدقق حسابات", "مراجع حسابات"),
        "Financial Analyst": ("financial analyst", "محلل مالي", "محللة مالية"),
        "Finance Manager": ("finance manager", "مدير مالي", "مديرة مالية"),
    },
    "Marketing": {
        "Performance Marketing Specialist": ("performance marketing specialist",),
        "CRM & Marketing Automation Specialist": (
            "crm & marketing automation specialist",
            "crm and marketing automation specialist",
        ),
        "CRM Specialist": ("crm specialist",),
        "Marketing Operations Coordinator": ("marketing operations coordinator",),
        "Digital Marketing Executive": ("digital marketing executive",),
        "Marketing Manager": ("marketing manager", "مدير تسويق", "مديرة تسويق"),
        "Digital Marketing Specialist": ("digital marketing specialist", "أخصائي تسويق رقمي"),
        "SEO Specialist": ("seo specialist", "أخصائي تحسين محركات البحث"),
        "Content Marketer": ("content marketer", "مسوق محتوى", "مسوقة محتوى"),
        "Social Media Specialist": ("social media specialist", "أخصائي وسائل التواصل الاجتماعي"),
    },
    "Human Resources": {
        "Recruiter": ("recruiter", "talent acquisition specialist", "مسؤول توظيف", "أخصائي استقطاب"),
        "HR Specialist": ("human resources specialist", "hr specialist", "أخصائي موارد بشرية"),
        "HR Manager": ("human resources manager", "hr manager", "مدير موارد بشرية"),
    },
    "Sales": {
        "Sales Representative": ("sales representative", "sales executive", "مندوب مبيعات", "مندوبة مبيعات"),
        "Sales Manager": ("sales manager", "مدير مبيعات", "مديرة مبيعات"),
        "Business Development": ("business development", "تطوير الأعمال"),
    },
    "Healthcare": {
        "Nurse": ("registered nurse", "nurse", "ممرض", "ممرضة"),
        "Physician": ("physician", "medical doctor", "طبيب", "طبيبة"),
        "Pharmacist": ("pharmacist", "صيدلي", "صيدلانية"),
    },
    "Education": {
        "Teacher": ("teacher", "مدرس", "مدرسة", "معلم", "معلمة"),
        "Lecturer": ("lecturer", "محاضر", "محاضرة"),
        "Academic Researcher": ("academic researcher", "باحث أكاديمي", "باحثة أكاديمية"),
    },
}

JOB_FIELD_LABELS = {
    "Engineering": "Engineering / الهندسة",
    "Software & IT": "Software & IT / البرمجيات وتقنية المعلومات",
    "Data & AI": "Data & AI / البيانات والذكاء الاصطناعي",
    "Cybersecurity": "Cybersecurity / الأمن السيبراني",
    "Accounting & Finance": "Accounting & Finance / المحاسبة والمالية",
    "Marketing": "Marketing / التسويق",
    "Human Resources": "Human Resources / الموارد البشرية",
    "Sales": "Sales / المبيعات",
    "Healthcare": "Healthcare / الرعاية الصحية",
    "Education": "Education / التعليم",
    "Unclassified": "Unclassified / غير مصنف",
}


def _compile_title_pattern(title: str) -> re.Pattern[str]:
    words = re.escape(title).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){words}(?!\w)", re.IGNORECASE)


_TITLE_PATTERNS = [
    (field, title, _compile_title_pattern(alias))
    for field, titles in JOB_TITLE_DICTIONARY.items()
    for title, aliases in titles.items()
    for alias in sorted(aliases, key=len, reverse=True)
]
_TITLE_PATTERNS.sort(key=lambda item: max(len(alias) for alias in JOB_TITLE_DICTIONARY[item[0]][item[1]]), reverse=True)


def _matches_in_line(line: str) -> list[tuple[str, str, int, int]]:
    matches: list[tuple[str, str, int, int]] = []
    occupied: list[tuple[int, int]] = []
    for field, title, pattern in _TITLE_PATTERNS:
        match = pattern.search(line)
        if match is None:
            continue
        start, end = match.span()
        if any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied):
            continue
        matches.append((field, title, start, end))
        occupied.append((start, end))
    return matches


def classify_job_profile(sections: dict[str, list[str]]) -> dict[str, Any]:
    """Classify only job-title evidence from a CV header and work-experience sections."""
    fields: set[str] = set()
    titles: set[str] = set()
    sources: set[str] = set()

    for section_name in ("Header", "Work Experience"):
        for text in sections.get(section_name, []):
            for line in text.splitlines():
                for field, title, _, _ in _matches_in_line(line):
                    fields.add(field)
                    titles.add(title)
                    sources.add(section_name)

    ordered_fields = sorted(fields)
    if not ordered_fields:
        ordered_fields = ["Unclassified"]

    return {
        "job_fields": ordered_fields,
        "job_titles": sorted(titles),
        "job_classification_sources": sorted(sources),
        "job_classification_version": 2,
    }


def classify_job_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    sections: dict[str, list[str]] = {"Header": [], "Work Experience": []}
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        section_name = metadata.get("section")
        text = str(chunk.get("text") or chunk.get("content") or "")
        text = re.sub(r"^Section:\s*[^\r\n]+\r?\n", "", text, count=1)
        if section_name == "Unclassified" and int(chunk.get("chunk_index", -1)) == 0:
            # Older indexed CVs used Unclassified for the initial identity/title header.
            section_name = "Header"
        relevant_experience = re.search(r"(?im)^\s*RELEVANT\s+EXPERIENCE\s*$", text)
        if relevant_experience:
            # Some older CVs placed this heading inside a different chunk section.
            section_name = "Work Experience"
            text = text[relevant_experience.end():]
        if section_name not in sections:
            continue
        sections[section_name].append(text)
    return classify_job_profile(sections)
