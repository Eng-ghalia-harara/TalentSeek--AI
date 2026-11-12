from __future__ import annotations

from collections import defaultdict
from typing import Any

from psycopg.types.json import Jsonb

from db.connection import get_connection
from src.job_classification import classify_job_chunks


def reclassify_ready_documents() -> list[dict[str, Any]]:
    """Refresh saved job fields and normalize legacy header chunks without re-embedding."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT d.id, d.title, d.metadata AS document_metadata,
                   c.id AS chunk_id, c.chunk_index, c.content,
                   c.metadata AS chunk_metadata
            FROM documents d
            JOIN chunks c ON c.document_id = d.id
            WHERE d.status = 'ready'
            ORDER BY d.id, c.chunk_index
        """).fetchall()

        grouped: dict[int, dict[str, Any]] = defaultdict(
            lambda: {"chunks": [], "title": "", "metadata": {}}
        )
        for row in rows:
            document = grouped[int(row["id"])]
            document["title"] = str(row["title"])
            document["metadata"] = row["document_metadata"] or {}
            document["chunks"].append({
                "chunk_index": int(row["chunk_index"]),
                "chunk_id": int(row["chunk_id"]),
                "content": row["content"],
                "metadata": row["chunk_metadata"] or {},
            })

        updated: list[dict[str, Any]] = []
        for document_id, document in grouped.items():
            for chunk in document["chunks"]:
                if (
                    chunk["chunk_index"] == 0
                    and chunk["metadata"].get("section") == "Unclassified"
                    and str(chunk["content"]).startswith("Section: Unclassified\n")
                ):
                    chunk["metadata"]["section"] = "Header"
                    chunk["content"] = str(chunk["content"]).replace(
                        "Section: Unclassified\n", "Section: Header\n", 1
                    )
                    conn.execute("""
                        UPDATE chunks
                        SET metadata = metadata || %s, content = %s
                        WHERE id = %s
                    """, (
                        Jsonb({"section": "Header"}),
                        chunk["content"],
                        chunk["chunk_id"],
                    ))

            profile = classify_job_chunks(document["chunks"])
            metadata = document["metadata"]
            if all(metadata.get(key) == value for key, value in profile.items()):
                continue
            conn.execute("""
                UPDATE documents
                SET metadata = COALESCE(metadata, '{}'::jsonb) || %s,
                    updated_at = NOW()
                WHERE id = %s AND status = 'ready'
            """, (Jsonb(profile), document_id))
            updated.append({
                "document_id": document_id,
                "title": document["title"],
                "job_fields": profile["job_fields"],
            })
    return updated


if __name__ == "__main__":
    changed = reclassify_ready_documents()
    if changed:
        for item in changed:
            print(f"Updated {item['document_id']} {item['title']}: {', '.join(item['job_fields'])}")
    else:
        print("All ready CV job-field classifications are already current.")
