# ADR 0006: FinanceBench subset from the GitHub repository at a pinned commit

Date: 2026-11-27. Status: accepted.

## Context
The evaluation uses the FinanceBench open sample: 150 questions about 84 filings of
32 US companies. Each document has an original link (`doc_link`) on a company or CDN site,
and some of these links are reported to be dead. The GitHub repository
`patronus-ai/financebench` also holds a copy of every PDF: all 84 documents that the
150 questions cite are in its `pdfs/` folder.

The Hugging Face dataset card states the license CC-BY-NC-4.0 (non-commercial use).
The GitHub repository has no license file.

## Decision
- Download the questions, the document metadata and the PDFs from the GitHub repository at
  commit `cc39aeb4afdf33909ee1412188bf89035950c2eb`, not from the original links.
- Start with five companies: American Express, JPMorgan, PepsiCo, 3M and Best Buy
  (39 questions, 17 documents). Two are financial companies (a card issuer and a bank),
  whose filings have finance-specific structure; the others give a range of sectors and
  question types.
- Commit only `manifests/financebench_subset.json`: question ids and types, document
  metadata, the original link, the pinned URL, the SHA-256 and the size of every file, and
  the UTC date of retrieval. Question text and PDFs stay in `data/`, which is not committed.
- `scripts/financebench.py fetch` downloads every file in the manifest and refuses a file
  whose SHA-256 differs.

## Alternatives considered
- Original `doc_link` URLs: closer to the primary source, but some are dead, and the hosts
  can change the files.
- Hugging Face dataset: same questions, but no PDFs, and not reachable from every
  environment used in this project.
- All 150 questions now: more data, but parsing and evaluation should first work on a
  smaller set.

## Consequences
- The corpus is reproducible: the same commit and hashes give the same files.
- The question mix is 7 metrics-generated, 16 domain-relevant and 16 novel-generated
  questions. In the open sample every question cites one document; there are no
  multi-document questions.
- Use is non-commercial (a portfolio project), and the README credits the source and the
  paper. Results on 39 questions vary a lot; reports must state the sample size.
- More companies can be added later by running `manifest` with a longer company list.
