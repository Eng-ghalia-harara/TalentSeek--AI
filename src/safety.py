from __future__ import annotations

import re


_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
_CONTACT_TERMS_RE = re.compile(
    r"\b(?:phone\s+number|mobile\s+number|telephone\s+number|e-?mail\s+address|contact\s+(?:details|information|info))\b",
    re.IGNORECASE,
)
_CANDIDATE_CONTACT_RE = re.compile(
    r"\b(?:candidate|applicant|employee|person)\b.{0,60}\b(?:phone|mobile|telephone|e-?mail|contact)\b"
    r"|\b(?:phone|mobile|telephone|e-?mail|contact)\b.{0,60}\b(?:candidate|applicant|employee|person)\b",
    re.IGNORECASE,
)
_ARABIC_CONTACT_RE = re.compile(
    r"(?:رقم\s*(?:الهاتف|الجوال|الموبايل)|البريد\s*(?:الإلكتروني|الالكتروني)|"
    r"معلومات\s*(?:الاتصال|التواصل)|بيانات\s*(?:الاتصال|التواصل)|"
    r"(?:هاتف|جوال|بريد)\s+(?:المرشح|المتقدم))"
)


def requests_personal_contact_data(question: str) -> bool:
    """Detect requests to disclose a candidate's personal contact coordinates."""
    if _CONTACT_TERMS_RE.search(question) or _ARABIC_CONTACT_RE.search(question):
        return True
    if not _CANDIDATE_CONTACT_RE.search(question):
        return False
    # Don't block job searches for email-marketing skills or similar terms.
    contact_context = re.search(
        r"\b(?:give|show|share|reveal|provide|list|send|get|tell)\b|"
        r"\b(?:private|personal)\b|\b(?:address|number|details|information)\b",
        question,
        re.IGNORECASE,
    )
    arabic_context = re.search(r"(?:اعطني|أعطني|اعرض|أظهر|شارك|اكشف|رقم|عنوان|خاص|الشخصية)", question)
    return bool(contact_context or arabic_context)


def redact_personal_contact_data(text: str) -> str:
    """Remove contact coordinates if the model repeats them despite instructions."""
    text = _EMAIL_RE.sub("[contact information hidden]", text)
    return _PHONE_RE.sub("[contact information hidden]", text)
