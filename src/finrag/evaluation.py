"""Retrieval metrics for FinanceBench questions (pure functions, no I/O).

A retrieved chunk is a hit when its (filing_id, page) is an evidence page of the
question. FinanceBench page numbers are 0-based; chunks.page is 1-based (ADR 0007).
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from .query_filters import parse_filters

FINANCEBENCH_PAGE_OFFSET = 1  # add to FinanceBench evidence_page_num to get chunks.page
KS = (1, 3, 5, 10, 20)
SCOPES = ("corpus", "parsed", "oracle")
SCOPE_DESCRIPTIONS = {
    "corpus": "No filter. Uses only the question text; available at question time.",
    "parsed": "Company and year read from the question text; available at question time.",
    "oracle": "FinanceBench company and evidence-document year. Uses labels; NOT available "
    "at question time. Upper bound only; not a basis for design decisions.",
}

Page = tuple[str, int]


def evidence_pages(question: dict[str, Any]) -> frozenset[Page]:
    """Return the (filing_id, 1-based page) pairs that hold the question's evidence.

    Raises ValueError if the question has no evidence.
    """
    pages = frozenset(
        (e["doc_name"], int(e["evidence_page_num"]) + FINANCEBENCH_PAGE_OFFSET)
        for e in question.get("evidence", [])
    )
    if not pages:
        raise ValueError(f"{question.get('financebench_id')}: no evidence pages")
    return pages


def first_hit_rank(retrieved: Sequence[Page], evidence: Iterable[Page]) -> int | None:
    """Return the 1-based rank of the first retrieved page in evidence, or None."""
    wanted = set(evidence)
    return next((rank for rank, page in enumerate(retrieved, start=1) if page in wanted), None)


def first_document_rank(retrieved: Sequence[str], documents: Iterable[str]) -> int | None:
    """Return the 1-based rank of the first chunk from an evidence document, or None."""
    wanted = set(documents)
    return next((rank for rank, doc in enumerate(retrieved, start=1) if doc in wanted), None)


def summarize(ranks: Sequence[int | None], ks: Sequence[int] = KS) -> dict[str, float]:
    """Return recall@k for each k and MRR over the ranks (None counts as a miss).

    Recall@k is the share of questions with a hit at rank k or better. MRR is the mean
    of 1/rank, with 0 for a miss. Raises ValueError for an empty sequence.
    """
    if not ranks:
        raise ValueError("No ranks to summarize")
    n = len(ranks)
    summary = {f"recall@{k}": sum(1 for r in ranks if r is not None and r <= k) / n for k in ks}
    summary["mrr"] = sum(1 / r for r in ranks if r is not None) / n
    return {key: round(value, 4) for key, value in summary.items()}


def summarize_by(
    records: Sequence[dict[str, Any]], group: str, rank_field: str = "page_rank"
) -> dict[str, dict[str, Any]]:
    """Summarize records overall ("all") and per value of the group field, sorted by name."""
    groups: dict[str, list[int | None]] = defaultdict(list)
    for record in records:
        groups["all"].append(record[rank_field])
        groups[str(record[group])].append(record[rank_field])
    return {
        name: {"n": len(ranks), **summarize(ranks)}
        for name, ranks in sorted(groups.items(), key=lambda item: (item[0] != "all", item[0]))
    }


def scope_filters(
    question: dict[str, Any], scope: str, fiscal_years: dict[str, int]
) -> tuple[str | None, int | None]:
    """Return the (company, fiscal_year) search filters for a scope.

    "corpus": no filter. "parsed": company and year read from the question text only, as
    available at query time. "oracle": the FinanceBench company and the fiscal year of the
    evidence document; this leaks labels and is an upper bound, not a realistic result.
    Raises ValueError for an unknown scope and KeyError for a document without a year.
    """
    if scope == "corpus":
        return None, None
    if scope == "parsed":
        return parse_filters(question["question"])
    if scope == "oracle":
        return question["company"], fiscal_years[question["doc_name"]]
    raise ValueError(f"Unknown scope {scope!r}; expected one of {', '.join(SCOPES)}")
