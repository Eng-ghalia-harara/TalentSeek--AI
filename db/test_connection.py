"""Run this file from VS Code to verify the existing PostgreSQL connection."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.connection import get_connection


def main() -> None:
    with get_connection() as conn:
        database = conn.execute("SELECT current_database() AS name").fetchone()["name"]
        docs = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
        chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        vector_type = conn.execute("""
            SELECT format_type(a.atttypid, a.atttypmod) AS type
            FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = 'chunks' AND a.attname = 'embedding' AND a.attnum > 0
        """).fetchone()["type"]
    print("PostgreSQL connection: OK")
    print(f"Database: {database}")
    print(f"Documents: {docs}")
    print(f"Chunks: {chunks}")
    print(f"Embedding column: {vector_type}")
    if vector_type != "vector(768)":
        raise RuntimeError(f"Expected vector(768), found {vector_type}")


if __name__ == "__main__":
    main()
