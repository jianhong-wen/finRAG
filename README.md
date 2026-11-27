# Finance RAG: document search and structured facts in one PostgreSQL database

This project answers questions about company filings. It combines two kinds of retrieval:

- **Document search** over filing text: keyword search and vector search, merged with
  Reciprocal Rank Fusion (RRF, a method that combines two ranked lists).
- **Fact lookup** over structured numbers (for example revenue from XBRL data).

Both kinds of data live in one PostgreSQL database, so a document chunk and a number can be
linked through the same `filing_id`. A model chooses which tool to call. Every tool call is
written to an audit table.

## Status

| Part | State |
|---|---|
| Schema (`sql/schema.sql`) | Tested on PostgreSQL 16 with pgvector 0.6.0 |
| Tools `get_fact` and `search_filings` | Tested with synthetic data (`scripts/check_setup.py`) |
| Agent loop with audit logging | Tested with a mocked model response |
| Embedding model (fastembed) | Tested on macOS with Python 3.12 (2026-11-27) |
| Neon database | Tested: `check_setup.py` 9 of 9 checks, `pytest` 25 passed (2026-11-27) |
| Neon environments | Tested: `check_setup.py` 9 of 9 on `development`, `pytest` 32 passed with database tests on `test` (2026-11-27) |
| Ingestion of real filings | Not built yet |

## Setup

Requirements: Python 3.12 or later (the pinned numpy needs it; CI uses 3.12). The Python that
ships with the macOS Command Line Tools is 3.9 and does not work. Node.js is needed only for the Neon CLI.

1. Link the Neon project and write its environment variables to `.env`
   (see [ADR 0004](docs/adr/0004-neon-cli-config.md)):

   ```
   npm i -g neon@latest        # or use npx neon@latest
   neon login
   touch .env                  # neon deploy writes to .env only if it exists
   neon init -y --org-id <org-id> --project-id <project-id> --branch production --services postgres
   neon deploy
   ```

   The free plan has 1 GB of storage per project, and compute stops after 5 minutes without use.
   Never commit `.env` or paste the connection string into a chat.
   Add `ANTHROPIC_API_KEY` to `.env` by hand if you want to run the agent.

   Then point `.env` at the development and test branches
   (see [ADR 0005](docs/adr/0005-neon-environments.md)):

   ```
   neon checkout development   # writes DATABASE_URL for the development branch
   printf 'TEST_DATABASE_URL="%s"\n' "$(neon cs test --pooled)" >> .env
   ```

   | Branch | Used by | Variable |
   |---|---|---|
   | `production` | Loading scripts and evaluation, only when named explicitly | none in `.env` |
   | `development` | Daily work, `check_setup.py`, the agent | `DATABASE_URL` |
   | `test` | Database tests (synthetic data only) | `TEST_DATABASE_URL` |
2. Install the dependencies:

   ```
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Create the tables and run the self-check:

   ```
   python scripts/init_db.py
   python scripts/check_setup.py
   ```

   The self-check inserts a few synthetic rows (company "SampleCo", fiscal year 2099),
   runs both tools, and removes the rows. The first run downloads the embedding model
   (BAAI/bge-small-en-v1.5, 384 dimensions), so it can take a few minutes.

To ask a question with the agent, set `ANTHROPIC_API_KEY` in `.env`, then run:

```
PYTHONPATH=src python -m finrag.agent "What was SampleCo revenue in 2099?"
```

## Development

```
pip install -r requirements-dev.txt
pre-commit install          # run format, lint and secret checks before each commit
make check                  # lint, format check, mypy --strict, tests with coverage
```

`make check` runs `make lint`, `make typecheck` and `make test`. Database tests run only on
`TEST_DATABASE_URL` (the Neon `test` branch) and are skipped when it is not set.

GitHub Actions (`.github/workflows/ci.yml`) runs the same checks on every push, with a
PostgreSQL + pgvector service container. Rules for AI assistants are in `CLAUDE.md`.
Design decisions are recorded in `docs/adr/`.

## Data model

| Table | Purpose |
|---|---|
| `filings` | One row per source document |
| `facts` | Structured numbers, with `source` (`xbrl` or `pdf_table`), page, and confidence |
| `concept_aliases` | Maps raw tags to one normalized concept name |
| `chunks` | Text chunks with a vector (`embedding`) and a keyword index (`tsv`) |
| `audit_log` | One row per tool call: input, output summary, and time taken |

## Design notes

- `get_fact` uses fixed, parameterized queries. The model never writes SQL.
- If a concept is not found, `get_fact` returns the concepts that exist, so the model can correct its request.
- The vector size is 384. If you change the embedding model, change `vector(384)` in
  `sql/schema.sql` and `EMBED_DIM` in `src/finrag/config.py` together.
- `EMBED_BACKEND=hash` is a word-hashing function for offline tests only.

## Next steps

1. Load real filings: PDF parsing, table extraction, and XBRL facts.
2. Add a cross-encoder reranker after the RRF step.
3. Evaluate on the FinanceBench open sample (150 questions): PDF only, facts only, and combined.
