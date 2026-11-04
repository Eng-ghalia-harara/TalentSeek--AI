from __future__ import annotations

from pathlib import Path
from typing import Any

from src import config
from src.ats_validator import validate_pdf
from src.chunking import make_chunks
from src.database import (
    document_hash_exists,
    get_document,
    record_ingestion_event,
    save_document_and_chunks,
)
from src.embeddings import GeminiService
from src.extraction import sha256_bytes
from src.gemini_tokens import count_gemini_tokens
from src.job_classification import classify_job_chunks
from src.storage import remove_file, save_original_pdf, write_staging_file


def validate_uploaded_cv(file_name: str, data: bytes) -> dict[str, Any]:
    if not file_name.lower().endswith(".pdf"):
        return {"accepted": False, "errors": ["Only PDF files are supported."], "warnings": [], "pages": []}
    content_hash = sha256_bytes(data)
    temporary_path = write_staging_file(file_name, data)
    try:
        result = validate_pdf(temporary_path, original_size=len(data))
        result["content_hash"] = content_hash
        result["file_name"] = file_name
        return result
    finally:
        temporary_path.unlink(missing_ok=True)


def ingest_uploaded_cv(
    *,
    file_name: str,
    data: bytes,
    user_id: int,
    validation: dict[str, Any] | None = None,
    replace_document_id: int | None = None,
) -> dict[str, Any]:
    """Validate/prepare fully, then atomically publish document + chunks."""
    action = "replace" if replace_document_id is not None else "upload"
    content_hash = sha256_bytes(data)
    old_document = get_document(replace_document_id) if replace_document_id else None
    if replace_document_id is not None and old_document is None:
        raise LookupError("The selected CV to replace does not exist.")

    duplicate = document_hash_exists(content_hash, exclude_document_id=replace_document_id)
    if duplicate:
        record_ingestion_event(
            user_id, file_name, content_hash, action, "duplicate",
            [f"Identical content already exists as document ID {duplicate['id']}."],
            {"duplicate_document_id": duplicate["id"]}, replace_document_id,
        )
        return {
            "status": "duplicate",
            "document_id": duplicate["id"],
            "message": (
                "An identical CV already exists as document "
                f"{duplicate['id']} ({duplicate['title']})."
            ),
        }

    if validation is None:
        validation = validate_uploaded_cv(file_name, data)
    if not validation.get("accepted"):
        reasons = list(validation.get("errors", []))
        record_ingestion_event(
            user_id, file_name, content_hash, action, "rejected", reasons,
            {"warnings": validation.get("warnings", [])}, replace_document_id,
        )
        return {"status": "rejected", "errors": reasons, "warnings": validation.get("warnings", [])}

    pages = validation.get("pages", [])
    if not pages:
        reasons = ["No extracted page content was available for ingestion."]
        record_ingestion_event(user_id, file_name, content_hash, action, "failed", reasons, {}, replace_document_id)
        return {"status": "failed", "errors": reasons}

    record_ingestion_event(
        user_id, file_name, content_hash, action, "accepted", [],
        {"page_count": validation.get("page_count"), "recognized_sections": validation.get("recognized_sections", [])},
        replace_document_id,
    )
    record_ingestion_event(user_id, file_name, content_hash, action, "processing", [], {}, replace_document_id)

    new_path: Path | None = None
    try:
        chunks = make_chunks(pages, strategy=config.CHUNKING_STRATEGY)
        if not chunks:
            raise ValueError("Section chunking did not produce any searchable chunks.")
        job_profile = classify_job_chunks(chunks)

        gemini = GeminiService()
        prepared_records: list[dict[str, Any]] = []
        title = Path(file_name).stem

        for chunk in chunks:
            section = str(chunk.get("metadata", {}).get("section") or "Unclassified")
            token_count = int(chunk.get("token_count") or count_gemini_tokens(chunk["text"]))
            vector = gemini.embed_document(chunk["text"], title=title, section=section)
            if len(vector) != config.EMBEDDING_DIM:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {config.EMBEDDING_DIM}, got {len(vector)}."
                )
            prepared_records.append({
                "chunk_index": int(chunk["chunk_index"]),
                "text": chunk["text"],
                "token_count": token_count,
                "embedding": vector,
                "metadata": dict(chunk.get("metadata", {})),
            })

        new_path = save_original_pdf(content_hash, file_name, data)
        doc_metadata = {
            "file_name": file_name,
            "extraction_method": config.EXTRACTION_METHOD,
            "chunking_strategy": config.CHUNKING_STRATEGY,
            "embedding_model": config.EMBEDDING_MODEL,
            "embedding_dim": config.EMBEDDING_DIM,
            "pages": validation.get("page_count"),
            "recognized_sections": validation.get("recognized_sections", []),
            "warnings": validation.get("warnings", []),
            **job_profile,
        }
        document_id, previous_source = save_document_and_chunks(
            title=title,
            source_uri=str(new_path),
            content_hash=content_hash,
            chunks=prepared_records,
            user_id=user_id,
            replace_document_id=replace_document_id,
            metadata=doc_metadata,
        )
    except Exception as exc:
        if new_path:
            remove_file(str(new_path))
        try:
            record_ingestion_event(
                user_id, file_name, content_hash, action, "failed",
                [f"{type(exc).__name__}: {exc}"], {}, replace_document_id,
            )
        except Exception:
            pass
        # The old document and chunks remain untouched if replacement failed.
        raise

    # The database transaction has committed. Cleanup/logging failures must never
    # remove the newly published file or roll back the already-published CV.
    if previous_source and previous_source != str(new_path):
        try:
            remove_file(previous_source)
        except OSError:
            pass
    try:
        record_ingestion_event(
            user_id, file_name, content_hash, action, "succeeded", [],
            {"chunks_created": len(prepared_records), "embedding_model": config.EMBEDDING_MODEL},
            document_id,
        )
    except Exception:
        pass
    return {
        "status": "succeeded",
        "document_id": document_id,
        "chunks_created": len(prepared_records),
        "warnings": validation.get("warnings", []),
        "message": "CV was successfully indexed.",
    }
