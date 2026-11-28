# Architecture decision records

An ADR (architecture decision record: a short file that records one design decision)
explains what was decided, why, and which alternatives were rejected.
Small decisions go to [`docs/decision-log.md`](../decision-log.md) instead.

## When a decision needs an ADR
Write an ADR when a change:
- changes the database schema, the embedding model, or the vector dimension;
- adds a tool, or changes which tools the agent may call;
- changes how documents are chunked, retrieved, or ranked;
- changes a safety rule (audit logging, parameterized SQL, "every number comes from a tool");
- chooses or replaces a hosting service, a major library, or a data source;
- accepts a known limitation that affects results or cost.

If you are not sure, write a one-line entry in the decision log. Promote it to an ADR
later if it becomes important.

## Process
1. Copy [`0000-template.md`](0000-template.md) to `NNNN-short-title.md`, using the next number.
2. Write the ADR in the same pull request as the code that carries out the decision.
3. Add the ADR to the index below.
4. Reference it in commit messages and the pull request, for example `Refs: ADR-0004`.
5. Do not rewrite an accepted ADR. To change a decision, write a new ADR with the line
   "Supersedes ADR NNNN.", and set the old ADR's status to "superseded by ADR <new number>".

`tests/test_decision_records.py` checks the file names, statuses, sections, this index,
and that the vector dimension in the schema, the config, and an accepted ADR agree.

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-postgresql-pgvector.md) | One PostgreSQL database with pgvector | accepted | 2026-11-27 |
| [0002](0002-embedding-384.md) | 384-dimension embeddings (BAAI/bge-small-en-v1.5) | accepted | 2026-11-27 |
| [0003](0003-fixed-sql-tools.md) | Fixed, parameterized SQL tools instead of model-written SQL | accepted | 2026-11-27 |
| [0004](0004-neon-cli-config.md) | Manage the Neon project with the Neon CLI and neon.ts | accepted | 2026-11-27 |
| [0005](0005-neon-environments.md) | Production, development and test as Neon branches | accepted | 2026-11-27 |
| [0006](0006-financebench-subset.md) | FinanceBench subset from the GitHub repository at a pinned commit | accepted | 2026-11-27 |
| [0007](0007-pdf-parsing-and-chunking.md) | PDF text with pypdfium2, page-bounded chunks, idempotent loading | accepted | 2026-11-27 |
| [0008](0008-agent-runtime-and-llm-provider.md) | Own agent loop on the Anthropic SDK; AMD Radeon Cloud as the model provider | accepted | 2026-11-27 |
| [0009](0009-agent-retrieval-mode.md) | Agent retrieval uses vector search; evaluation scopes without label leakage | accepted | 2026-11-27 |
