from __future__ import annotations

import re


_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
_CONTACT_TERMS_RE = re.compile(
    r"\b(?:phone(?:\s+number)?|mobile(?:\s+number)?|telephone(?:\s+number)?|e-?mail(?:\s+addresses?)?|contact\s+(?:details|information|info))\b|"
    r"(?:بريد(?:\s+إلكتروني)?|ايميلات|إيميلات|ايميل|إيميل|البريد الإلكتروني|"
    r"رقم\s+(?:الهاتف|الجوال|الموبايل)|(?:رقم\s+)?جوال|معلومات التواصل|بيانات التواصل)",
    re.IGNORECASE,
)
_CANDIDATE_CONTACT_RE = re.compile(
    r"\b(?:candidate|applicant|employee|person)\b.{0,60}\b(?:phone|mobile|telephone|e-?mail|contact)\b"
    r"|\b(?:phone|mobile|telephone|e-?mail|contact)\b.{0,60}\b(?:candidate|applicant|employee|person)\b",
    re.IGNORECASE,
)
_CONTACT_REQUEST_ACTION_RE = re.compile(
    r"\b(?:what\s+(?:is|are)|who\s+is|give|show|share|provide|list|send|get|tell|find|retrieve|need|want)\b|"
    r"(?:ما\s*(?:هو|هي)?|شو|بدي|اريد|أريد|محتاج|أحتاج|اعطني|أعطني|عطني|اعرض|أظهر|هات|زوّدني|زودني)",
    re.IGNORECASE,
)
_BULK_CONTACT_REQUEST_RE = re.compile(
    r"\b(?:all|every|each|everyone|all\s+candidates|contact\s+list|export|bulk|database)\b|"
    r"(?:كل|جميع|كافة)\s*(?:المرشحين|المرشحات|المتقدمين|المتقدمات|عناوين|بيانات|قائمة)|"
    r"(?:قائمة\s+(?:بريد|ايميل|إيميل|تواصل))",
    re.IGNORECASE,
)
_MATCHING_CANDIDATE_SCOPE_RE = re.compile(
    r"\b(?:matching|qualified|relevant|shortlisted|filtered)\s+candidates?\b|"
    r"\bcandidates?\b.{0,80}\b(?:who|that)\s+(?:match|meet|satisfy)\b|"
    r"\b(?:meet|meeting|satisfy|satisfying)\s+(?:the\s+)?(?:stated\s+)?criteria\b|"
    r"(?:المرشحين|المرشحات|المتقدمين|المتقدمات).{0,80}"
    r"(?:المطابقين|المطابقات|المطابق|المناسبين|المؤهلين|الذين\s+تنطبق\s+عليهم)",
    re.IGNORECASE,
)


def requests_candidate_contact_data(question: str) -> bool:
    """Detect an explicit request for contact details, so only that answer may include them."""
    has_contact_term = bool(
        _CONTACT_TERMS_RE.search(question)
        or _CANDIDATE_CONTACT_RE.search(question)
    )
    return has_contact_term and bool(_CONTACT_REQUEST_ACTION_RE.search(question))


def can_access_candidate_contact_data(user_role: str | None) -> bool:
    return user_role in {"admin", "recruiter"}


def requests_personal_contact_data(question: str) -> bool:
    """Block unfiltered database-wide contact requests, not contacts for matching candidates."""
    has_contact_term = bool(
        _CONTACT_TERMS_RE.search(question)
        or _CANDIDATE_CONTACT_RE.search(question)
    )
    return (
        has_contact_term
        and bool(_BULK_CONTACT_REQUEST_RE.search(question))
        and not _MATCHING_CANDIDATE_SCOPE_RE.search(question)
    )


def redact_personal_contact_data(text: str) -> str:
    """Remove contact coordinates when the recruiter did not explicitly request them."""
    text = _EMAIL_RE.sub("[contact information hidden]", text)
    return _PHONE_RE.sub("[contact information hidden]", text)


def extract_personal_contact_data(texts: list[str]) -> dict[str, list[str]]:
    emails: list[str] = []
    phones: list[str] = []
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()

    for text in texts:
        for match in _EMAIL_RE.finditer(text):
            email = match.group(0)
            normalized = email.casefold()
            if normalized not in seen_emails:
                seen_emails.add(normalized)
                emails.append(email)
        for match in _PHONE_RE.finditer(text):
            phone = match.group(0).strip()
            digits = re.sub(r"\D", "", phone)
            if not 9 <= len(digits) <= 15 or digits in seen_phones:
                continue
            seen_phones.add(digits)
            phones.append(phone)

    return {"emails": emails, "phones": phones}
