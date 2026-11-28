# ADR 0009: Agent retrieval uses vector search; evaluation scopes without label leakage

Date: 2026-11-28. Status: accepted.

## Context
`search_filings` fused vector search with keyword search built on
`websearch_to_tsquery`, which requires every query word in a chunk. FinanceBench
questions average 23 words, and only 3 of the 39 subset questions matched any chunk,
so the hybrid search was in effect vector search.

`scripts/evaluate_retrieval.py` measured five modes on the 39 questions
(`results/retrieval/2026-11-28.json`). A hit is a retrieved chunk on an evidence page
(FinanceBench page + 1). Three scopes set the search filters:

| Scope | Filters | Available when a user asks? |
|---|---|---|
| `corpus` | none | yes |
| `parsed` | company and year read from the question text (`finrag.query_filters`) | yes |
| `oracle` | FinanceBench company label and the evidence document's fiscal year | no: uses labels |

The parser found the right company for 38 questions (one question names no company) and
the right year for 30 (nine name no year or several years); it set no wrong filter. Its
alias list includes "AMEX" and "JPM", added after reading the questions.

| Scope | Mode | R@1 | R@5 | R@20 | MRR |
|---|---|---|---|---|---|
| parsed | keyword_and | 0.000 | 0.000 | 0.000 | 0.000 |
| parsed | keyword_or | 0.128 | 0.179 | 0.359 | 0.166 |
| parsed | vector | 0.154 | 0.385 | 0.590 | 0.276 |
| parsed | hybrid_and | 0.128 | 0.385 | 0.590 | 0.263 |
| parsed | hybrid_or | 0.256 | 0.333 | 0.513 | 0.299 |
| corpus | vector | 0.103 | 0.282 | 0.513 | 0.189 |
| corpus | hybrid_or | 0.128 | 0.231 | 0.385 | 0.179 |
| oracle (upper bound) | vector | 0.154 | 0.436 | 0.641 | 0.299 |
| oracle (upper bound) | hybrid_or | 0.256 | 0.410 | 0.590 | 0.327 |

Paired by question (parsed): within the top 5, vector alone hits 4 questions and
hybrid_or alone 2; within the top 20, 5 and 2; at rank 1, 2 and 6. With 39 questions none
of these differences is statistically significant.

An earlier draft of this ADR chose `hybrid_or` from the oracle scope. That scope uses
labels a user does not provide, so it cannot support a decision (see "Evaluation
integrity" in `CLAUDE.md`); on the leakage-free scopes the ranking on R@5 reverses.

## Decision
- The agent's `search_filings` uses `vector`.
- The tool description asks the model to pass `company` and `fiscal_year` when the
  question states them. Without labels, these filters raised vector R@5 from 0.282
  (corpus) to 0.385 (parsed).
- All five modes stay in `finrag.retrieval` for evaluation.

The agent sees the top 5 chunks, so R@5 is the primary metric; vector is better on it in
both leakage-free scopes, and also on R@20, the candidate pool for a reranker (step 8).
hybrid_or is better on R@1 and, in the parsed scope, on MRR.

## Alternatives considered
- `hybrid_or`: more precise first result, lower R@5 and R@20. Instructions inside
  questions ("Give a response to the question by relying on ...") add noise to its
  any-word keyword part; compare again after query cleanup (step 8).
- Keep `hybrid_and`: equal to vector search with a worse first rank.

## Consequences
- The choice rests on a small sample; repeat the comparison with 150 questions (step 7).
- In 92% to 95% of questions the right document is in the top 5 (leakage-free scopes),
  but the right page in only 28% to 39%: finding the page inside a long filing is the main
  weakness. Step 8 tests query cleanup and a reranker over the top 20.
- Step 6 measures which filters the agent itself passes, instead of the parser's.
- Vector search currently scans all rows (exact). A larger corpus may make the planner use
  the HNSW index, which can return fewer rows under filters; check again in step 7.
- The embedding model is the quantized ONNX build of BAAI/bge-small-en-v1.5 that fastembed
  ships; queries are embedded without an instruction prefix.
