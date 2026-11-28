"""Tests for FinanceBench subset selection, the manifest and verified downloads.

No network: downloads use fake fetchers and a fake opener.
"""

import io
from urllib.error import HTTPError, URLError

import pytest

from finrag.financebench import (
    COMMIT,
    DOCUMENTS_PATH,
    QUESTIONS_PATH,
    ChecksumError,
    DownloadError,
    build_manifest,
    download_verified,
    fetch_url,
    manifest_files,
    pdf_path,
    select_subset,
    sha256_hex,
)

QUESTIONS = [
    {"financebench_id": "fb_3", "company": "Beta", "doc_name": "BETA_2022_10K",
     "question_type": "metrics-generated", "question": "secret text?", "evidence": []},
    {"financebench_id": "fb_2", "company": "Alpha", "doc_name": "ALPHA_2022_10K",
     "question_type": "domain-relevant", "question": "secret text?",
     "evidence": [{"doc_name": "ALPHA_2021_10K"}]},
    {"financebench_id": "fb_1", "company": "Gamma", "doc_name": "GAMMA_2022_10K",
     "question_type": "novel-generated", "question": "secret text?", "evidence": []},
]  # fmt: skip
DOCUMENTS = [
    {"doc_name": name, "company": name.split("_")[0].title(), "doc_type": "10k",
     "doc_period": name.split("_")[1], "gics_sector": "Test", "doc_link": f"https://x/{name}"}
    for name in ("ALPHA_2021_10K", "ALPHA_2022_10K", "BETA_2022_10K", "GAMMA_2022_10K")
]  # fmt: skip


def test_select_subset_keeps_named_companies_sorted_with_cited_documents():
    questions, documents = select_subset(QUESTIONS, DOCUMENTS, ["Beta", "Alpha"])
    assert [q["financebench_id"] for q in questions] == ["fb_2", "fb_3"]
    assert [d["doc_name"] for d in documents] == [
        "ALPHA_2021_10K",  # cited only as evidence
        "ALPHA_2022_10K",
        "BETA_2022_10K",
    ]


def test_select_subset_rejects_unknown_company():
    with pytest.raises(ValueError, match="Delta"):
        select_subset(QUESTIONS, DOCUMENTS, ["Alpha", "Delta"])


def test_select_subset_rejects_document_without_metadata():
    with pytest.raises(ValueError, match="BETA_2022_10K"):
        select_subset(QUESTIONS, DOCUMENTS[:2], ["Beta"])


def _manifest():
    questions, documents = select_subset(QUESTIONS, DOCUMENTS, ["Alpha"])
    paths = [QUESTIONS_PATH, DOCUMENTS_PATH] + [pdf_path(d["doc_name"]) for d in documents]
    files = {p: (sha256_hex(p.encode()), len(p)) for p in paths}
    return build_manifest(questions, documents, files, "2026-11-27")


def test_manifest_pins_commit_and_omits_question_text():
    manifest = _manifest()
    assert manifest["source"]["commit"] == COMMIT
    assert all(COMMIT in entry["url"] for entry in manifest_files(manifest))
    assert "question" not in manifest["questions"][0]
    assert "secret text" not in str(manifest)


def test_manifest_records_original_link_and_hash_per_document():
    document = _manifest()["documents"][0]
    assert document["original_doc_link"] == "https://x/ALPHA_2021_10K"
    assert document["path"] == "pdfs/ALPHA_2021_10K.pdf"
    assert document["sha256"] == sha256_hex(b"pdfs/ALPHA_2021_10K.pdf")


def test_manifest_is_deterministic():
    assert _manifest() == _manifest()


def test_download_writes_file_with_matching_hash(tmp_path):
    dest = tmp_path / "pdfs" / "a.pdf"
    assert download_verified("https://h/a", dest, sha256_hex(b"pdf"), fetch=lambda url: b"pdf")
    assert dest.read_bytes() == b"pdf"


def test_download_skips_file_that_already_matches(tmp_path):
    dest = tmp_path / "a.pdf"
    dest.write_bytes(b"pdf")

    def must_not_fetch(url):
        raise AssertionError("fetch was called")

    assert not download_verified("https://h/a", dest, sha256_hex(b"pdf"), fetch=must_not_fetch)


def test_download_replaces_corrupted_file(tmp_path):
    dest = tmp_path / "a.pdf"
    dest.write_bytes(b"corrupted")
    assert download_verified("https://h/a", dest, sha256_hex(b"pdf"), fetch=lambda url: b"pdf")
    assert dest.read_bytes() == b"pdf"


def test_checksum_mismatch_raises_and_leaves_no_file(tmp_path):
    dest = tmp_path / "a.pdf"
    with pytest.raises(ChecksumError, match="expected sha256"):
        download_verified("https://h/a", dest, sha256_hex(b"pdf"), fetch=lambda url: b"other")
    assert list(tmp_path.iterdir()) == []


class FakeOpener:
    """Raise the queued errors in order, then return the body."""

    def __init__(self, errors, body=b"ok"):
        self.errors, self.body, self.calls = list(errors), body, 0

    def __call__(self, request, timeout):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return io.BytesIO(self.body)


def _http_error(code):
    return HTTPError("https://h/a", code, "error", {}, None)


def test_fetch_retries_network_and_server_errors_then_succeeds():
    opener = FakeOpener([URLError("reset"), _http_error(503)])
    waits: list[float] = []
    assert fetch_url("https://h/a", opener=opener, sleep=waits.append) == b"ok"
    assert opener.calls == 3
    assert waits == [2.0, 4.0]


def test_fetch_does_not_retry_client_errors():
    opener = FakeOpener([_http_error(404)])
    with pytest.raises(DownloadError, match="HTTP 404"):
        fetch_url("https://h/a", opener=opener, sleep=lambda s: None)
    assert opener.calls == 1


def test_fetch_gives_up_after_the_attempt_limit():
    opener = FakeOpener([TimeoutError()] * 5)
    with pytest.raises(DownloadError, match="after 3 attempts"):
        fetch_url("https://h/a", opener=opener, sleep=lambda s: None)
    assert opener.calls == 3


def test_fetch_rejects_non_https_urls():
    with pytest.raises(ValueError, match="https"):
        fetch_url("http://h/a", opener=FakeOpener([]), sleep=lambda s: None)
