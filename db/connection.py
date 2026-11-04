"""PostgreSQL connection factory. Keeps DB credentials outside application SQL."""
from __future__ import annotations

import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

from src.config import DB_CONNECT_TIMEOUT, ROOT_DIR

load_dotenv(ROOT_DIR / ".env")


def get_connection() -> psycopg.Connection:
    required = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASS")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing PostgreSQL settings in .env: " + ", ".join(missing)
        )

    conn = psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASS"],
        connect_timeout=DB_CONNECT_TIMEOUT,
        row_factory=dict_row,
    )
    register_vector(conn)
    return conn
