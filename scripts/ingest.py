"""Load the PDFs listed in the FinanceBench manifest into the database.

Usage:
    python scripts/ingest.py                         # development branch (DATABASE_URL)
    python scripts/ingest.py --target production     # needs PRODUCTION_DATABASE_URL

Each filing is skipped when its PDF hash and the pipeline version are unchanged.
Run `python scripts/financebench.py fetch` first.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finrag.config import database_url, describe_database  # noqa: E402
from finrag.db import apply_schema, connect  # noqa: E402
from finrag.embed import MODEL_MAX_TOKENS, count_tokens, embed_documents  # noqa: E402
from finrag.ingest import (  # noqa: E402
    build_chunks,
    filing_row,
    load_filing,
    needs_load,
    pipeline_version,
    stored_state,
)
from finrag.pdf_text import extract_pages, library_version  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TARGET_VARIABLES = {"development": "DATABASE_URL", "production": "PRODUCTION_DATABASE_URL"}


def select_target(target: str) -> None:
    """Point DATABASE_URL at the chosen environment for this process only."""
    variable = TARGET_VARIABLES[target]
    url = os.environ.get(variable)
    if not url:
        sys.exit(f"{variable} is not set; it is needed for --target {target}.")
    os.environ["DATABASE_URL"] = url


def ingest(documents: list[dict[str, Any]], pdf_dir: Path, version: str) -> dict[str, int]:
    """Load every changed document. Return counts of loaded and skipped filings and chunks."""
    stats = {"loaded": 0, "skipped": 0, "chunks": 0, "max_tokens": 0}
    with connect() as conn:
        for document in documents:
            row = filing_row(document)
            if not needs_load(stored_state(conn, row["filing_id"]), row["source_sha256"], version):
                stats["skipped"] += 1
                continue
            start = time.perf_counter()
            pages = extract_pages(pdf_dir / f"{row['filing_id']}.pdf")
            chunks = build_chunks(row, pages, count_tokens)
            load_filing(conn, row, chunks, embed_documents, version)
            longest = max((count_tokens(c.embedding_input()) for c in chunks), default=0)
            stats["max_tokens"] = max(stats["max_tokens"], longest)
            stats["loaded"] += 1
            stats["chunks"] += len(chunks)
            print(
                f"loaded {row['filing_id']}: {len(pages)} pages, {len(chunks)} chunks, "
                f"longest {longest} tokens, {time.perf_counter() - start:.1f}s"
            )
    return stats


def main() -> int:
    """Parse arguments, apply the schema, and load the manifest documents."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=sorted(TARGET_VARIABLES), default="development")
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "manifests" / "financebench_subset.json"
    )
    parser.add_argument("--pdf-dir", type=Path, default=ROOT / "data" / "financebench" / "pdfs")
    args = parser.parse_args()
    select_target(args.target)
    print(f"Target: {args.target}, {describe_database(database_url())}")
    apply_schema()
    documents = json.loads(args.manifest.read_text(encoding="utf-8"))["documents"]
    version = pipeline_version(library_version())
    stats = ingest(documents, args.pdf_dir, version)
    print(
        f"{stats['loaded']} loaded, {stats['skipped']} unchanged, {stats['chunks']} chunks; "
        f"longest chunk {stats['max_tokens']} tokens (model limit {MODEL_MAX_TOKENS})"
    )
    return 1 if stats["max_tokens"] >= MODEL_MAX_TOKENS else 0


if __name__ == "__main__":
    sys.exit(main())
