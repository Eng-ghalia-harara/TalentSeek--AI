from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.config import MAX_EVIDENCE_PER_CANDIDATE


def group_chunks_by_candidate(rows: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for row in rows:
        document_id = int(row["document_id"])
        if document_id not in grouped:
            grouped[document_id] = {
                "document_id": document_id,
                "candidate_label": row.get("title") or row.get("file_name") or f"CV {document_id}",
                "file_name": row.get("file_name") or row.get("title") or f"cv_{document_id}.pdf",
                "source_uri": row.get("source_uri"),
                "score": 0.0,
                "evidence": [],
            }
        grouped[document_id]["evidence"].append({
            "chunk_id": row["chunk_id"],
            "content": row["content"],
            "section": row.get("section") or (row.get("metadata") or {}).get("section", "Unclassified"),
            "page_num": (row.get("metadata") or {}).get("page_num"),
            "page_nums": (row.get("metadata") or {}).get("page_nums", []),
            "token_count": row.get("token_count"),
            "rrf_score": float(row.get("rrf_score") or 0),
        })

    candidates = []
    for candidate in grouped.values():
        evidence = sorted(candidate["evidence"], key=lambda item: item["rrf_score"], reverse=True)
        candidate["evidence"] = evidence[:MAX_EVIDENCE_PER_CANDIDATE]
        scores = [item["rrf_score"] for item in evidence]
        candidate["score"] = (scores[0] if scores else 0.0) + 0.25 * sum(scores[1:3])
        candidates.append(candidate)
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:top_k]
