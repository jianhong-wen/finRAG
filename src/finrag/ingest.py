"""Load PDF filings into the database: one filing row, then its page-bounded chunks.

A filing is reloaded only when its file hash or the pipeline version changes (ADR 0007).
Each filing is written in one transaction, so a failed load leaves the old rows in place.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import DictRow

from .chunking import MAX_TOKENS, OVERLAP_TOKENS, TokenCounter, chunk_page
from .config import EMBED_BACKEND
from .embed import EMBED_MODEL, Vector

FORM_NAMES = {"10k": "10-K", "10q": "10-Q", "8k": "8-K", "earnings": "Earnings release"}

Embedder = Callable[[list[str]], list[Vector]]


@dataclass(frozen=True)
class ChunkRow:
    """One chunk ready to store: 1-based page number, context line and text."""

    page: int
    context: str
    text: str

    def embedding_input(self) -> str:
        """Text given to the embedding model: the context line, then the chunk text."""
        return f"{self.context}\n{self.text}"


def pipeline_version(parser_version: str) -> str:
    """Describe everything that changes the stored chunks; a change forces a reload."""
    model = "hash-test-embeddings" if EMBED_BACKEND == "hash" else EMBED_MODEL
    return f"pypdfium2 {parser_version}; chunks {MAX_TOKENS}/{OVERLAP_TOKENS}; {model}"


def filing_row(document: dict[str, Any]) -> dict[str, Any]:
    """Map a manifest document to a filings row. Raises ValueError for an unknown form."""
    doc_type = str(document["doc_type"]).lower()
    if doc_type not in FORM_NAMES:
        raise ValueError(f"{document['doc_name']}: unknown document type {doc_type!r}")
    return {
        "filing_id": document["doc_name"],
        "company": document["company"],
        "form": FORM_NAMES[doc_type],
        "fiscal_year": int(str(document["doc_period"])[:4]),
        "source_url": document.get("original_doc_link"),
        "source_sha256": document["sha256"],
    }


def context_line(row: dict[str, Any], page: int) -> str:
    """Return the line that precedes every chunk, for example '3M | 10-K | FY2018 | page 60'."""
    return f"{row['company']} | {row['form']} | FY{row['fiscal_year']} | page {page}"


def build_chunks(row: dict[str, Any], pages: Sequence[str], count: TokenCounter) -> list[ChunkRow]:
    """Chunk every page of a filing; pages[0] is page 1."""
    chunks: list[ChunkRow] = []
    for page_number, text in enumerate(pages, start=1):
        context = context_line(row, page_number)
        chunks.extend(ChunkRow(page_number, context, t) for t in chunk_page(text, context, count))
    return chunks


def needs_load(stored: tuple[str | None, str | None] | None, sha256: str, version: str) -> bool:
    """True unless the stored (sha256, pipeline_version) equals the current pair."""
    return stored != (sha256, version)


def stored_state(
    conn: psycopg.Connection[DictRow], filing_id: str
) -> tuple[str | None, str | None] | None:
    """Return (source_sha256, pipeline_version) of a stored filing, or None if absent."""
    row = conn.execute(
        "select source_sha256, pipeline_version from filings where filing_id = %s", (filing_id,)
    ).fetchone()
    return (row["source_sha256"], row["pipeline_version"]) if row else None


def load_filing(
    conn: psycopg.Connection[DictRow],
    row: dict[str, Any],
    chunks: list[ChunkRow],
    embed: Embedder,
    version: str,
) -> None:
    """Replace one filing and all its chunks in a single transaction."""
    vectors = embed([c.embedding_input() for c in chunks])
    with conn.transaction():
        conn.execute(
            "insert into filings (filing_id, company, form, fiscal_year, source_url, "
            "source_sha256, pipeline_version) "
            "values (%(filing_id)s, %(company)s, %(form)s, %(fiscal_year)s, %(source_url)s, "
            "%(source_sha256)s, %(version)s) "
            "on conflict (filing_id) do update set company = excluded.company, "
            "form = excluded.form, fiscal_year = excluded.fiscal_year, "
            "source_url = excluded.source_url, source_sha256 = excluded.source_sha256, "
            "pipeline_version = excluded.pipeline_version, ingested_at = now()",
            row | {"version": version},
        )
        conn.execute("delete from chunks where filing_id = %s", (row["filing_id"],))
        with conn.cursor() as cursor:
            cursor.executemany(
                "insert into chunks (filing_id, page, context, text, embedding) "
                "values (%s, %s, %s, %s, %s)",
                [
                    (row["filing_id"], c.page, c.context, c.text, v)
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
