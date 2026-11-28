"""FinanceBench open sample: subset selection, manifest building and verified downloads.

Source: github.com/patronus-ai/financebench at a pinned commit (ADR 0006). The manifest
holds question ids and document metadata only. Question text and PDFs are downloaded to
data/, which is never committed.
"""

import hashlib
import json
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .fileio import write_atomic

REPOSITORY = "patronus-ai/financebench"
COMMIT = "cc39aeb4afdf33909ee1412188bf89035950c2eb"
QUESTIONS_PATH = "data/financebench_open_source.jsonl"
DOCUMENTS_PATH = "data/financebench_document_information.jsonl"
LICENSE = "CC-BY-NC-4.0 (Hugging Face dataset card); the GitHub repository has no license file"
PAPER = "https://arxiv.org/abs/2311.11944"
TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 2.0
USER_AGENT = "finrag-portfolio-project"
QUESTION_FIELDS = ("financebench_id", "company", "doc_name", "question_type", "question_reasoning")
DOCUMENT_FIELDS = ("doc_name", "company", "gics_sector", "doc_type", "doc_period")

Record = dict[str, Any]
Fetcher = Callable[[str], bytes]


class DownloadError(RuntimeError):
    """A file could not be downloaded."""


class ChecksumError(ValueError):
    """Downloaded content does not match the expected SHA-256."""


def raw_url(path: str, commit: str = COMMIT) -> str:
    """Return the raw.githubusercontent.com URL of a repository file at a commit."""
    return f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/{path}"


def pdf_path(doc_name: str) -> str:
    """Return the repository path of a document's PDF."""
    return f"pdfs/{doc_name}.pdf"


def parse_jsonl(text: str) -> list[Record]:
    """Parse JSON Lines text into a list of records, skipping blank lines."""
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 digest of data as a hex string."""
    return hashlib.sha256(data).hexdigest()


def select_subset(
    questions: list[Record], documents: list[Record], companies: Iterable[str]
) -> tuple[list[Record], list[Record]]:
    """Return the questions of the named companies and every document they cite.

    Both lists are sorted (questions by id, documents by name). Raises ValueError for a
    company with no questions, or for a cited document that has no metadata row.
    """
    wanted = set(companies)
    unknown = sorted(wanted - {q["company"] for q in questions})
    if unknown:
        raise ValueError(f"No FinanceBench questions for: {', '.join(unknown)}")
    chosen = sorted(
        (q for q in questions if q["company"] in wanted), key=lambda q: q["financebench_id"]
    )
    cited = {q["doc_name"] for q in chosen}
    cited |= {e["doc_name"] for q in chosen for e in q.get("evidence", [])}
    by_name = {d["doc_name"]: d for d in documents}
    missing = sorted(cited - by_name.keys())
    if missing:
        raise ValueError(f"Documents without metadata: {', '.join(missing)}")
    return chosen, [by_name[name] for name in sorted(cited)]


def build_manifest(
    questions: list[Record],
    documents: list[Record],
    files: dict[str, tuple[str, int]],
    retrieved: str,
) -> Record:
    """Build the manifest from selected records and {repository path: (sha256, bytes)}.

    retrieved is the UTC date of the download (YYYY-MM-DD).

    Question text is not stored. Raises KeyError if a needed file has no hash.
    """

    def file_entry(path: str) -> Record:
        sha256, size = files[path]
        return {"path": path, "url": raw_url(path), "sha256": sha256, "bytes": size}

    return {
        "source": {
            "repository": f"https://github.com/{REPOSITORY}",
            "commit": COMMIT,
            "license": LICENSE,
            "paper": PAPER,
            "retrieved": retrieved,
        },
        "companies": sorted({q["company"] for q in questions}),
        "metadata_files": [file_entry(QUESTIONS_PATH), file_entry(DOCUMENTS_PATH)],
        "questions": [{k: q.get(k) for k in QUESTION_FIELDS} for q in questions],
        "documents": [
            {k: d.get(k) for k in DOCUMENT_FIELDS}
            | {"original_doc_link": d.get("doc_link")}
            | file_entry(pdf_path(d["doc_name"]))
            for d in documents
        ],
    }


def manifest_files(manifest: Record) -> list[Record]:
    """Return every file entry of a manifest: metadata files first, then the PDFs."""
    return list(manifest["metadata_files"]) + list(manifest["documents"])


def fetch_url(
    url: str,
    *,
    attempts: int = MAX_ATTEMPTS,
    opener: Callable[..., Any] = urlopen,
    sleep: Callable[[float], None] = time.sleep,
    user_agent: str = USER_AGENT,
) -> bytes:
    """Download an https URL, retrying network and server errors with backoff.

    Client errors (HTTP 4xx) are not retried. Raises DownloadError when all attempts fail.
    """
    if not url.startswith("https://"):
        raise ValueError(f"Only https URLs are allowed: {url}")
    request = Request(url, headers={"User-Agent": user_agent})  # noqa: S310 (https only)
    for attempt in range(1, attempts + 1):
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                return bytes(response.read())
        except (URLError, TimeoutError) as exc:
            if isinstance(exc, HTTPError) and exc.code < 500:
                raise DownloadError(f"{url}: HTTP {exc.code}") from exc
            if attempt == attempts:
                raise DownloadError(f"{url}: failed after {attempts} attempts: {exc}") from exc
            sleep(BACKOFF_SECONDS * attempt)
    raise DownloadError(f"{url}: no attempt was made")  # only reached when attempts < 1


def download_verified(url: str, dest: Path, sha256: str, fetch: Fetcher = fetch_url) -> bool:
    """Make dest hold the file at url with the given SHA-256.

    Returns False if dest already matched, True if it was downloaded. Raises ChecksumError
    if the downloaded content does not match; dest is then left unchanged.
    """
    if dest.is_file() and sha256_hex(dest.read_bytes()) == sha256:
        return False
    data = fetch(url)
    actual = sha256_hex(data)
    if actual != sha256:
        raise ChecksumError(f"{url}: expected sha256 {sha256}, got {actual}")
    write_atomic(dest, data)
    return True
