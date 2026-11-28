# ADR 0010: Structured facts from SEC XBRL company facts, current-period values only

Date: 2026-11-28. Status: accepted.

## Context
`get_fact` needs reported numbers for the five companies of the subset. The SEC
companyfacts API returns every XBRL value a company has filed, one JSON file per company.
Each 10-K also repeats the values of earlier years as comparatives, and every entry carries
the fiscal year of the filing (`fy`), not the year of the value. In the 3M 10-K for 2018
(accession 0001558370-19-000470), capital expenditure has three entries, all with `fy` 2018,
for 2016 (1,420 million), 2017 (1,373 million) and 2018 (1,577 million). Loading by `fy`
would return three values, two of them wrong. The `fy` field is also not always right:
Best Buy's 10-K for the year ended 2021-01-30 has `fy` 2020, the same as the year before.

## Decision
- Download one companyfacts file per company to `data/sec/` (not committed). Record the
  download date, SHA-256 and size in `manifests/sec_companyfacts.json`. Requests name the
  client with `SEC_USER_AGENT`, as the SEC asks. Each file must name the expected CIK and
  company before it is accepted.
- Use only 10-K entries (`form` 10-K, `fp` FY). Amendments (10-K/A) and 10-Q values are
  not loaded: quarterly reports mix three-month and year-to-date values.
- Keep only current-period values of each 10-K: duration values of 350 to 380 days that end
  on the filing's period end date, and instant values dated on that day. The period end is
  the latest end date among the filing's annual values.
- Derive the fiscal year from the period end date: the calendar year in which the fiscal
  year ends, or the previous year when it ends in the first seven days of January. The SEC
  `fy` is kept for comparison, and differences are printed during loading.
- Map us-gaap tags to 18 normalized concepts with a fixed priority list
  (`finrag.sec_facts.CONCEPTS`), stored in `concept_aliases`. If the chosen tag has two
  different values for the same period, the concept is skipped for that filing and reported.
- Store each 10-K as a `filings` row `SEC-<accession>` with its EDGAR index link. A filing
  is reloaded only when the snapshot hash or the pipeline version (selection version and a
  hash of the concept map) changes.
- Check the loaded values against five FinanceBench metric questions
  (`scripts/sec_facts.py check`). The answers are used only to score the loaded values, with
  a 1 percent tolerance because the answers are rounded. They are never written to the
  database.

Disclosure (evaluation integrity, see CLAUDE.md): the concept list and the five check
questions were chosen after reading the FinanceBench questions of the subset. Capital
expenditure, net PP&E, inventory, operating income and D&A appear in those questions. The
check therefore verifies the loader; it is not an unbiased estimate of coverage on new
questions.

## Alternatives considered
- Load every entry and filter at query time: `get_fact` would have to choose among
  comparatives, and the same value would be stored once per filing that repeats it.
- Group by the SEC `frame` field (for example CY2018): frames follow calendar periods, so
  they do not fit Best Buy, whose fiscal year ends in late January or early February.
- Use the SEC `fy` field as the fiscal year: shown above to be wrong for some filings.
- Parse the full XBRL instance of each filing: more complete (dimensions, custom tags) but
  much more work; the companyfacts API is enough for the line items of the subset.

## Consequences
- 84 10-K filings and 1,213 facts loaded into development (2026-11-28); all five checks pass.
- `get_fact` returns one value per company, concept and fiscal year, with the EDGAR link.
- Coverage depends on the tags each company uses. Known gaps: banks (American Express,
  JPMorgan) have no cost of revenue, gross profit or inventory; 3M has no `cash` value under
  `CashAndCashEquivalentsAtCarryingValue` from 2017; Best Buy reports no total liabilities.
  Such questions fall back to `search_filings`.
- Values that a company restated later are stored as first reported in the 10-K of that year.
- SEC data changes over time. `fetch` refuses a file that no longer matches the manifest;
  `fetch --refresh` takes a new snapshot, after which load and check must run again.
- Revisit the concept list when the evaluation grows beyond the subset (step 9), and decide
  then whether 10-Q values are needed.
