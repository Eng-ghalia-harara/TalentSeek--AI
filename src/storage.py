from __future__ import annotations

import re
import uuid
from pathlib import Path

from src.config import STORAGE_DIR, STAGING_DIR


def safe_filename(name: str) -> str:
    stem = Path(name).stem
    suffix = Path(name).suffix.lower() or ".pdf"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "cv"
    return f"{stem[:100]}{suffix}"


def save_original_pdf(content_hash: str, file_name: str, data: bytes) -> Path:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    destination = STORAGE_DIR / f"{content_hash[:16]}_{safe_filename(file_name)}"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(destination)
    return destination.resolve()


def remove_file(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value).resolve()
    storage_root = STORAGE_DIR.resolve()
    try:
        path.relative_to(storage_root)
    except ValueError:
        # Never delete a path outside this app's managed CV storage.
        return
    if path.is_file():
        path.unlink(missing_ok=True)


def write_staging_file(file_name: str, data: bytes) -> Path:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    path = STAGING_DIR / f"upload_{uuid.uuid4().hex}_{safe_filename(file_name)}"
    path.write_bytes(data)
    return path
