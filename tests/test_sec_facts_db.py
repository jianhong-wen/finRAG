"""Load synthetic SEC facts into the test database and read them back with get_fact."""

import pytest

from finrag.ingest import stored_state
from finrag.sec_facts import (
    filing_row,
    load_annual_filing,
    pipeline_version,
    select_annual_facts,
    sync_aliases,
)
from finrag.tools import get_fact
from tests.sec_fixture import SAMPLE_SEC_COMPANY, companyfacts

pytestmark = pytest.mark.db

PREFIX = "TEST-SEC-"


@pytest.fixture
def sec_rows(sample_db):
    """Load the synthetic FY2099 10-K, then remove it and any alias the test added."""
    filing = select_annual_facts(companyfacts())[1]
    row = filing_row(SAMPLE_SEC_COMPANY, filing, "synthetic-sha", prefix=PREFIX)
    added = sync_aliases(sample_db)
    try:
        load_annual_filing(sample_db, row, filing.facts, pipeline_version())
        yield sample_db, row, filing
    finally:
        sample_db.execute("delete from filings where filing_id like %s", (PREFIX + "%",))
        sample_db.execute("delete from concept_aliases where raw_tag = any(%s)", (added,))


def test_get_fact_returns_current_period_value(sec_rows):
    rows = get_fact("SampleCo", "capex", 2099)["rows"]
    assert [r["value"] for r in rows] == [90]
    assert rows[0]["filing_id"].startswith(PREFIX)
    assert rows[0]["source_url"].startswith("https://www.sec.gov/Archives/edgar/data/9999999/")


def test_get_fact_accepts_xbrl_tag(sec_rows):
    rows = get_fact("SampleCo", "PaymentsToAcquirePropertyPlantAndEquipment", 2099)["rows"]
    assert [r["value"] for r in rows] == [90]


def test_reload_replaces_facts(sec_rows):
    conn, row, filing = sec_rows
    load_annual_filing(conn, row, filing.facts[:1], pipeline_version())
    n = conn.execute(
        "select count(*) as n from facts where filing_id = %s", (row["filing_id"],)
    ).fetchone()["n"]
    assert n == 1


def test_stored_state_records_snapshot_and_version(sec_rows):
    conn, row, _ = sec_rows
    assert stored_state(conn, row["filing_id"]) == ("synthetic-sha", pipeline_version())
