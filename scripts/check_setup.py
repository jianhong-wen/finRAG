"""Self-check for the database and the two tools.

It applies the schema, inserts a few SYNTHETIC rows (company "SampleCo", fiscal
year 2099), runs both tools, and removes the sample rows afterwards.
No real financial data is involved.

Usage:  python scripts/check_setup.py
"""

import sys
from pathlib import Path

import psycopg
from psycopg.rows import DictRow

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finrag.agent import run_tool  # noqa: E402
from finrag.config import database_url, describe_database  # noqa: E402
from finrag.db import apply_schema, connect  # noqa: E402
from finrag.sample_data import (  # noqa: E402
    SAMPLE_ALIAS_TAG,
    SAMPLE_REVENUE,
    SAMPLE_YEAR,
    delete_sample_data,
    insert_sample_data,
)
from finrag.tools import get_fact, search_filings  # noqa: E402

FILING_ID = "SAMPLE-0001"
QUESTION_TAG = "check_setup"
REQUIRED_TABLES = {"filings", "facts", "chunks", "audit_log"}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """Record and print the result of one check."""
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def check_database(conn: psycopg.Connection[DictRow]) -> None:
    """Check that the pgvector extension is installed."""
    ext = conn.execute("select extversion from pg_extension where extname = 'vector'").fetchone()
    version = conn.execute("select version() as v").fetchone()
    detail = f"vector {ext['extversion']}" if ext else str(version["v"] if version else "")
    check("pgvector extension installed", ext is not None, detail)


def check_get_fact() -> None:
    """Check exact lookup, alias mapping, and the hint for an unknown concept."""
    rows = get_fact("SampleCo", "revenue", SAMPLE_YEAR)["rows"]
    check(
        "get_fact returns the stored value",
        len(rows) == 1 and rows[0]["value"] == SAMPLE_REVENUE and rows[0]["source"] == "xbrl",
        str(rows[0]["value"]) if rows else "no rows",
    )
    rows = get_fact("SampleCo", SAMPLE_ALIAS_TAG, SAMPLE_YEAR)["rows"]
    check("get_fact maps an alias tag to the concept", len(rows) == 1)
    result = get_fact("SampleCo", "ebitda", SAMPLE_YEAR)
    check(
        "get_fact lists available concepts when nothing matches",
        result["rows"] == [] and "revenue" in result["available_concepts"],
        ", ".join(result.get("available_concepts", [])),
    )


def check_search() -> None:
    """Check ranking and the company and fiscal year filters of search_filings."""
    chunks = search_filings("supply chain risk", company="SampleCo", fiscal_year=SAMPLE_YEAR, k=3)[
        "chunks"
    ]
    top = chunks[0]["text"] if chunks else ""
    check(
        "search_filings ranks the matching chunk first",
        "supply chain" in top.lower(),
        f"{len(chunks)} chunks returned",
    )
    chunks = search_filings("supply chain risk", company="SampleCo", fiscal_year=SAMPLE_YEAR - 1)[
        "chunks"
    ]
    check("search_filings applies the fiscal year filter", chunks == [])
    chunks = search_filings("supply chain risk", company="OtherCo")["chunks"]
    check("search_filings applies the company filter", chunks == [])


def check_audit_log(conn: psycopg.Connection[DictRow]) -> None:
    """Check that each tool call through run_tool writes one audit_log row."""
    run_tool(
        QUESTION_TAG,
        "get_fact",
        {"company": "SampleCo", "concept": "revenue", "fiscal_year": SAMPLE_YEAR},
    )
    run_tool(QUESTION_TAG, "search_filings", {"query": "revenue decreased", "company": "SampleCo"})
    row = conn.execute(
        "select count(*) as n from audit_log where question = %s", (QUESTION_TAG,)
    ).fetchone()
    count = row["n"] if row else 0
    check("audit_log records each tool call", count == 2, f"{count} rows")


def main() -> int:
    """Run all checks against DATABASE_URL. Return 0 if every check passed, else 1."""
    print(f"Target: {describe_database(database_url())}")
    tables = apply_schema()
    check("schema applied", REQUIRED_TABLES <= set(tables), ", ".join(tables))
    with connect() as conn:
        check_database(conn)
        delete_sample_data(conn, FILING_ID, QUESTION_TAG)  # leftovers from an interrupted run
        try:
            insert_sample_data(conn, FILING_ID)
            check_get_fact()
            check_search()
            check_audit_log(conn)
        finally:
            delete_sample_data(conn, FILING_ID, QUESTION_TAG)
    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
