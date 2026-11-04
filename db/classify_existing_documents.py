from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection
from src.database import Jsonb
from src.job_classification import classify_job_profile


def classify_existing_documents(document_id: int | None = None) -> dict[str, int]:
    query = """
        SELECT d.id AS document_id, c.content, c.metadata->>'section' AS section
        FROM documents d
        LEFT JOIN chunks c
            ON c.document_id = d.id
           AND c.extraction_method = 'pymupdf'
           AND c.chunking_strategy = 'section'
        WHERE d.status = 'ready'
    """
    params: tuple[int, ...] = ()
    if document_id is not None:
        query += " AND d.id = %s"
        params = (document_id,)
    query += " ORDER BY d.id, c.chunk_index"

    documents: dict[int, dict[str, list[str]]] = defaultdict(
        lambda: {"Header": [], "Work Experience": []}
    )
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        for row in rows:
            section = row["section"]
            if section in {"Header", "Work Experience"} and row["content"]:
                documents[int(row["document_id"])][section].append(str(row["content"]))

        updated = 0
        classified = 0
        with conn.transaction():
            for current_document_id, sections in documents.items():
                profile: dict[str, Any] = classify_job_profile(sections)
                conn.execute("""
                    UPDATE documents
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || %s,
                        updated_at = NOW()
                    WHERE id = %s AND status = 'ready'
                """, (Jsonb(profile), current_document_id))
                updated += 1
                if profile["job_fields"] != ["Unclassified"]:
                    classified += 1

    return {"updated": updated, "classified": classified, "unclassified": updated - classified}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify indexed CVs using stored Header and Work Experience chunks."
    )
    parser.add_argument("--document-id", type=int, help="Classify one ready document ID.")
    args = parser.parse_args()
    if args.document_id is not None and args.document_id < 1:
        parser.error("--document-id must be a positive integer.")

    result = classify_existing_documents(args.document_id)
    print(
        "Classification complete: "
        f"{result['updated']} CVs updated, "
        f"{result['classified']} classified, "
        f"{result['unclassified']} unclassified."
    )


if __name__ == "__main__":
    main()
