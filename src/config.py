from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else default


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_path(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default)).expanduser()
    return value if value.is_absolute() else ROOT_DIR / value


# Fixed product choices for v1
EXTRACTION_METHOD = "pymupdf"
CHUNKING_STRATEGY = "section"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIM = env_int("EMBEDDING_DIM", 768)
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "openai/gpt-oss-120b")

# Section chunking: sections stay intact where possible. Very long sections
# are split conservatively before Gemini Embedding 2's 8192-token input limit.
MAX_SECTION_TOKENS = env_int("MAX_SECTION_TOKENS", 6000)
# Token counting still uses Google's API, independently of the generation provider.
TOKEN_COUNT_MODEL = os.getenv("TOKEN_COUNT_MODEL", "gemini-3.1-flash-lite")

# Upload and storage
MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 15)
MAX_PDF_PAGES = env_int("MAX_PDF_PAGES", 30)
MIN_EXTRACTED_CHARS = env_int("MIN_EXTRACTED_CHARS", 100)
STORAGE_DIR = env_path("STORAGE_DIR", "storage/cvs")
STAGING_DIR = env_path("STAGING_DIR", "storage/staging")
REPORTS_DIR = env_path("REPORTS_DIR", "reports")
CACHE_DIR = env_path("CACHE_DIR", "cache")

# Retrieval
DEFAULT_TOP_K = env_int("DEFAULT_TOP_K", 3)
RETRIEVAL_FETCH_K = env_int("RETRIEVAL_FETCH_K", 40)
MAX_EVIDENCE_PER_CANDIDATE = env_int("MAX_EVIDENCE_PER_CANDIDATE", 4)

# Each role uses one shared password configured outside the source tree.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
RECRUITER_PASSWORD = os.getenv("RECRUITER_PASSWORD", "")
DB_CONNECT_TIMEOUT = env_int("DB_CONNECT_TIMEOUT", 5)

if EMBEDDING_DIM not in {768, 1536, 3072}:
    raise ValueError("EMBEDDING_DIM must be 768, 1536, or 3072 for this project configuration.")

for directory in (STORAGE_DIR, STAGING_DIR, REPORTS_DIR, CACHE_DIR):
    directory.mkdir(parents=True, exist_ok=True)
