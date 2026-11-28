"""Chunk retrieval with fixed SQL: keyword, vector, and hybrid (RRF) search.

Keyword search has two forms. "and" requires every query word in the chunk
(websearch_to_tsquery). "or" accepts chunks with any query word and ranks them by
ts_rank_cd, which is closer to how BM25-style search treats long questions.
The SQL is composed once from constant fragments with psycopg.sql; inputs are always
parameters.
"""

from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import DictRow

from .db import connect
from .embed import Vector, embed_query

RRF_K = 60  # Reciprocal Rank Fusion constant commonly used in the literature
POOL = 50  # candidates taken from each side before fusion
MAX_K = 20
MODES = ("keyword_and", "keyword_or", "vector", "hybrid_and", "hybrid_or")

_FILTER = sql.SQL(
    "(%(company)s::text is null or f.company ilike %(company)s::text) "
    "and (%(fy)s::int is null or f.fiscal_year = %(fy)s::int)"
)
_TSQUERY = {
    "and": sql.SQL("websearch_to_tsquery('english', %(q)s)"),
    "or": sql.SQL("replace(plainto_tsquery('english', %(q)s)::text, '&', '|')::tsquery"),
}
_VECTOR_CTE = sql.SQL("""vec as (
  select c.chunk_id, row_number() over (order by c.embedding <=> %(qv)s, c.chunk_id) as r,
         1 - (c.embedding <=> %(qv)s) as score
  from chunks c join filings f using (filing_id)
  where {filter}
  order by c.embedding <=> %(qv)s, c.chunk_id
  limit %(pool)s
)""").format(filter=_FILTER)
_KEYWORD_CTE = sql.SQL("""kw as (
  select c.chunk_id,
         row_number() over (order by ts_rank_cd(c.tsv, tsq.query) desc, c.chunk_id) as r,
         ts_rank_cd(c.tsv, tsq.query) as score
  from chunks c join filings f using (filing_id)
  cross join (select {tsquery} as query) as tsq
  where c.tsv @@ tsq.query and {filter}
  order by ts_rank_cd(c.tsv, tsq.query) desc, c.chunk_id
  limit %(pool)s
)""")
_FUSED = sql.SQL("""ranked as (
  select chunk_id, sum(1.0 / (%(rrf_k)s + r)) as score
  from (select chunk_id, r from vec union all select chunk_id, r from kw) u
  group by chunk_id
)""")
_SINGLE = sql.SQL("ranked as (select chunk_id, score from {source})")
_SELECT = sql.SQL("""select c.chunk_id, c.filing_id, f.company, f.fiscal_year, c.page, c.section,
       c.text, ranked.score
from ranked
join chunks c using (chunk_id)
join filings f on f.filing_id = c.filing_id
order by ranked.score desc, c.chunk_id
limit %(k)s""")


def _query(*ctes: sql.Composable) -> sql.Composed:
    return sql.SQL("with {ctes}\n{select}").format(ctes=sql.SQL(",\n").join(ctes), select=_SELECT)


def _build_sql() -> dict[str, sql.Composed]:
    queries = {"vector": _query(_VECTOR_CTE, _SINGLE.format(source=sql.SQL("vec")))}
    for form, tsquery in _TSQUERY.items():
        keyword = _KEYWORD_CTE.format(tsquery=tsquery, filter=_FILTER)
        queries[f"keyword_{form}"] = _query(keyword, _SINGLE.format(source=sql.SQL("kw")))
        queries[f"hybrid_{form}"] = _query(_VECTOR_CTE, keyword, _FUSED)
    return queries


SQL = _build_sql()


def search_chunks(
    query: str,
    mode: str,
    company: str | None = None,
    fiscal_year: int | None = None,
    k: int = 5,
    conn: psycopg.Connection[DictRow] | None = None,
    query_vector: Vector | None = None,
) -> list[dict[str, Any]]:
    """Return up to k chunks for query, best first, with filing, page and score.

    mode is one of MODES. company matches by substring (case-insensitive). k is
    clamped to 1..MAX_K. Pass conn to reuse a connection, and query_vector to reuse
    an embedding. Raises ValueError for an unknown mode.
    """
    if mode not in SQL:
        raise ValueError(f"Unknown search mode {mode!r}; expected one of {', '.join(MODES)}")
    needs_vector = not mode.startswith("keyword")
    params = {
        "q": query,
        "qv": (query_vector if query_vector is not None else embed_query(query))
        if needs_vector
        else None,
        "company": f"%{company}%" if company else None,
        "fy": fiscal_year,
        "pool": POOL,
        "k": max(1, min(int(k), MAX_K)),
        "rrf_k": RRF_K,
    }
    if conn is not None:
        return conn.execute(SQL[mode], params).fetchall()
    with connect() as own:
        return own.execute(SQL[mode], params).fetchall()
