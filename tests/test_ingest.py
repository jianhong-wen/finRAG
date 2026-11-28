"""Tests for PDF extraction and filing loading. Database tests use synthetic filings only."""

import pytest

from finrag.embed import embed_documents, estimate_tokens
from finrag.ingest import (
    build_chunks,
    context_line,
    filing_row,
    load_filing,
    needs_load,
    pipeline_version,
    stored_state,
)
from finrag.pdf_text import extract_pages
from finrag.tools import search_filings
from tests.pdf_fixture import make_pdf

DOCUMENT = {
    "doc_name": "TEST-INGEST-2099_10K",
    "company": "SampleCo (synthetic)",
    "doc_type": "10k",
    "doc_period": 2099,
    "original_doc_link": "https://example.com/sampleco-2099.pdf",
    "sha256": "a" * 64,
}
PAGES = [
    ["SampleCo Annual Report 2099", "Risk Factors", "Helium supply could become scarce."],
    ["Consolidated Statement of Cash Flows", "(Millions) 2099 2098", "Capital spending (77) (66)"],
]


def test_extract_pages_returns_text_per_page_in_order(tmp_path):
    path = tmp_path / "sample.pdf"
    path.write_bytes(make_pdf(PAGES))
    pages = extract_pages(path)
    assert len(pages) == 2
    assert pages[0].splitlines()[:2] == ["SampleCo Annual Report 2099", "Risk Factors"]
    assert "Capital spending (77) (66)" in pages[1]


def test_extract_pages_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_pages(tmp_path / "missing.pdf")


def test_filing_row_maps_form_and_fiscal_year():
    row = filing_row(DOCUMENT | {"doc_type": "Earnings", "doc_period": 2023})
    assert (row["form"], row["fiscal_year"]) == ("Earnings release", 2023)
    assert row["source_url"] == DOCUMENT["original_doc_link"]


def test_filing_row_rejects_unknown_form():
    with pytest.raises(ValueError, match="unknown document type"):
        filing_row(DOCUMENT | {"doc_type": "prospectus"})


def test_chunks_carry_one_based_page_and_context():
    chunks = build_chunks(filing_row(DOCUMENT), ["first page", "", "third page"], estimate_tokens)
    assert [c.page for c in chunks] == [1, 3]
    assert chunks[1].context == "SampleCo (synthetic) | 10-K | FY2099 | page 3"
    assert chunks[1].embedding_input() == f"{chunks[1].context}\nthird page"


def test_context_line_format():
    assert context_line(filing_row(DOCUMENT), 60).endswith("| 10-K | FY2099 | page 60")


def test_reload_only_when_file_or_pipeline_changes():
    assert needs_load(None, "h1", "v1")
    assert not needs_load(("h1", "v1"), "h1", "v1")
    assert needs_load(("h1", "v1"), "h2", "v1")
    assert needs_load(("h1", "v1"), "h1", "v2")


def test_pipeline_version_names_parser_chunking_and_model():
    version = pipeline_version("9.9")
    assert "pypdfium2 9.9" in version
    assert "chunks 350/50" in version


@pytest.mark.db
def test_load_filing_replaces_chunks_and_is_searchable(sample_db, tmp_path):
    path = tmp_path / "sample.pdf"
    path.write_bytes(make_pdf(PAGES))
    row = filing_row(DOCUMENT)
    chunks = build_chunks(row, extract_pages(path), estimate_tokens)
    try:
        load_filing(sample_db, row, chunks, embed_documents, "v1")
        load_filing(sample_db, row, chunks, embed_documents, "v2")  # reload: no duplicates
        count = sample_db.execute(
            "select count(*) as n from chunks where filing_id = %s", (row["filing_id"],)
        ).fetchone()["n"]
        assert count == len(chunks) == 2
        assert stored_state(sample_db, row["filing_id"]) == (DOCUMENT["sha256"], "v2")
        top = search_filings("helium supply", company="SampleCo", fiscal_year=2099)["chunks"][0]
        assert (top["filing_id"], top["page"]) == (row["filing_id"], 1)
    finally:
        sample_db.execute("delete from filings where filing_id = %s", (row["filing_id"],))
