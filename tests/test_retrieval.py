"""Tests for the search modes. Database tests use the synthetic SampleCo data."""

import pytest

from finrag.retrieval import MODES, SQL, search_chunks

LONG_QUERY = "What supply chain risk factors does the company describe in its filing?"


def test_unknown_mode_is_rejected_before_any_query():
    with pytest.raises(ValueError, match="Unknown search mode"):
        search_chunks("revenue", "fulltext")


def test_every_mode_has_fixed_parameterized_sql():
    assert set(SQL) == set(MODES)
    for mode, query in SQL.items():
        text = query.as_string(None)
        assert "%(company)s" in text and "%(k)s" in text
        assert ("%(q)s" in text) == ("keyword" in mode or "hybrid" in mode)
        assert ("%(qv)s" in text) == (mode != "keyword_and" and mode != "keyword_or")


db = pytest.mark.db


@db
def test_keyword_and_needs_every_word(sample_db):
    assert search_chunks(LONG_QUERY, "keyword_and", company="SampleCo", conn=sample_db) == []


@db
def test_keyword_or_finds_the_chunk_with_some_words(sample_db):
    rows = search_chunks(LONG_QUERY, "keyword_or", company="SampleCo", conn=sample_db)
    assert [r["page"] for r in rows] == [12]


@db
@pytest.mark.parametrize("mode", MODES)
def test_company_filter_applies_to_every_mode(sample_db, mode):
    assert search_chunks("supply chain", mode, company="OtherCo", conn=sample_db) == []


@db
@pytest.mark.parametrize("mode", ["vector", "hybrid_and", "hybrid_or"])
def test_vector_modes_return_all_sample_chunks_in_a_stable_order(sample_db, mode):
    first = search_chunks(LONG_QUERY, mode, company="SampleCo", k=10, conn=sample_db)
    second = search_chunks(LONG_QUERY, mode, company="SampleCo", k=10, conn=sample_db)
    assert len(first) == 3
    assert [r["chunk_id"] for r in first] == [r["chunk_id"] for r in second]


@db
def test_hybrid_or_ranks_the_keyword_match_first(sample_db):
    rows = search_chunks(LONG_QUERY, "hybrid_or", company="SampleCo", conn=sample_db)
    assert rows[0]["page"] == 12


def test_search_filings_uses_the_evaluated_mode(monkeypatch):
    """ADR 0009: the agent uses vector search, chosen on leakage-free evaluation scopes."""
    import finrag.tools as tools

    calls = []

    def fake_search(query, mode, **kwargs):
        calls.append(mode)
        return [{"text": "x" * 2000, "score": 1}]

    monkeypatch.setattr(tools, "search_chunks", fake_search)
    result = tools.search_filings("capital expenditures", company="3M", fiscal_year=2018)
    assert calls == ["vector"]
    assert len(result["chunks"][0]["text"]) == tools.TEXT_LIMIT
    assert isinstance(result["chunks"][0]["score"], float)
