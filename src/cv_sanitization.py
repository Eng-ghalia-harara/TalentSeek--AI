from __future__ import annotations

import re


_BOILERPLATE_PATTERNS = (
    re.compile(r"^\s*synthetic\s+cv\s+for\s+training/demo\s+purposes[.!]?\s*$", re.IGNORECASE),
)

_INSTRUCTION_PATTERNS = (
    re.compile(
        r"\b(?:ignore|disregard|override|forget)\b.{0,100}\b"
        r"(?:instructions?|prompts?|rules?|criteria)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:always|must|should)\b.{0,80}\b"
        r"(?:select|rank|recommend|hire|shortlist|choose)\b.{0,80}\b"
        r"(?:candidate|applicant)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:select|rank|recommend|hire|shortlist|choose|consider)\b.{0,80}\b"
        r"(?:candidate|applicant)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:candidate|applicant)\b.{0,60}\b"
        r"(?:ideal|best|perfect|top|strongest)\b|"
        r"\b(?:ideal|best|perfect|top|strongest)\b.{0,40}\b"
        r"(?:candidate|applicant)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?:تجاهل|تجاوز|انسَ|انسى).{0,100}(?:التعليمات|القواعد|المعايير|البرومبت)"),
    re.compile(
        r"(?:اختر|رشح|رشّح|وظف|وظّف|اعتبر|اعتمد).{0,80}"
        r"(?:هذا المرشح|المرشح|هذا المتقدم|المتقدم).{0,80}"
        r"(?:الأفضل|افضل|المثالي|مثالي|الأقوى|اقوى)"
    ),
    re.compile(
        r"(?:هذا المرشح|المرشح|هذا المتقدم|المتقدم).{0,60}"
        r"(?:الأفضل|افضل|المثالي|مثالي|الأقوى|اقوى)"
    ),
)


def sanitize_cv_text(text: str) -> str:
    """Remove known CV boilerplate and high-confidence candidate-ranking directives."""
    sanitized_lines: list[str] = []
    for line in text.splitlines():
        if any(pattern.fullmatch(line) for pattern in _BOILERPLATE_PATTERNS):
            continue

        sentences = re.split(r"(?<=[.!?؟])\s+", line)
        safe_sentences = [
            sentence
            for sentence in sentences
            if not any(pattern.search(sentence) for pattern in _INSTRUCTION_PATTERNS)
        ]
        sanitized_lines.append(" ".join(safe_sentences))
    return "\n".join(sanitized_lines)


def remove_nonrendered_pdf_text(text: str, spans: list[dict[str, object]]) -> str:
    """Remove extracted text spans that the PDF renderer marks as invisible or tiny."""
    for span in spans:
        if not (
            span.get("type") == 3
            or float(span.get("opacity", 1.0)) <= 0.0
            or float(span.get("size", 100.0)) < 3.0
        ):
            continue
        chars = span.get("chars", ())
        if not isinstance(chars, (tuple, list)):
            continue
        hidden_text = "".join(
            chr(char[0])
            for char in chars
            if isinstance(char, (tuple, list))
            and char
            and isinstance(char[0], int)
            and 0 < char[0] <= 0x10FFFF
        )
        normalized = re.sub(r"\s+", " ", hidden_text).strip()
        if not normalized:
            continue
        pattern = re.escape(normalized).replace(r"\ ", r"\s+")
        matches = list(re.finditer(pattern, text))
        if len(matches) == 1:
            text = re.sub(pattern, " ", text, count=1)
    return text
