from __future__ import annotations

from typing import Any

from pgvector import Vector
from psycopg.types.json import Jsonb

from db.connection import get_connection
from src.config import EXTRACTION_METHOD, CHUNKING_STRATEGY


def check_database() -> dict[str, Any]:
    with get_connection() as conn:
        db_name = conn.execute("SELECT current_database() AS name").fetchone()["name"]
        tables = conn.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name IN
                ('documents', 'chunks', 'app_users', 'ingestion_events')
            ORDER BY table_name
        """).fetchall()
        vector_type = conn.execute("""
            SELECT format_type(a.atttypid, a.atttypmod) AS type
            FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = 'chunks' AND a.attname = 'embedding' AND a.attnum > 0
        """).fetchone()
    return {"database": db_name, "tables": [r["table_name"] for r in tables], "embedding_type": vector_type["type"] if vector_type else None}


def get_or_create_role_user(role: str) -> dict[str, Any]:
    if role not in {"admin", "recruiter"}:
        raise ValueError("Role must be admin or recruiter.")
    email = f"talentseek-{role}@local.invalid"
    display_name = "Admin (shared role)" if role == "admin" else "Recruiter (shared role)"
    with get_connection() as conn:
        with conn.transaction():
            conn.execute(
                """INSERT INTO app_users (email, display_name, role, is_active)
                   VALUES (%s, %s, %s, TRUE)
                   ON CONFLICT (LOWER(email)) DO NOTHING""",
                (email, display_name, role),
            )
            user = conn.execute(
                """SELECT id, email, display_name, role, is_active
                   FROM app_users WHERE LOWER(email) = %s FOR UPDATE""",
                (email,),
            ).fetchone()
            if user is None or user["role"] != role:
                raise RuntimeError(f"Could not load the internal {role} role account.")
            if not user["is_active"]:
                raise PermissionError(f"The {role} role account has been disabled.")
            user = conn.execute(
                """UPDATE app_users SET last_login = NOW()
                   WHERE id = %s AND is_active = TRUE AND role = %s
                   RETURNING id, email, display_name, role, is_active""",
                (user["id"], role),
            ).fetchone()
            if user is None:
                raise PermissionError(f"The {role} role account is no longer active.")
            return user


def list_users() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, email, display_name, role, is_active, created_at, last_login FROM app_users ORDER BY created_at DESC"
        ).fetchall()


def get_active_user(user_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """SELECT id, email, display_name, role, is_active
               FROM app_users WHERE id = %s AND is_active = TRUE""",
            (user_id,),
        ).fetchone()


def document_hash_exists(content_hash: str, exclude_document_id: int | None = None) -> dict[str, Any] | None:
    with get_connection() as conn:
        if exclude_document_id is None:
            return conn.execute(
                "SELECT id, title, source_uri FROM documents WHERE content_hash = %s LIMIT 1",
                (content_hash,),
            ).fetchone()
        return conn.execute(
            "SELECT id, title, source_uri FROM documents WHERE content_hash = %s AND id <> %s LIMIT 1",
            (content_hash, exclude_document_id),
        ).fetchone()


def get_document(document_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM documents WHERE id = %s", (document_id,)).fetchone()


def list_documents() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute("""
            SELECT d.id, d.title, d.source_uri, d.content_hash, d.status,
                   d.mime_type, d.created_at, d.updated_at,
                   COUNT(c.id) AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            GROUP BY d.id
            ORDER BY d.updated_at DESC NULLS LAST, d.id DESC
        """).fetchall()


def list_job_fields() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT field.value AS job_field
            FROM documents d
            CROSS JOIN LATERAL jsonb_array_elements_text(
                CASE
                    WHEN jsonb_typeof(d.metadata->'job_fields') = 'array'
                    THEN d.metadata->'job_fields'
                    ELSE '[]'::jsonb
                END
            ) AS field(value)
            WHERE d.status = 'ready'
            ORDER BY job_field
        """).fetchall()
    return [str(row["job_field"]) for row in rows]


def update_document_job_profile(document_id: int, profile: dict[str, Any]) -> None:
    with get_connection() as conn:
        result = conn.execute("""
            UPDATE documents
            SET metadata = COALESCE(metadata, '{}'::jsonb) || %s,
                updated_at = NOW()
            WHERE id = %s AND status = 'ready'
        """, (Jsonb(profile), document_id))
        if result.rowcount != 1:
            raise LookupError(f"Ready CV document {document_id} was not found.")


