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


def fetch_chunks(document_id: int | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT c.id AS chunk_id,
               c.document_id,
               d.title,
               d.metadata->>'file_name' AS file_name,
               c.chunk_index,
               c.token_count,
               c.metadata,
               c.content
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
    """
    params: tuple[int, ...] = ()
    if document_id is not None:
        query += " WHERE c.document_id = %s"
        params = (document_id,)
    query += " ORDER BY c.document_id, c.chunk_index, c.id"

    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def build_report(chunks: list[dict[str, Any]]) -> str:
    file_count = len({chunk["document_id"] for chunk in chunks})
    report = [
        f"Indexed CV Chunks Report for {file_count} files & {len(chunks)} chunks",
        "=" * 80,
    ]
    if not chunks:
        report.append("No indexed chunks were found.")
        return "\n".join(report) + "\n"

    previous_document_id = None
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        section = metadata.get("section") or "Unclassified"
        if chunk["document_id"] != previous_document_id:
            report.extend([
                "",
                "=" * 80,
                f"Document ID: {chunk['document_id']}",
                f"Title: {chunk['title']}",
                f"File: {chunk.get('file_name') or 'Unknown'}",
            ])
            previous_document_id = chunk["document_id"]

        pages = metadata.get("page_nums") or (
            [metadata["page_num"]] if metadata.get("page_num") is not None else []
        )
        report.extend([
            "",
            f"Chunk ID: {chunk['chunk_id']}",
            f"Chunk index: {chunk['chunk_index']}",
            f"Section: {section}",
            f"Pages: {', '.join(map(str, pages)) or 'Unknown'}",
            f"Tokens: {chunk.get('token_count') if chunk.get('token_count') is not None else 'Unknown'}",
            "Chunk text:",
            "-" * 80,
            chunk["content"].rstrip(),
            "-" * 80,
        ])

    return "\n".join(report).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export indexed CV chunk text to a TXT report."
    )
    parser.add_argument(
        "--document-id",
        type=int,
        help="Export chunks for one document ID; omit to export every chunk.",
    )
    args = parser.parse_args()
    if args.document_id is not None and args.document_id < 1:
        parser.error("--document-id must be a positive integer.")

    report = build_report(fetch_chunks(args.document_id))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORTS_DIR / "chunks_report.txt"
    output_path.write_text(report, encoding="utf-8")
    print(f"Chunks report saved: {output_path}")


if __name__ == "__main__":
    main()
