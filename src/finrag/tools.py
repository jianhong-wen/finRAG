"""The two retrieval tools used by the agent.

get_fact       looks up a stored number (structured data).
search_filings searches document text (hybrid keyword + vector search).
"""

from typing import Any

import psycopg
from psycopg.rows import DictRow

from .db import connect
from .embed import embed_query

# Reciprocal Rank Fusion (RRF) constant. 60 is the value commonly used in the literature.
RRF_K = 60
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


_SEARCH_SQL = """
with vec as (
  select c.chunk_id,
         row_number() over (order by c.embedding <=> %(qv)s) as r
  from chunks c join filings f using (filing_id)
  where (%(company)s::text is null or f.company ilike %(company)s::text)
    and (%(fy)s::int is null or f.fiscal_year = %(fy)s::int)
  order by c.embedding <=> %(qv)s
  limit %(pool)s
),
kw as (
  select c.chunk_id,
         row_number() over (order by ts_rank_cd(c.tsv, tsq.query) desc) as r
  from chunks c
  join filings f using (filing_id)
  cross join websearch_to_tsquery('english', %(q)s) as tsq(query)
  where c.tsv @@ tsq.query
    and (%(company)s::text is null or f.company ilike %(company)s::text)
    and (%(fy)s::int is null or f.fiscal_year = %(fy)s::int)
  order by ts_rank_cd(c.tsv, tsq.query) desc
  limit %(pool)s
),
fused as (
  select chunk_id, sum(1.0 / (%(rrf_k)s + r)) as score
  from (select chunk_id, r from vec union all select chunk_id, r from kw) u
  group by chunk_id
)
select c.chunk_id, c.filing_id, f.company, f.fiscal_year, c.page, c.section,
       c.text, fu.score
from fused fu
join chunks c using (chunk_id)
join filings f on f.filing_id = c.filing_id
order by fu.score desc
limit %(k)s
"""


def search_filings(
    query: str,
    company: str | None = None,
    fiscal_year: int | None = None,
    k: int = 5,
) -> dict[str, Any]:
    """Hybrid search over document chunks. Returns the top k chunks with sources."""
    k = max(1, min(int(k), 20))
    with connect() as conn:
        rows = conn.execute(
            _SEARCH_SQL,
            {
                "qv": embed_query(query),
                "q": query,
                "company": f"%{company}%" if company else None,
                "fy": fiscal_year,
                "pool": 50,
                "k": k,
                "rrf_k": RRF_K,
            },
        ).fetchall()
    for r in rows:
        r["text"] = r["text"][:TEXT_LIMIT]
        r["score"] = float(r["score"])
    return {"chunks": rows}
