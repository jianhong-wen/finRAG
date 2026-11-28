"""Build the FinanceBench subset manifest, or download the files it lists.

Usage:
    python scripts/financebench.py manifest --companies "American Express" JPMorgan ...
    python scripts/financebench.py fetch

`manifest` reads the pinned FinanceBench commit, selects the companies' questions and the
documents they cite, downloads them to data/financebench/, and writes the manifest.
`fetch` downloads every file in the manifest and checks its SHA-256. Files that already
match are skipped.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finrag.fileio import write_atomic  # noqa: E402
from finrag.financebench import (  # noqa: E402
    DOCUMENTS_PATH,
    QUESTIONS_PATH,
    Record,
    download_verified,
    fetch_url,
    manifest_files,
    parse_jsonl,
    pdf_path,
    raw_url,
    select_subset,
    sha256_hex,
)
from finrag.financebench import build_manifest as build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "manifests" / "financebench_subset.json"
DEFAULT_DEST = ROOT / "data" / "financebench"


def download_to(path: str, dest: Path, hashes: dict[str, tuple[str, int]]) -> bytes:
    """Download one repository file at the pinned commit, save it, and record its hash."""
    data = fetch_url(raw_url(path))
    write_atomic(dest / path, data)
    hashes[path] = (sha256_hex(data), len(data))
    return data


def make_manifest(companies: list[str], dest: Path, out: Path) -> Record:
    """Select the subset, download its files to dest, and write the manifest to out."""
    hashes: dict[str, tuple[str, int]] = {}
    questions = parse_jsonl(download_to(QUESTIONS_PATH, dest, hashes).decode("utf-8"))
    documents = parse_jsonl(download_to(DOCUMENTS_PATH, dest, hashes).decode("utf-8"))
    chosen, cited = select_subset(questions, documents, companies)
    for document in cited:
        download_to(pdf_path(document["doc_name"]), dest, hashes)
        print(f"downloaded {document['doc_name']}")
    manifest = build(chosen, cited, hashes, datetime.now(UTC).date().isoformat())
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    write_atomic(out, text.encode("utf-8"))
    return manifest


def fetch_all(manifest_path: Path, dest: Path) -> tuple[int, int]:
    """Download every manifest file that is missing or changed. Return (downloaded, kept)."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    downloaded = kept = 0
    for entry in manifest_files(manifest):
        if download_verified(entry["url"], dest / entry["path"], entry["sha256"]):
            downloaded += 1
            print(f"downloaded {entry['path']}")
        else:
            kept += 1
    return downloaded, kept


def main() -> int:
    """Parse the command line and run the chosen command."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("manifest", help="select a subset and write the manifest")
    make.add_argument("--companies", nargs="+", required=True)
    make.add_argument("--out", type=Path, default=DEFAULT_MANIFEST)
    get = commands.add_parser("fetch", help="download and verify the manifest files")
    get.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    for sub in (make, get):
        sub.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()
    if args.command == "manifest":
        manifest = make_manifest(args.companies, args.dest, args.out)
        print(
            f"{len(manifest['questions'])} questions, {len(manifest['documents'])} documents, "
            f"{len(manifest['companies'])} companies -> {args.out}"
        )
    else:
        downloaded, kept = fetch_all(args.manifest, args.dest)
        print(f"{downloaded} downloaded, {kept} already up to date -> {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
