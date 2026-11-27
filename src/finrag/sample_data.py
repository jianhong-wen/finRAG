"""Synthetic sample data for the self-check script and the database tests.

Every row belongs to the fictional company "SampleCo (synthetic)", fiscal year 2099.
The alias tag is invented, so cleanup never removes a real XBRL alias.
"""

import psycopg
from psycopg.rows import DictRow

from .embed import embed_documents

SAMPLE_COMPANY = "SampleCo (synthetic)"
SAMPLE_YEAR = 2099
SAMPLE_ALIAS_TAG = "SampleCoTotalRevenue"
SAMPLE_REVENUE = 1_000_000
SAMPLE_FACTS: tuple[tuple[str, int], ...] = (("revenue", SAMPLE_REVENUE), ("net_income", 150_000))
SAMPLE_CHUNKS: tuple[tuple[int, str, str], ...] = (
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
)


def insert_sample_data(conn: psycopg.Connection[DictRow], filing_id: str) -> None:
    """Insert one synthetic filing with its facts, one alias tag and three text chunks."""
    conn.execute(
        "insert into filings (filing_id, company, form, fiscal_year, period_end) "
        "values (%s, %s, '10-K', %s, %s)",
        (filing_id, SAMPLE_COMPANY, SAMPLE_YEAR, f"{SAMPLE_YEAR}-12-31"),
    )
    for concept, value in SAMPLE_FACTS:
        conn.execute(
            "insert into facts (filing_id, concept, raw_tag, period_start, period_end, "
            "value, unit, source, confidence) "
            "values (%s, %s, %s, %s, %s, %s, 'USD', 'xbrl', 1.0)",
            (
                filing_id,
                concept,
                concept,
                f"{SAMPLE_YEAR}-01-01",
                f"{SAMPLE_YEAR}-12-31",
                value,
            ),
        )
    conn.execute(
        "insert into concept_aliases (raw_tag, concept) values (%s, 'revenue')",
        (SAMPLE_ALIAS_TAG,),
    )
    vectors = embed_documents([text for _, _, text in SAMPLE_CHUNKS])
    for (page, section, text), vector in zip(SAMPLE_CHUNKS, vectors, strict=True):
        conn.execute(
            "insert into chunks (filing_id, page, section, text, embedding) "
            "values (%s, %s, %s, %s, %s)",
            (filing_id, page, section, text, vector),
        )


def delete_sample_data(
    conn: psycopg.Connection[DictRow], filing_id: str, audit_question: str
) -> None:
    """Delete the synthetic filing, the synthetic alias and the audit rows of one run.

    Facts and chunks are removed with the filing (on delete cascade).
    """
    conn.execute("delete from filings where filing_id = %s", (filing_id,))
    conn.execute("delete from concept_aliases where raw_tag = %s", (SAMPLE_ALIAS_TAG,))
    conn.execute("delete from audit_log where question = %s", (audit_question,))
