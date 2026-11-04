from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection
from src.config import REPORTS_DIR
from src.extraction import extract_pdf


def fetch_documents(document_id: int | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT id, title, source_uri, metadata
        FROM documents
        WHERE status = 'ready'
    """
    params: tuple[int, ...] = ()
    if document_id is not None:
        query += " AND id = %s"
        params = (document_id,)
    query += " ORDER BY id"

    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def build_report(documents: list[dict[str, Any]]) -> str:
    report = [f"Extracted CV Text Report for {len(documents)} files", "=" * 80]
    if not documents:
        report.append("No ready CV documents were found.")
        return "\n".join(report) + "\n"

    for document in documents:
        pdf_path = Path(document["source_uri"])
        if not pdf_path.is_file():
            raise FileNotFoundError(
                f"PDF for document {document['id']} was not found: {pdf_path}"
            )

        extracted = extract_pdf(pdf_path)
        metadata = document.get("metadata") or {}
        file_name = metadata.get("file_name") or pdf_path.name
        report.extend([
            "",
            f"Document ID: {document['id']}",
            f"Title: {document['title']}",
            f"File: {file_name}",
            f"PDF pages: {extracted['page_count']}",
            "-" * 80,
        ])
        if not extracted["pages"]:
            report.append("[No selectable text was extracted from this PDF.]")
            continue
        for page in extracted["pages"]:
            report.extend([
                "",
                f"--- Page {page['page_number']} ---",
                page["text"].rstrip(),
            ])

    return "\n".join(report).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export extracted text from indexed CV PDFs to a TXT report."
    )
    parser.add_argument(
        "--document-id",
        type=int,
        help="Export one document ID; omit to export every ready CV.",
    )
    args = parser.parse_args()
    if args.document_id is not None and args.document_id < 1:
        parser.error("--document-id must be a positive integer.")

    report = build_report(fetch_documents(args.document_id))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORTS_DIR / "extracted_text_report.txt"
    output_path.write_text(report, encoding="utf-8")
    print(f"Extracted text report saved: {output_path}")


if __name__ == "__main__":
    main()
