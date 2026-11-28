# ADR 0007: PDF text with pypdfium2, page-bounded chunks, idempotent loading

Date: 2026-11-27. Status: accepted.

## Context
Step 3 loads the 17 FinanceBench PDFs (3,305 pages). FinanceBench marks evidence by page,
so retrieval is evaluated by page, and answers must cite pages. The embedding model
(BAAI/bge-small-en-v1.5) reads at most 512 tokens; longer text is cut off silently.

A test on the 17 PDFs checked, for each of the 44 evidence passages of the 39 questions,
whether the passage's words appear on the labeled page:

| Parser | License | Time, all pages | Best-matching page is the labeled page |
|---|---|---|---|
| pypdfium2 5.15 | BSD-3 / Apache-2.0 | 4.8 s | 44 of 44 |
| PyMuPDF 2.2 | AGPL-3.0 or commercial | 3.7 s | 44 of 44 |
| pypdf 7.2 | BSD-3 | 63 s | 43 of 44 |
| markitdown 0.1.9 | MIT | about 3.5 min (estimate) | not measurable: output has no page boundaries |

The test also showed that FinanceBench page numbers are 0-based, and that only 4 of
3,305 pages have no text layer, so no OCR is needed.

## Decision
- **Parser:** pypdfium2. It keeps each table row on one line, for example
  "Purchases of property, plant and equipment (PP&E) (1,577) (1,373) (1,420)".
- **Chunks:** a chunk never spans two pages. Pages are split between lines, so a table row
  stays whole. A chunk holds at most 350 tokens including its context line; consecutive
  chunks of a page share up to 50 tokens of lines. A single line longer than the budget is
  split between words. Token counts come from the model's own tokenizer.
- **Context line:** every chunk is stored with a line such as
  `3M | 10-K | FY2018 | page 60` in `chunks.context`. The embedding input is the context
  line followed by the chunk text; the keyword index includes the context too.
- **Pages:** stored 1-based (`chunks.page`). Evaluation adds 1 to FinanceBench page labels.
- **Loading:** `filings` records `source_sha256` and `pipeline_version` (parser version,
  chunk sizes, embedding model). A filing is reloaded only when one of them changes, and
  each filing is replaced in one transaction. The default target is `development`;
  `--target production` reads `PRODUCTION_DATABASE_URL` (ADR 0005).

## Alternatives considered
- PyMuPDF: as fast and accurate, but AGPL-3.0; this repository is public, and pypdfium2
  gives the same results under permissive licenses.
- markitdown: joins all pages into one text without page markers, so page citations and
  page-based evaluation are impossible; its table output is not better than pypdfium2.
- pypdf: about 13 times slower, and one evidence page fewer.
- pdfplumber: about 0.1 s per page; useful for table heuristics, not needed for text.
- Docling (MIT; layout and table-structure models): best table structure, but needs model
  downloads and takes seconds per table on a CPU. It will be compared in step 8 on pages
  with tables, using the evaluation from step 4.

## Consequences
- Table headers (for example the year columns) are separate lines; they stay in the same
  chunk as the rows only when they fit in the same 350-token window.
- A dry run with the token estimate gave 11,662 chunks; the real tokenizer gives fewer.
  Storage stays far below the 1 GB Neon limit.
- Changing the parser, the chunk sizes or the model changes `pipeline_version`, and the
  next run reloads every filing.
