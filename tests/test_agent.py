"""Tests for the tool-calling loop. The model client is replaced by a fake; no API calls."""

from types import SimpleNamespace

import pytest

from finrag import agent
from tests.conftest import AUDIT_TAG

pytestmark = pytest.mark.db


class FakeMessages:
    """Requests get_fact once, then returns a final answer."""

    def __init__(self):
        self.calls = 0
        self.last_tool_result = None

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            block = SimpleNamespace(
                type="tool_use",
                id="call-1",
                name="get_fact",
                input={"company": "SampleCo", "concept": "revenue", "fiscal_year": 2099},
            )
            return SimpleNamespace(stop_reason="tool_use", content=[block])
        self.last_tool_result = kwargs["messages"][-1]["content"][0]["content"]
        text = SimpleNamespace(type="text", text="Revenue was 1,000,000 USD.")
        return SimpleNamespace(stop_reason="end_turn", content=[text])


class LoopingMessages:
    """Always requests a tool, to test the round limit."""

    def create(self, **kwargs):
        block = SimpleNamespace(
            type="tool_use", id="loop", name="search_filings", input={"query": "revenue"}
        )
        return SimpleNamespace(stop_reason="tool_use", content=[block])


def _fake_client(messages):
    return lambda: SimpleNamespace(messages=messages)


def _audit_rows(conn):
    return conn.execute(
        "select tool, output_summary from audit_log where question = %s order by id", (AUDIT_TAG,)
    ).fetchall()


def test_answer_runs_tool_and_logs_call(sample_db, monkeypatch):
    sample_db.execute("delete from audit_log where question = %s", (AUDIT_TAG,))
    fake = FakeMessages()
    monkeypatch.setattr(agent.anthropic, "Anthropic", _fake_client(fake))

    text, evidence = agent.answer(AUDIT_TAG)

    assert text == "Revenue was 1,000,000 USD."
    assert [e["tool"] for e in evidence] == ["get_fact"]
    assert "1000000" in fake.last_tool_result and "2099-12-31" in fake.last_tool_result
    rows = _audit_rows(sample_db)
    assert [r["tool"] for r in rows] == ["get_fact"]


def test_tool_error_is_returned_and_logged(sample_db):
    sample_db.execute("delete from audit_log where question = %s", (AUDIT_TAG,))
    output = agent.run_tool(AUDIT_TAG, "get_fact", {"company": "SampleCo"})  # missing arguments
    assert "error" in output
    assert "error" in _audit_rows(sample_db)[0]["output_summary"]


def test_round_limit_stops_the_loop(sample_db, monkeypatch):
    monkeypatch.setattr(agent.anthropic, "Anthropic", _fake_client(LoopingMessages()))
    with pytest.raises(RuntimeError, match="tool rounds"):
        agent.answer(AUDIT_TAG)


def test_search_tool_asks_for_company_and_fiscal_year_filters():
    search = next(t for t in agent.TOOLS if t["name"] == "search_filings")
    assert "fiscal_year" in search["description"]
    assert "Every number in your answer must come from" in agent.SYSTEM


def test_get_fact_description_lists_loaded_concepts():
    from finrag.agent import TOOLS
    from finrag.sec_facts import CONCEPT_NAMES

    fact = next(t for t in TOOLS if t["name"] == "get_fact")
    description = fact["input_schema"]["properties"]["concept"]["description"]
    assert all(name in description for name in CONCEPT_NAMES)
