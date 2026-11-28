"""Measure retrieval on the FinanceBench subset: keyword, vector and hybrid search.

Usage:
    python scripts/evaluate_retrieval.py
    python scripts/evaluate_retrieval.py --modes vector hybrid_or --scopes company

Reads the questions from data/financebench/ (run `python scripts/financebench.py fetch`
first) and searches the database in DATABASE_URL, the development branch. It only reads.
Scopes: "corpus" uses no filter; "parsed" filters by the company and year read from the
question text; "oracle" uses the FinanceBench labels (upper bound only, it leaks labels).
Writes results/retrieval/<UTC date>.json and prints a summary table.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import DictRow

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finrag.config import database_url, describe_database  # noqa: E402
from finrag.db import connect  # noqa: E402
from finrag.embed import EMBED_MODEL, embed_query  # noqa: E402
from finrag.evaluation import (  # noqa: E402
    KS,
    SCOPE_DESCRIPTIONS,
    SCOPES,
    evidence_pages,
    first_document_rank,
    first_hit_rank,
    scope_filters,
    summarize_by,
)
from finrag.fileio import write_atomic  # noqa: E402
from finrag.financebench import QUESTIONS_PATH, parse_jsonl  # noqa: E402
from finrag.retrieval import MAX_K, MODES, search_chunks  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def fiscal_years(manifest_path: Path) -> dict[str, int]:
    """Return {document name: fiscal year} for the manifest's documents."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {d["doc_name"]: int(str(d["doc_period"])[:4]) for d in manifest["documents"]}


def load_questions(manifest_path: Path, data_dir: Path) -> list[dict[str, Any]]:
    """Return the manifest's questions with their text and evidence, sorted by id.

    Raises ValueError if a manifest question is missing from the downloaded file.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    wanted = {q["financebench_id"] for q in manifest["questions"]}
    text = (data_dir / QUESTIONS_PATH).read_text(encoding="utf-8")
    found = {q["financebench_id"]: q for q in parse_jsonl(text) if q["financebench_id"] in wanted}
    missing = sorted(wanted - found.keys())
    if missing:
        raise ValueError(f"Questions missing from the data file: {', '.join(missing)}")
    return [found[i] for i in sorted(found)]


def evaluate_question(
    conn: psycopg.Connection[DictRow],
    question: dict[str, Any],
    modes: list[str],
    scopes: list[str],
    years: dict[str, int],
) -> list[dict[str, Any]]:
    """Run every mode and scope for one question; return one record per combination."""
    evidence = evidence_pages(question)
    documents = {doc for doc, _ in evidence}
    vector = embed_query(question["question"])
    records = []
    for scope in scopes:
        company, year = scope_filters(question, scope, years)
        for mode in modes:
            rows = search_chunks(
                question["question"],
                mode,
                company=company,
                fiscal_year=year,
                k=MAX_K,
                conn=conn,
                query_vector=vector,
            )
            pages = [(r["filing_id"], r["page"]) for r in rows]
            records.append(
                {
                    "financebench_id": question["financebench_id"],
                    "company": question["company"],
                    "question_type": question["question_type"],
                    "scope": scope,
                    "mode": mode,
                    "page_rank": first_hit_rank(pages, evidence),
                    "doc_rank": first_document_rank([p[0] for p in pages], documents),
                    "top5": [f"{doc} p{page}" for doc, page in pages[:5]],
                }
            )
    return records


def summaries(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Summarize page and document ranks per scope and mode, overall and per question type."""
    result: dict[str, dict[str, Any]] = {}
    for scope in sorted({r["scope"] for r in records}):
        result[scope] = {}
        for mode in [m for m in MODES if any(r["mode"] == m for r in records)]:
            subset = [r for r in records if r["scope"] == scope and r["mode"] == mode]
            result[scope][mode] = {
                "pages": summarize_by(subset, "question_type"),
                "documents": summarize_by(subset, "question_type", rank_field="doc_rank")["all"],
            }
    return result


def print_table(summary: dict[str, dict[str, Any]]) -> None:
    """Print recall@k and MRR for evidence pages, one line per scope and mode."""
    header = "".join(f"{'R@' + str(k):>8}" for k in KS)
    print(f"\n{'scope':13} {'mode':12}{header}{'MRR':>8}{'doc R@5':>9}")
    for scope, modes in summary.items():
        for mode, result in modes.items():
            pages = result["pages"]["all"]
            cells = "".join(f"{pages[f'recall@{k}']:8.3f}" for k in KS)
            doc = result["documents"]["recall@5"]
            print(f"{scope:13} {mode:12}{cells}{pages['mrr']:8.3f}{doc:9.3f}")


def main() -> int:
    """Parse arguments, run the evaluation, write the results file, print the summary."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--scopes", nargs="+", choices=SCOPES, default=list(SCOPES))
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "manifests" / "financebench_subset.json"
    )
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "financebench")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    print(f"Target: {describe_database(database_url())}")
    questions = load_questions(args.manifest, args.data_dir)
    years = fiscal_years(args.manifest)
    records: list[dict[str, Any]] = []
    with connect() as conn:
        for number, question in enumerate(questions, start=1):
            records.extend(evaluate_question(conn, question, args.modes, args.scopes, years))
            print(f"\r{number}/{len(questions)} questions", end="", flush=True)
        versions = [
            r["pipeline_version"]
            for r in conn.execute(
                "select distinct pipeline_version from filings order by 1"
            ).fetchall()
        ]
    summary = summaries(records)
    print_table(summary)
    date = datetime.now(UTC).date().isoformat()
    out = args.out or ROOT / "results" / "retrieval" / f"{date}.json"
    payload = {
        "date_utc": date,
        "questions": len(questions),
        "k": MAX_K,
        "embedding_model": EMBED_MODEL,
        "pipeline_versions": versions,
        "page_rule": "FinanceBench evidence_page_num + 1 = chunks.page",
        "scopes": {s: SCOPE_DESCRIPTIONS[s] for s in args.scopes},
        "summary": summary,
        "records": records,
    }
    write_atomic(out, (json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    print(f"\nResults: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
