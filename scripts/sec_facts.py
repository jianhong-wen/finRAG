"""Download SEC XBRL company facts, load current-period values, and check them.

Usage:
    python scripts/sec_facts.py fetch               # download files missing from data/sec/
    python scripts/sec_facts.py fetch --refresh     # take a new snapshot and rewrite the manifest
    python scripts/sec_facts.py load                # development branch (DATABASE_URL)
    python scripts/sec_facts.py load --target production   # needs PRODUCTION_DATABASE_URL
    python scripts/sec_facts.py check               # compare get_fact with FinanceBench answers

Requests name the client with SEC_USER_AGENT (see .env.example). There are five requests
in total, far below the SEC limit of ten per second.
`check` uses FinanceBench answers for scoring only; they are never written to the database.
"""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finrag.config import database_url, describe_database  # noqa: E402
from finrag.db import apply_schema, connect  # noqa: E402
from finrag.fileio import write_atomic  # noqa: E402
from finrag.financebench import fetch_url, parse_jsonl, sha256_hex  # noqa: E402
from finrag.ingest import needs_load, stored_state  # noqa: E402
from finrag.sec_facts import (  # noqa: E402
    COMPANIES,
    FACT_CHECKS,
    build_manifest,
    company_by_name,
    filing_row,
    load_annual_filing,
    manifest_entry,
    parse_answer,
    pipeline_version,
    sec_user_agent,
    select_annual_facts,
    sync_aliases,
    within_tolerance,
)
from finrag.tools import get_fact  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "manifests" / "sec_companyfacts.json"
DEFAULT_DEST = ROOT / "data" / "sec"
QUESTIONS = ROOT / "data" / "financebench" / "data" / "financebench_open_source.jsonl"
TARGET_VARIABLES = {"development": "DATABASE_URL", "production": "PRODUCTION_DATABASE_URL"}
PAUSE_SECONDS = 0.5


def download(url: str) -> bytes:
    """Download one SEC file with the configured User-Agent."""
    data = fetch_url(url, user_agent=sec_user_agent())
    time.sleep(PAUSE_SECONDS)
    return data


