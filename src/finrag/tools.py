"""The two retrieval tools used by the agent.

get_fact       looks up a stored number (structured data).
search_filings searches document text (vector search, ADR 0009).
"""

from typing import Any

import psycopg
from psycopg.rows import DictRow

from .db import connect
from .retrieval import search_chunks

SEARCH_MODE = "vector"  # retrieval mode used by the agent (ADR 0009)
TEXT_LIMIT = 1500  # characters of chunk text returned to the model


def _normalize_concept(conn: psycopg.Connection[DictRow], concept: str) -> str:
    """Map a raw tag or free text to the normalized concept name."""
    row = conn.execute(
        "select concept from concept_aliases where lower(raw_tag) = lower(%(c)s)",
        {"c": concept},
    ).fetchone()
    if row:
        return str(row["concept"])
    return concept.strip().lower().replace(" ", "_")


def get_fact(company: str, concept: str, fiscal_year: int) -> dict[str, Any]:
    """Return stored values for one company, concept and fiscal year.

    If nothing matches, return the concepts that do exist for that company and
    year, so the caller can correct the name.
    """
    with connect() as conn:
        concept_name = _normalize_concept(conn, concept)
        params = {"company": f"%{company}%", "concept": concept_name, "fy": fiscal_year}
        rows = conn.execute(
            """
            select f.company, f.fiscal_year, fa.concept, fa.value, fa.unit,
                   fa.period_start, fa.period_end, fa.source, fa.page,
                   fa.confidence, f.filing_id, f.source_url
            from facts fa
            join filings f using (filing_id)
            where fa.concept = %(concept)s
              and f.company ilike %(company)s
              and f.fiscal_year = %(fy)s
            order by (fa.source = 'xbrl') desc, fa.confidence desc nulls last
            """,
            params,
        ).fetchall()
        if rows:
            return {"rows": rows}
        available = conn.execute(
            """
            select distinct fa.concept
            from facts fa join filings f using (filing_id)
            where f.company ilike %(company)s and f.fiscal_year = %(fy)s
            order by 1
            """,
            params,
        ).fetchall()
        return {
            "rows": [],
            "message": f"No value found for concept '{concept_name}'.",
            "available_concepts": [r["concept"] for r in available],
        }


def search_filings(
    query: str,
    company: str | None = None,
    fiscal_year: int | None = None,
    k: int = 5,
) -> dict[str, Any]:
    """Search document chunks (SEARCH_MODE). Returns the top k chunks with sources."""
    rows = search_chunks(query, SEARCH_MODE, company=company, fiscal_year=fiscal_year, k=k)
    for r in rows:
        r["text"] = r["text"][:TEXT_LIMIT]
        r["score"] = float(r["score"])
    return {"chunks": rows}
