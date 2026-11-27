"""Database connection helper."""

from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import DictRow, dict_row

from .config import database_url


def connect(register_vectors: bool = True) -> psycopg.Connection[DictRow]:
    """Open a connection that returns rows as dictionaries.

    Set register_vectors=False only before the vector extension exists
    (for example while creating the schema).
    """
    conn = psycopg.connect(
        database_url(),
        autocommit=True,
        row_factory=dict_row,
        prepare_threshold=None,  # avoids problems with pooled connections
    )
    if register_vectors:
        register_vector(conn)
    return conn


SCHEMA_FILE = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


def apply_schema() -> list[str]:
    """Create the extension, tables and indexes. Returns the table names."""
    with connect(register_vectors=False) as conn:
        conn.execute(SCHEMA_FILE.read_text())
        rows = conn.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'public' order by 1"
        ).fetchall()
    return [r["table_name"] for r in rows]