def get_dashboard_stats() -> dict[str, int]:
    with get_connection() as conn:
        docs = conn.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'ready') AS ready,
                   COUNT(*) FILTER (WHERE status <> 'ready') AS not_ready
            FROM documents
        """).fetchone()
        chunks = conn.execute("SELECT COUNT(*) AS total FROM chunks").fetchone()
        events = conn.execute("""
            SELECT COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
                   COUNT(*) FILTER (WHERE status IN ('failed', 'duplicate')) AS issues
            FROM ingestion_events
            WHERE created_at >= NOW() - INTERVAL '30 days'
        """).fetchone()
    return {"documents": docs["total"], "ready": docs["ready"], "not_ready": docs["not_ready"], "chunks": chunks["total"], "rejected_30d": events["rejected"], "issues_30d": events["issues"]}


def record_ingestion_event(
    user_id: int | None,
    file_name: str,
    content_hash: str | None,
    action: str,
    status: str,
    reasons: list[str] | None = None,
    details: dict[str, Any] | None = None,
    document_id: int | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO ingestion_events
                (user_id, document_id, file_name, content_hash, action, status, reasons, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id, document_id, file_name, content_hash, action, status,
            Jsonb(reasons or []), Jsonb(details or {}),
        ))


def save_document_and_chunks(
    *,
    title: str,
    source_uri: str,
    content_hash: str,
    chunks: list[dict[str, Any]],
    user_id: int,
    replace_document_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[int, str | None]:
    """Atomically publish a fully processed CV. Returns document id and previous source path."""
    previous_source: str | None = None
    with get_connection() as conn:
        with conn.transaction():
            if replace_document_id is None:
                row = conn.execute(
                    """INSERT INTO documents
                       (title, source_uri, mime_type, content_hash, status, metadata, created_by_user_id, updated_by_user_id)
                       VALUES (%s, %s, 'application/pdf', %s, 'ready', %s, %s, %s)
                       RETURNING id""",
                    (title, source_uri, content_hash, Jsonb(metadata or {}), user_id, user_id),
                ).fetchone()
                document_id = int(row["id"])
            else:
                existing = conn.execute(
                    "SELECT id, source_uri FROM documents WHERE id = %s FOR UPDATE",
                    (replace_document_id,),
                ).fetchone()
                if not existing:
                    raise LookupError("The CV selected for replacement no longer exists.")
                previous_source = existing["source_uri"]
                conn.execute("DELETE FROM chunks WHERE document_id = %s", (replace_document_id,))
                conn.execute("""
                    UPDATE documents
                    SET title = %s, source_uri = %s, mime_type = 'application/pdf',
                        content_hash = %s, status = 'ready', metadata = %s,
                        updated_at = NOW(), updated_by_user_id = %s
                    WHERE id = %s
                """, (title, source_uri, content_hash, Jsonb(metadata or {}), user_id, replace_document_id))
                document_id = replace_document_id

            for chunk in chunks:
                chunk_meta = dict(chunk["metadata"])
                conn.execute("""
                    INSERT INTO chunks
                        (document_id, chunk_index, extraction_method, chunking_strategy,
                         content, metadata, token_count, embedding)
                    VALUES (%s, %s, 'pymupdf', 'section', %s, %s, %s, %s)
                """, (
                    document_id,
                    int(chunk["chunk_index"]),
                    chunk["text"],
                    Jsonb(chunk_meta),
                    int(chunk["token_count"]),
                    Vector(chunk["embedding"]),
                ))
            return document_id, previous_source


def delete_document(document_id: int) -> str | None:
    with get_connection() as conn:
        with conn.transaction():
            row = conn.execute(
                "DELETE FROM documents WHERE id = %s RETURNING source_uri, title",
                (document_id,),
            ).fetchone()
            return row["source_uri"] if row else None


def retrieve_chunks(
    query_vector: list[float],
    query_text: str,
    top_k: int = 40,
    section: str | None = None,
    candidate_ids: list[int] | None = None,
    job_field: str | None = None,
) -> list[dict[str, Any]]:
    """Hybrid SQL search: cosine vector retrieval + PostgreSQL full-text retrieval + RRF."""
    if candidate_ids is not None:
        candidate_ids = list(dict.fromkeys(int(candidate_id) for candidate_id in candidate_ids))
        if not candidate_ids:
            return []
    candidate_filter = " AND c.document_id = ANY(%s::int[])" if candidate_ids is not None else ""
    sql = """
    WITH q AS (
        SELECT plainto_tsquery('simple', %s) AS tsq
    ),
    semantic AS (
        SELECT c.id AS chunk_id,
               ROW_NUMBER() OVER (ORDER BY c.embedding <=> %s) AS rank
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.status = 'ready'
          AND c.extraction_method = 'pymupdf'
          AND c.chunking_strategy = 'section'
          AND (%s::text IS NULL OR c.metadata->>'section' = %s)
          AND (%s::text IS NULL OR d.metadata->'job_fields' ? %s)
          {candidate_filter}
        ORDER BY c.embedding <=> %s
        LIMIT %s
    ),
    keyword_base AS (
        SELECT c.id AS chunk_id,
               ts_rank_cd(to_tsvector('simple', c.content), q.tsq) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        CROSS JOIN q
        WHERE d.status = 'ready'
          AND c.extraction_method = 'pymupdf'
          AND c.chunking_strategy = 'section'
          AND (%s::text IS NULL OR c.metadata->>'section' = %s)
          AND (%s::text IS NULL OR d.metadata->'job_fields' ? %s)
          {candidate_filter}
          AND to_tsvector('simple', c.content) @@ q.tsq
    ),
    keyword AS (
        SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank
        FROM keyword_base
        ORDER BY score DESC
        LIMIT %s
    ),
    combined AS (
        SELECT chunk_id, rank FROM semantic
        UNION ALL
        SELECT chunk_id, rank FROM keyword
    ),
    fused AS (
        SELECT chunk_id, SUM(1.0 / (60 + rank)) AS rrf_score
        FROM combined
        GROUP BY chunk_id
    )
    SELECT c.id AS chunk_id, c.document_id, d.title, d.source_uri,
           d.metadata->>'file_name' AS file_name,
           c.content, c.metadata, c.token_count, fused.rrf_score
    FROM fused
    JOIN chunks c ON c.id = fused.chunk_id
    JOIN documents d ON d.id = c.document_id
    ORDER BY fused.rrf_score DESC
    LIMIT %s
    """.format(candidate_filter=candidate_filter)
    params = [
        query_text,
        Vector(query_vector),
        section, section, job_field, job_field,
    ]
    if candidate_ids is not None:
        params.append(candidate_ids)
    params.extend([Vector(query_vector), top_k, section, section, job_field, job_field])
    if candidate_ids is not None:
        params.append(candidate_ids)
    params.extend([
        top_k,
        top_k,
    ])
    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()
