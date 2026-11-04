from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pymupdf


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_pdf(pdf_path: Path) -> dict[str, Any]:
    """Extract selectable PDF text page-by-page and retain text block geometry."""
    pages: list[dict[str, Any]] = []
    with pymupdf.open(pdf_path) as document:
        if document.needs_pass:
            raise ValueError("The PDF is password-protected.")
        page_count = len(document)
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text", sort=True) or ""
            blocks: list[dict[str, Any]] = []
            for block_number, block in enumerate(page.get_text("blocks", sort=True) or []):
                if len(block) < 5:
                    continue
                block_text = str(block[4]).strip()
                if not block_text:
                    continue
                blocks.append({
                    "text": block_text,
                    "bbox": [round(float(value), 2) for value in block[:4]],
                    "block_number": block_number,
                    "kind": "pdf_text_block",
                })
            if text.strip():
                pages.append({
                    "page_number": page_number,
                    "page_width": round(float(page.rect.width), 2),
                    "page_height": round(float(page.rect.height), 2),
                    "text": text,
                    "blocks": blocks,
                })
    return {"extractor": "pymupdf", "page_count": page_count, "pages": pages}
