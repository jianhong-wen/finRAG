"""Tests for retrieval metrics. No database needed."""

import pytest

from finrag.evaluation import (
    evidence_pages,
    first_document_rank,
    first_hit_rank,
    scope_filters,
    summarize,
    summarize_by,
)


def test_financebench_pages_are_shifted_to_one_based_chunk_pages():
    question = {"evidence": [{"doc_name": "3M_2018_10K", "evidence_page_num": 59}]}
    assert evidence_pages(question) == {("3M_2018_10K", 60)}


def test_question_without_evidence_is_rejected():
    with pytest.raises(ValueError, match="fb_9"):
        evidence_pages({"financebench_id": "fb_9", "evidence": []})


def test_first_hit_rank_is_one_based():
    retrieved = [("A", 1), ("A", 2), ("B", 7)]
    assert first_hit_rank(retrieved, {("B", 7), ("A", 2)}) == 2


def test_same_page_number_in_another_document_is_not_a_hit():
    assert first_hit_rank([("A", 7)], {("B", 7)}) is None


def test_first_document_rank():
    assert first_document_rank(["A", "B", "B"], {"B"}) == 2
    assert first_document_rank(["A"], {"B"}) is None


def test_summarize_recall_and_mrr():
    summary = summarize([1, 3, None, 10])
    assert summary["recall@1"] == 0.25
    assert summary["recall@3"] == 0.5
    assert summary["recall@5"] == 0.5
    assert summary["recall@10"] == 0.75
    assert summary["recall@20"] == 0.75
    assert summary["mrr"] == round((1 + 1 / 3 + 1 / 10) / 4, 4)


def test_summarize_rejects_empty_input():
    with pytest.raises(ValueError):
        summarize([])


def test_summarize_by_reports_all_first_then_groups_by_name():
    records = [
        {"question_type": "b", "page_rank": 1},
        {"question_type": "a", "page_rank": None},
        {"question_type": "b", "page_rank": 2},
    ]
    result = summarize_by(records, "question_type")
    assert list(result) == ["all", "a", "b"]
    assert result["all"]["n"] == 3
    assert result["a"]["recall@20"] == 0.0
    assert result["b"]["recall@1"] == 0.5


QUESTION = {
    "company": "3M",
    "doc_name": "3M_2022_10K",
    "question": "Is 3M a capital-intensive business based on FY2022 data?",
}


@pytest.mark.parametrize(
    "scope, expected",
    [("corpus", (None, None)), ("parsed", ("3M", 2022)), ("oracle", ("3M", 2022))],
)
def test_scope_filters(scope, expected):
    assert scope_filters(QUESTION, scope, {"3M_2022_10K": 2022}) == expected


def test_parsed_scope_ignores_labels_and_reads_only_the_question():
    question = QUESTION | {"company": "Best Buy", "question": "Is 3M capital-intensive?"}
    assert scope_filters(question, "parsed", {"3M_2022_10K": 2022}) == ("3M", None)


def test_unknown_scope_is_rejected():
    with pytest.raises(ValueError, match="Unknown scope"):
        scope_filters(QUESTION, "company_year", {})
