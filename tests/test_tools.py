"""Tests for get_fact and search_filings against synthetic data."""

import pytest

from finrag.sample_data import SAMPLE_ALIAS_TAG, delete_sample_data
from finrag.tools import get_fact, search_filings

pytestmark = pytest.mark.db


def test_get_fact_returns_stored_value(sample_db):
    rows = get_fact("SampleCo", "revenue", 2099)["rows"]
    assert len(rows) == 1
    assert rows[0]["value"] == 1000000
    assert rows[0]["source"] == "xbrl"
    assert rows[0]["period_end"].isoformat() == "2099-12-31"


def test_get_fact_maps_alias_to_concept(sample_db):
    assert len(get_fact("SampleCo", SAMPLE_ALIAS_TAG, 2099)["rows"]) == 1


def test_get_fact_lists_available_concepts_when_missing(sample_db):
    result = get_fact("SampleCo", "ebitda", 2099)
    assert result["rows"] == []
    assert set(result["available_concepts"]) == {"net_income", "revenue"}


def test_get_fact_wrong_year_returns_nothing(sample_db):
    assert get_fact("SampleCo", "revenue", 2098)["rows"] == []


def test_get_fact_treats_input_as_data_not_sql(sample_db):
    result = get_fact("SampleCo' or '1'='1", "revenue", 2099)
    assert result["rows"] == []


def test_search_ranks_matching_chunk_first(sample_db):
    chunks = search_filings("supply chain risk", company="SampleCo", fiscal_year=2099, k=3)[
        "chunks"
    ]
    assert chunks
    assert "supply chain" in chunks[0]["text"].lower()
    assert chunks[0]["page"] == 12


@pytest.mark.parametrize(
    "kwargs",
    [
        {"company": "SampleCo", "fiscal_year": 2098},
        {"company": "OtherCo"},
    ],
)
def test_search_applies_filters(sample_db, kwargs):
    assert search_filings("supply chain risk", **kwargs)["chunks"] == []


@pytest.mark.parametrize("k, expected", [(0, 1), (2, 2), (100, 3)])
def test_search_clamps_k(sample_db, k, expected):
    # Only 3 chunks exist, so k above 3 returns 3.
    chunks = search_filings("revenue supply capital", company="SampleCo", k=k)["chunks"]
    assert len(chunks) == expected


def _alias_count(conn, raw_tag):
    return conn.execute(
        "select count(*) as n from concept_aliases where raw_tag = %s", (raw_tag,)
    ).fetchone()["n"]


def test_sample_cleanup_keeps_real_aliases(sample_db):
    """Regression: cleanup once deleted the alias of the real XBRL tag "Revenues"."""
    sample_db.execute(
        "insert into concept_aliases (raw_tag, concept) values ('Revenues', 'revenue')"
    )
    try:
        delete_sample_data(sample_db, "TEST-NO-SUCH-FILING", "pytest-cleanup-check")
        assert _alias_count(sample_db, "Revenues") == 1
        assert _alias_count(sample_db, SAMPLE_ALIAS_TAG) == 0
    finally:
        sample_db.execute("delete from concept_aliases where raw_tag = 'Revenues'")
        sample_db.execute(  # restore the shared sample alias for the other tests
            "insert into concept_aliases (raw_tag, concept) values (%s, 'revenue') "
            "on conflict do nothing",
            (SAMPLE_ALIAS_TAG,),
        )