def take_snapshot(manifest_path: Path, dest: Path) -> None:
    """Download every company file and write a new manifest."""
    entries = []
    for company in COMPANIES:
        data = download(company.url)
        entry = manifest_entry(company, data)
        write_atomic(dest / company.file_name, data)
        entries.append(entry)
        print(f"downloaded {company.name}: {entry['entity_name']}, {len(data):,} bytes")
    manifest = build_manifest(entries, datetime.now(UTC).date().isoformat())
    write_atomic(manifest_path, (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    print(f"manifest written -> {manifest_path}")


def fetch_missing(manifest_path: Path, dest: Path) -> int:
    """Download files missing locally; stop if the SEC data no longer matches the snapshot."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["companies"]:
        path = dest / entry["path"]
        if path.is_file() and sha256_hex(path.read_bytes()) == entry["sha256"]:
            print(f"up to date {entry['company']}")
            continue
        data = download(entry["url"])
        if sha256_hex(data) != entry["sha256"]:
            print(
                f"{entry['company']}: the SEC data changed after the snapshot of "
                f"{manifest['source']['retrieved']}. Run `fetch --refresh` to take a new "
                "snapshot, then load and check again."
            )
            return 1
        write_atomic(path, data)
        print(f"downloaded {entry['company']}")
    return 0


def select_target(target: str) -> None:
    """Point DATABASE_URL at the chosen environment for this process only."""
    variable = TARGET_VARIABLES[target]
    url = os.environ.get(variable)
    if not url:
        sys.exit(f"{variable} is not set; it is needed for --target {target}.")
    os.environ["DATABASE_URL"] = url


def load(manifest_path: Path, dest: Path) -> int:
    """Load the current-period facts of every 10-K in the snapshot."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = pipeline_version()
    status = 0
    with connect() as conn:
        added = sync_aliases(conn)
        print(f"concept aliases: {len(added)} added")
        for entry in manifest["companies"]:
            data = (dest / entry["path"]).read_bytes()
            if sha256_hex(data) != entry["sha256"]:
                sys.exit(f"{entry['path']} does not match the manifest; run `fetch` first.")
            company = company_by_name(entry["company"])
            counts = {"loaded": 0, "unchanged": 0, "facts": 0}
            for filing in select_annual_facts(json.loads(data)):
                row = filing_row(company, filing, entry["sha256"])
                if filing.fiscal_year != filing.sec_fiscal_year:
                    print(
                        f"  note: {filing.accession} ends {filing.period_end}; stored as "
                        f"FY{filing.fiscal_year}, the SEC fy field says {filing.sec_fiscal_year}"
                    )
                for conflict in filing.conflicts:
                    print(f"  skipped in FY{filing.fiscal_year}: {conflict}")
                    status = 1
                if not needs_load(stored_state(conn, row["filing_id"]), entry["sha256"], version):
                    counts["unchanged"] += 1
                    continue
                load_annual_filing(conn, row, filing.facts, version)
                counts["loaded"] += 1
                counts["facts"] += len(filing.facts)
            print(
                f"{company.name}: {counts['loaded']} filings loaded ({counts['facts']} facts), "
                f"{counts['unchanged']} unchanged"
            )
    return status


def check(results_dir: Path) -> int:
    """Compare get_fact values with FinanceBench answers and write a result file."""
    answers = {q["financebench_id"]: q["answer"] for q in parse_jsonl(QUESTIONS.read_text())}
    records: list[dict[str, Any]] = []
    for case in FACT_CHECKS:
        expected = parse_answer(answers[case.question_id])
        total = Decimal(0)
        missing = []
        for concept, sign in case.terms:
            rows = get_fact(case.company, concept, case.fiscal_year)["rows"]
            if not rows:
                missing.append(concept)
                continue
            total += sign * Decimal(rows[0]["value"])
        computed = (total / case.scale).quantize(Decimal("0.01"))
        ok = not missing and within_tolerance(computed, expected)
        records.append(
            {
                "question_id": case.question_id,
                "company": case.company,
                "fiscal_year": case.fiscal_year,
                "terms": [list(t) for t in case.terms],
                "computed": str(computed),
                "expected": str(expected),
                "missing": missing,
                "ok": ok,
            }
        )
        print(
            f"{'ok  ' if ok else 'FAIL'} {case.question_id} {case.company} FY{case.fiscal_year}: "
            f"computed {computed}, FinanceBench {expected}"
            + (f", missing {missing}" if missing else "")
        )
    date = datetime.now(UTC).date().isoformat()
    result = {
        "label_use": "FinanceBench answers are used only to score loaded facts.",
        "tolerance": "1 percent relative (FinanceBench answers are rounded)",
        "records": records,
    }
    out = results_dir / f"{date}.json"
    write_atomic(out, (json.dumps(result, indent=2) + "\n").encode("utf-8"))
    passed = sum(r["ok"] for r in records)
    print(f"{passed} of {len(records)} checks passed -> {out}")
    return 0 if passed == len(records) else 1


def main() -> int:
    """Parse the command line and run the chosen command."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    get = commands.add_parser("fetch", help="download the snapshot files")
    get.add_argument("--refresh", action="store_true", help="take a new snapshot")
    put = commands.add_parser("load", help="load current-period facts")
    put.add_argument("--target", choices=sorted(TARGET_VARIABLES), default="development")
    commands.add_parser("check", help="compare get_fact with FinanceBench answers")
    for sub in (get, put):
        sub.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
        sub.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()
    if args.command == "fetch":
        if args.refresh or not args.manifest.is_file():
            take_snapshot(args.manifest, args.dest)
            return 0
        return fetch_missing(args.manifest, args.dest)
    if args.command == "load":
        select_target(args.target)
        print(f"Target: {args.target}, {describe_database(database_url())}")
        apply_schema()
        return load(args.manifest, args.dest)
    print(f"Target: development, {describe_database(database_url())}")
    return check(ROOT / "results" / "xbrl_check")


if __name__ == "__main__":
    sys.exit(main())
