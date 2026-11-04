from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import MAX_PDF_PAGES, MAX_UPLOAD_MB, MIN_EXTRACTED_CHARS
from src.chunking import count_recognized_sections
from src.extraction import extract_pdf


def validate_pdf(path: Path, original_size: int | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if path.suffix.lower() != ".pdf":
        return {"accepted": False, "errors": ["Only PDF files are supported."], "warnings": [], "pages": []}
    try:
        with path.open("rb") as file:
            if file.read(5) != b"%PDF-":
                return {"accepted": False, "errors": ["The uploaded file does not have a valid PDF signature."], "warnings": [], "pages": []}
    except OSError as exc:
        return {"accepted": False, "errors": [f"Could not read the uploaded file: {exc}"], "warnings": [], "pages": []}

    file_size = original_size if original_size is not None else path.stat().st_size
    if file_size > MAX_UPLOAD_MB * 1024 * 1024:
        errors.append(f"File exceeds the {MAX_UPLOAD_MB} MB upload limit.")
        return {"accepted": False, "errors": errors, "warnings": warnings, "pages": []}

    try:
        extracted = extract_pdf(path)
    except Exception as exc:
        return {
            "accepted": False,
            "errors": [f"PDF could not be opened or read: {type(exc).__name__}: {exc}"],
            "warnings": [],
            "pages": [],
        }

    page_count = int(extracted.get("page_count", 0))
    pages = extracted.get("pages", [])
    full_text = "\n".join(page.get("text", "") for page in pages)
    char_count = len(full_text.strip())

    if page_count == 0:
        errors.append("The PDF contains no pages.")
    elif page_count > MAX_PDF_PAGES:
        errors.append(f"The PDF has {page_count} pages; the current limit is {MAX_PDF_PAGES}.")

    if char_count < MIN_EXTRACTED_CHARS:
        errors.append(
            "Not enough selectable text was extracted. Scanned/image-only CVs are not supported in this release."
        )

    if full_text:
        replacement_ratio = full_text.count("\ufffd") / max(len(full_text), 1)
        if replacement_ratio > 0.01:
            errors.append("The extracted text contains too many unreadable replacement characters.")

    # Layout heuristic: report possible columns for human review; do not reject
    # a CV solely because it uses columns, since some PDFs preserve reading order.
    for page in pages:
        width = float(page.get("page_width") or 0)
        blocks = [b for b in page.get("blocks", []) if b.get("bbox") and len(b["bbox"]) == 4]
        if width <= 0 or len(blocks) < 6:
            continue
        left_count = sum(1 for b in blocks if float(b["bbox"][0]) < width * 0.42)
        right_count = sum(1 for b in blocks if float(b["bbox"][0]) > width * 0.52)
        if left_count >= 3 and right_count >= 3:
            warnings.append(
                f"Page {page['page_number']} may use a multi-column layout. Review the extracted reading order before relying on it."
            )

    sections = count_recognized_sections(pages)
    if not sections:
        errors.append("No recognized CV section heading was detected. Use clear headings such as Skills, Experience, or Education.")
    elif len(sections) < 3:
        warnings.append("Only a small number of recognized section headings were detected; please review the extracted text.")

    if char_count >= MIN_EXTRACTED_CHARS and len(pages) < page_count:
        warnings.append("One or more pages contained no extractable text and were omitted from text processing.")

    if len(full_text.split()) < 25:
        warnings.append("The extracted CV contains very little text; review the original PDF before relying on it.")

    return {
        "accepted": not errors,
        "errors": errors,
        "warnings": warnings,
        "pages": pages,
        "page_count": page_count,
        "pages_with_text": len(pages),
        "character_count": char_count,
        "recognized_sections": sorted(sections),
    }
