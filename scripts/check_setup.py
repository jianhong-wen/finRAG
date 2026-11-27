"""Self-check for the database and the two tools.

It applies the schema, inserts a few SYNTHETIC rows (company "SampleCo", fiscal
year 2099), runs both tools, and removes the sample rows afterwards.
No real financial data is involved.

Usage:  python scripts/check_setup.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finrag.agent import run_tool  # noqa: E402
from finrag.config import database_url, describe_database  # noqa: E402
from finrag.db import apply_schema, connect  # noqa: E402
from finrag.embed import embed_documents  # noqa: E402
from finrag.tools import get_fact, search_filings  # noqa: E402

FILING_ID = "SAMPLE-0001"
QUESTION_TAG = "check_setup"
CHUNKS = [
    (
        12,
        "Risk Factors",
        "Supply chain disruptions could delay deliveries and increase our costs. "
        "We rely on a small number of suppliers for key components.",
    ),
    (
        31,
        "MD&A",
        "Revenue decreased compared with the prior year, mainly because of lower "
        "unit volumes in the second half of the year.",
    ),
    (45, "Notes", "Capital expenditures consisted mainly of manufacturing equipment and software."),
]

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def cleanup(conn) -> None:
    conn.execute("delete from filings where filing_id = %s", (FILING_ID,))
    conn.execute("delete from concept_aliases where raw_tag = 'Revenues'")
    conn.execute("delete from audit_log where question = %s", (QUESTION_TAG,))


def main() -> int:
    print(f"Target: {describe_database(database_url())}")
    tables = apply_schema()
    check(
        "schema applied",
        {"filings", "facts", "chunks", "audit_log"} <= set(tables),
        ", ".join(tables),
    )

    with connect() as conn:
        version = conn.execute("select version() as v").fetchone()["v"]
        ext = conn.execute(
            "select extversion from pg_extension where extname = 'vector'"
        ).fetchone()
        check(
            "pgvector extension installed",
            ext is not None,
            f"vector {ext['extversion']}" if ext else version,
        )
        cleanup(conn)  # remove leftovers from an earlier interrupted run
        try:
            conn.execute(
                "insert into filings (filing_id, company, form, fiscal_year, period_end) "
                "values (%s, 'SampleCo (synthetic)', '10-K', 2099, '2099-12-31')",
                (FILING_ID,),
            )
            for concept, value in (("revenue", 1000000), ("net_income", 150000)):
                conn.execute(
                    "insert into facts (filing_id, concept, raw_tag, period_start, period_end, "
                    "value, unit, source, page, confidence) "
                    "values (%s, %s, %s, '2099-01-01', '2099-12-31', %s, 'USD', 'xbrl', NULL, 1.0)",
                    (FILING_ID, concept, concept, value),
                )
            conn.execute(
                "insert into concept_aliases (raw_tag, concept) values ('Revenues', 'revenue')"
            )
            vectors = embed_documents([c[2] for c in CHUNKS])
            for (page, section, text), vec in zip(CHUNKS, vectors, strict=True):
                conn.execute(
                    "insert into chunks (filing_id, page, section, text, embedding) "
                    "values (%s, %s, %s, %s, %s)",
                    (FILING_ID, page, section, text, vec),
                )

            # Structured lookup
            r = get_fact("SampleCo", "revenue", 2099)
            check(
                "get_fact returns the stored value",
                len(r["rows"]) == 1
                and r["rows"][0]["value"] == 1000000
                and r["rows"][0]["source"] == "xbrl",
                str(r["rows"][0]["value"]) if r["rows"] else "no rows",
            )
            r = get_fact("SampleCo", "Revenues", 2099)
            check("get_fact maps an alias tag to the concept", len(r["rows"]) == 1)
            r = get_fact("SampleCo", "ebitda", 2099)
            check(
                "get_fact lists available concepts when nothing matches",
                r["rows"] == [] and "revenue" in r["available_concepts"],
                ", ".join(r.get("available_concepts", [])),
            )

            # Hybrid search
            r = search_filings("supply chain risk", company="SampleCo", fiscal_year=2099, k=3)
            top = r["chunks"][0]["text"] if r["chunks"] else ""
            check(
                "search_filings ranks the matching chunk first",
                "supply chain" in top.lower(),
                f"{len(r['chunks'])} chunks returned",
            )
            r = search_filings("supply chain risk", company="SampleCo", fiscal_year=2098)
            check("search_filings applies the fiscal year filter", r["chunks"] == [])
            r = search_filings("supply chain risk", company="OtherCo")
            check("search_filings applies the company filter", r["chunks"] == [])

            # Audit trail
            run_tool(
                QUESTION_TAG,
                "get_fact",
                {"company": "SampleCo", "concept": "revenue", "fiscal_year": 2099},
            )
            run_tool(
                QUESTION_TAG,
                "search_filings",
                {"query": "revenue decreased", "company": "SampleCo"},
            )
            n = conn.execute(
                "select count(*) as n from audit_log where question = %s", (QUESTION_TAG,)
            ).fetchone()["n"]
            check("audit_log records each tool call", n == 2, f"{n} rows")
        finally:
            cleanup(conn)

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
