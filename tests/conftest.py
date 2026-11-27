"""Shared test fixtures.

Database tests insert SYNTHETIC rows only (company "SampleCo", fiscal year 2099)
and delete them afterwards. They are skipped when DATABASE_URL is not set.
"""

import os

import pytest

# Tests must not download models or call the network.
os.environ.setdefault("EMBED_BACKEND", "hash")

FILING_ID = "TEST-SAMPLE-0001"
AUDIT_TAG = "pytest"
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


def _cleanup(conn) -> None:
    conn.execute("delete from filings where filing_id = %s", (FILING_ID,))
    conn.execute("delete from concept_aliases where raw_tag = 'Revenues'")
    conn.execute("delete from audit_log where question = %s", (AUDIT_TAG,))


@pytest.fixture(scope="session")
def sample_db():
    """Apply the schema and load synthetic sample data for one test session."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")

    from finrag.db import apply_schema, connect
    from finrag.embed import embed_documents

    apply_schema()
    with connect() as conn:
        _cleanup(conn)  # remove leftovers from an interrupted run
        conn.execute(
            "insert into filings (filing_id, company, form, fiscal_year, period_end) "
            "values (%s, 'SampleCo (synthetic)', '10-K', 2099, '2099-12-31')",
            (FILING_ID,),
        )
        for concept, value in (("revenue", 1000000), ("net_income", 150000)):
            conn.execute(
                "insert into facts (filing_id, concept, raw_tag, period_start, period_end, "
                "value, unit, source, confidence) "
                "values (%s, %s, %s, '2099-01-01', '2099-12-31', %s, 'USD', 'xbrl', 1.0)",
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
        try:
            yield conn
        finally:
            _cleanup(conn)
