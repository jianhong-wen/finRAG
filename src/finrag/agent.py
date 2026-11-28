"""Tool-calling loop. The model decides which tool to call; every call is logged.

Usage:
    PYTHONPATH=src python -m finrag.agent "What was SampleCo revenue in 2099?"
"""

import json
import sys
import time
from collections.abc import Callable
from typing import Any

import anthropic
from anthropic.types import MessageParam, ToolParam, ToolResultBlockParam
from psycopg.types.json import Jsonb

from .config import MAX_TOOL_ROUNDS, MODEL
from .db import connect
from .sec_facts import CONCEPT_NAMES
from .tools import get_fact, search_filings

SYSTEM = (
    "You answer questions about company filings.\n"
    "1. Every number in your answer must come from get_fact or from a passage "
    "returned by search_filings.\n"
    "2. If get_fact and a document passage give different values for the same item, "
    "report both and state the difference.\n"
    "3. If no source supports an answer, say so. Do not estimate.\n"
    "4. Name the company, fiscal year, source, and page for each number.\n"
    "5. Do not give investment advice."
)

TOOLS: list[ToolParam] = [
    {
        "name": "get_fact",
        "description": (
            "Look up a figure reported in a 10-K (SEC XBRL data) for one company and "
            "fiscal year. Values are in the reported unit, usually whole US dollars. "
            "If the concept is not found, the result lists the concepts that exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "concept": {
                    "type": "string",
                    "description": "One of: " + ", ".join(CONCEPT_NAMES),
                },
                "fiscal_year": {"type": "integer"},
            },
            "required": ["company", "concept", "fiscal_year"],
        },
    },
    {
        "name": "search_filings",
        "description": (
            "Search filing text. Use it for explanations, risks, definitions, "
            "and figures that get_fact cannot return. Always pass company and "
            "fiscal_year when the question states them: results are far more precise "
            "with both filters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "company": {"type": "string"},
                "fiscal_year": {"type": "integer"},
                "k": {"type": "integer", "description": "Number of chunks, 1 to 20"},
            },
            "required": ["query"],
        },
    },
]

_IMPLEMENTATIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_fact": get_fact,
    "search_filings": search_filings,
}


def _summarize(tool: str, output: dict[str, Any]) -> dict[str, Any]:
    if tool == "get_fact":
        return {
            "rows": len(output["rows"]),
            "filings": sorted({r["filing_id"] for r in output["rows"]}),
        }
    return {"chunks": [c["chunk_id"] for c in output["chunks"]]}


def _log(
    question: str, tool: str, tool_input: dict[str, Any], summary: dict[str, Any], ms: int
) -> None:
    with connect(register_vectors=False) as conn:
        conn.execute(
            "insert into audit_log (question, tool, input, output_summary, latency_ms) "
            "values (%s, %s, %s, %s, %s)",
            (question, tool, Jsonb(tool_input), Jsonb(summary), ms),
        )


def run_tool(question: str, name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Run one tool, write one audit_log row, and return the tool output.

    A tool error is returned as {"error": message} so the model can react to it.
    """
    start = time.perf_counter()
    try:
        output = _IMPLEMENTATIONS[name](**tool_input)
        summary = _summarize(name, output)
    except Exception as exc:  # return the error to the model instead of stopping
        output, summary = {"error": str(exc)}, {"error": str(exc)}
    _log(question, name, tool_input, summary, int((time.perf_counter() - start) * 1000))
    return output


def answer(question: str) -> tuple[str, list[dict[str, Any]]]:
    """Answer a question with the tool-calling loop.

    Returns the final text and the evidence (each tool call with its output).
    Raises RuntimeError if there is no final answer after MAX_TOOL_ROUNDS rounds.
    """
    client = anthropic.Anthropic()
    messages: list[MessageParam] = [{"role": "user", "content": question}]
    evidence: list[dict[str, Any]] = []
    for _ in range(MAX_TOOL_ROUNDS):
        reply = client.messages.create(
            model=MODEL, max_tokens=1500, system=SYSTEM, tools=TOOLS, messages=messages
        )
        if reply.stop_reason != "tool_use":
            text = "".join(getattr(b, "text", "") for b in reply.content if b.type == "text")
            return text, evidence
        messages.append({"role": "assistant", "content": reply.content})
        results: list[ToolResultBlockParam] = []
        for block in reply.content:
            if block.type == "tool_use":
                output = run_tool(question, block.name, block.input)
                evidence.append({"tool": block.name, "input": block.input, "output": output})
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(output, default=str),
                    }
                )
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"No final answer after {MAX_TOOL_ROUNDS} tool rounds.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('Usage: PYTHONPATH=src python -m finrag.agent "your question"')
    text, evidence = answer(" ".join(sys.argv[1:]))
    print(text)
    print(f"\n[{len(evidence)} tool call(s) logged to audit_log]")
