# Project rules for AI assistants

Finance RAG: document search (`search_filings`) and structured fact lookup (`get_fact`)
in one PostgreSQL + pgvector database. See README.md for setup.

## Layout
- `sql/schema.sql`: tables and indexes. It must stay safe to run more than once.
- `src/finrag/`: library code (config, db, embed, tools, agent).
- `scripts/`: command-line entry points.
- `tests/`: pytest tests. Database tests use synthetic data only (company "SampleCo", fiscal year 2099).
- `docs/adr/`: architecture decision records.
- `manifests/`: data manifests (ids, links, SHA-256). Downloaded files go to `data/`, never committed.

## Commands
- Install: `pip install -r requirements-dev.txt` (Python 3.12 or later)
- All checks: `make check` (= `make lint`, `make typecheck`, `make test`)
- Lint: `ruff check . && ruff format --check .`
- Type check: `mypy` (strict mode)
- Test: `pytest --cov` (database tests need TEST_DATABASE_URL; they are skipped without it)

## Environments (ADR 0005)
Three Neon branches in one project. CI uses its own PostgreSQL container.

| Branch | Variable | Used for |
|---|---|---|
| `production` (default) | none in `.env` | Loaded filings, evaluation, demo |
| `development` | `DATABASE_URL` | Daily work, scripts, the agent |
| `test` | `TEST_DATABASE_URL` | Database tests, synthetic data only |

- Do not point `DATABASE_URL` or `TEST_DATABASE_URL` at `production`.
- Write to `production` only when the user asks for it in the current conversation,
  and name the target explicitly in the command.
- Database tests use only `TEST_DATABASE_URL`. Do not remove or weaken the guards in
  `tests/_db_guard.py` and the `sample_db` fixture.
- Variables exported in the shell override `.env` (`load_dotenv` does not overwrite them).
  Before trusting a database result, check the `Target:` line that `init_db.py` and
  `check_setup.py` print.
- To name a database in output, use `describe_database()` (endpoint id only), never the URL.

## Definition of done
A change is done only when `make check` passes.
- Report the actual command output. Do not say that checks passed without running them.
- Do not delete, skip, or weaken a failing test to make it pass. If a test is wrong, say why.
- Every behavior change needs a new or updated test.
- If a check could not be run (for example no database), say so explicitly.
- Before finishing, state whether the change needs an ADR or a `docs/decision-log.md` entry
  (criteria in `docs/adr/README.md`), and write it in the same change if so.

## Evaluation integrity
- Every input that an evaluation gives to the system under test must be available when a
  user asks the question. Labels (answers, evidence pages, document names, company or
  fiscal-year metadata) may be used only to score results, never to build queries,
  filters or prompts. Using them otherwise leaks information and inflates results.
- Wherever an evaluation uses label information, state in the code, the result file and
  the report whether that information is available at question time. A run that uses
  labels on purpose (an upper bound) must be named as such, for example scope `oracle`,
  and must not be the basis of a design decision.
- Disclose any setting chosen while looking at the evaluation questions (for example an
  alias list or a threshold), because it makes results optimistic.

## Code standards
ruff (including complexity <= 10 and docstrings), `mypy --strict` and coverage are enforced
by `make check`. These rules are not checked by tools:
- One responsibility per module (about 400 lines at most) and per function (about 40 lines).
- Keep pure logic apart from database, file, network and model calls, so it can be tested.
- Fail loudly: validate inputs at module boundaries, raise specific errors, never swallow an
  exception. Missing data is reported as missing, never treated as success.
- Network and model calls (SEC EDGAR, Anthropic) have a timeout and a bounded number of retries.
- Evaluation output is deterministic: sorted results, fixed random seeds.
- Files under `data/` are written to a temporary file first, then moved into place.
- Pin new dependencies to an exact version in `requirements*.txt`.
- Code describes current behavior only. Dates, experiment ids and change history belong in
  commit messages, ADRs or `docs/decision-log.md`.
- Every bug fix includes a test that fails before the fix.

## Rules
- SQL uses parameters (`%s` or `%(name)s`). Never build SQL by string formatting with input values.
- The model never writes SQL. New queries become new tool functions with fixed SQL.
- Every number in an agent answer must come from a tool result. Keep this rule in the system prompt.
- Every tool call is written to `audit_log`. Do not remove this.
- If you change the embedding model, change `vector(384)` in `sql/schema.sql` and `EMBED_DIM`
  in `src/finrag/config.py` together, and add an ADR.
- Tests must not use the network or real API keys. Use `EMBED_BACKEND=hash` and fake model clients.
- Do not use real company data in tests.
- A significant design decision gets a short ADR in `docs/adr/`.

## Never
- Commit `.env`, connection strings, API keys, or downloaded filings (`data/`).
- Print connection strings or keys in logs or chat.
- Run destructive SQL (`drop`, `truncate`, unscoped `delete`) against a shared database without asking.
