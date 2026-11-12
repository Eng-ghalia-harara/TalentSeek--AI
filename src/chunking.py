from __future__ import annotations

import re
from typing import Any

from src.config import MAX_SECTION_TOKENS
from src.gemini_tokens import count_gemini_tokens

# ATS/CV section aliases. Extend conservatively when real CVs reveal new headings.
SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Work Experience", re.compile(r"^relevant\s+experience$", re.I)),
    ("Professional Summary", re.compile(r"^(professional\s+summary|career\s+summary|summary|profile|professional\s+profile|career\s+objective|objective|about\s+me|ملخص\s+مهني|الملخص\s+المهني|نبذة\s+عني|الهدف\s+المهني)$", re.I)),
    ("Skills", re.compile(r"^(core\s+skills|technical\s+skills|key\s+skills|skills|core\s+competencies|competencies|مهارات|المهارات|المهارات\s+التقنية|المهارات\s+الشخصية|الكفاءات)$", re.I)),
    ("Work Experience", re.compile(r"^(work\s+experience|professional\s+experience|employment\s+history|experience|career\s+history|الخبرات\s+العملية|الخبرة\s+العملية|الخبرات\s+المهنية|الخبرة\s+المهنية|الخبرات)$", re.I)),
    ("Projects", re.compile(r"^(projects|personal\s+projects|academic\s+projects|selected\s+projects|المشاريع|المشاريع\s+الشخصية|المشاريع\s+الأكاديمية|مشاريع)$", re.I)),
    ("Education", re.compile(r"^(education|academic\s+background|qualifications|التعليم|المؤهلات\s+العلمية|المؤهل\s+العلمي|الخلفية\s+الأكاديمية)$", re.I)),
    ("Certifications", re.compile(r"^(certifications|certificates|licenses|الشهادات|الشهادات\s+المهنية|الدورات|الدورات\s+التدريبية|الرخص)$", re.I)),
    ("Languages", re.compile(r"^(languages|اللغات|اللغة)$", re.I)),
    ("Contact", re.compile(r"^(contact|contact\s+information|personal\s+details|معلومات\s+التواصل|معلومات\s+شخصية|بيانات\s+التواصل)$", re.I)),
    ("Achievements", re.compile(r"^(achievements|awards|honors|الإنجازات|الجوائز|التكريمات)$", re.I)),
]


def normalize_heading(line: str) -> str:
    value = (line or "").strip()
    value = re.sub(r"^\s*#{1,6}\s*", "", value)
    value = value.strip(" \t•*-–—|:")
    value = re.sub(r"\s+", " ", value)
    return value


def detect_heading(line: str) -> str | None:
    value = normalize_heading(line)
    if not value or len(value) > 75:
        return None
    for canonical, pattern in SECTION_PATTERNS:
        if pattern.fullmatch(value):
            return canonical
    return None


def count_recognized_sections(pages: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    for page in pages:
        for line in str(page.get("text", "")).splitlines():
            section = detect_heading(line)
            if section:
                found.add(section)
    return found


def _collect_sections(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    # Text before the first recognized section is the CV identity/contact header.
    current_name = "Header"
    current_lines: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal current_lines
        body_lines = [(page, line) for page, line in current_lines if line.strip()]
        if body_lines:
            sections.append({"section": current_name, "lines": body_lines})
        current_lines = []

    for page in sorted(pages, key=lambda item: int(item["page_number"])):
        page_number = int(page["page_number"])
        for line in str(page.get("text", "")).replace("\r", "\n").splitlines():
            heading = detect_heading(line)
            if heading:
                flush()
                current_name = heading
                # Preserve the actual heading in searchable text.
                current_lines.append((page_number, normalize_heading(line)))
            else:
                current_lines.append((page_number, line.rstrip()))
    flush()
    return sections


def _join_lines(lines: list[tuple[int, str]]) -> tuple[str, list[tuple[int, int, int]]]:
    parts: list[str] = []
    page_spans: list[tuple[int, int, int]] = []
    cursor = 0
    for page_number, line in lines:
        if parts:
            parts.append("\n")
            cursor += 1
        clean_line = line.strip()
        start = cursor
        parts.append(clean_line)
        cursor += len(clean_line)
        if clean_line:
            page_spans.append((start, cursor, page_number))
    return "".join(parts).strip(), page_spans


def _preferred_boundary(text: str, start: int, end: int) -> int:
    """Move a candidate boundary backward to a paragraph/line/sentence/word boundary."""
    floor = start + max(1, int((end - start) * 0.72))
    candidates: list[int] = []
    for pattern in ("\n\n", "\n", ". ", "; ", " "):
        pos = text.rfind(pattern, floor, end)
        if pos >= floor:
            candidates.append(pos + len(pattern))
    return max(candidates) if candidates else end


def _split_long_text(text: str, max_tokens: int) -> list[tuple[int, int, str, int]]:
    if not text.strip():
        return []
    initial_count = count_gemini_tokens(text)
    if initial_count <= max_tokens:
        return [(0, len(text), text, initial_count)]

    result: list[tuple[int, int, str, int]] = []
    start = 0
    while start < len(text):
        low, high = start + 1, len(text)
        best = start
        while low <= high:
            mid = (low + high) // 2
            token_count = count_gemini_tokens(text[start:mid])
            if token_count <= max_tokens:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        if best == start:
            raise ValueError("A single text unit could not fit within MAX_SECTION_TOKENS.")
        end = _preferred_boundary(text, start, best)
        end = max(start + 1, min(end, best))
        piece = text[start:end]
        piece_tokens = count_gemini_tokens(piece)
        while piece_tokens > max_tokens and end > start + 1:
            end -= 1
            piece = text[start:end]
            piece_tokens = count_gemini_tokens(piece)
        if not piece.strip():
            start = end
            continue
        result.append((start, end, piece, piece_tokens))
        start = end
    return result


def make_chunks(pages: list[dict[str, Any]], strategy: str = "section") -> list[dict[str, Any]]:
    """Product v1 supports Section-based chunking only."""
    if strategy != "section":
        raise ValueError("This product version supports only strategy='section'.")
    if not pages:
        return []

    sections = _collect_sections(pages)
    output: list[dict[str, Any]] = []

    for section in sections:
        body, page_spans = _join_lines(section["lines"])
        if not body.strip():
            continue
        # Prefix every chunk with its section so the embedding retains context.
        full_text = f"Section: {section['section']}\n{body}"
        spans = _split_long_text(full_text, MAX_SECTION_TOKENS)

        for start, end, content, tokens in spans:
            header_length = len(f"Section: {section['section']}\n")
            body_start = max(0, start - header_length)
            body_end = max(0, end - header_length)
            page_numbers = sorted({
                page for span_start, span_end, page in page_spans
                if span_end > body_start and span_start < body_end
            })
            if not page_numbers:
                page_numbers = sorted({int(page["page_number"]) for page in pages})
            output.append({
                "chunk_index": len(output),
                "text": content.strip(),
                "token_count": tokens,
                "metadata": {
                    "section": section["section"],
                    "page_nums": page_numbers,
                },
            })
    return output
