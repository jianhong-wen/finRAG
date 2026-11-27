# ADR 0005: Production, development and test as Neon branches

Date: 2026-11-27. Status: accepted.

## Context
Until now, daily work and the database tests both used the `production` branch. From step 3
on, production will hold the loaded filings that the evaluation results depend on.
The tests insert and delete rows. Their cleanup also deletes the concept alias for the real
XBRL tag `Revenues`, so a test run on production could change real data.

## Decision
Use three Neon branches in one project:
- `production` (default branch): the loaded corpus for evaluation and the demo. Only
  loading scripts write to it, and only when the target is named explicitly.
- `development` (child of production, no expiry): daily development and schema experiments.
  `DATABASE_URL` points here. It can be reset from production when needed.
- `test` (child of production, no expiry): local database tests with synthetic data only.
  CI keeps using its PostgreSQL container.

The database tests read only `TEST_DATABASE_URL` and are skipped when it is not set.
They fail before writing anything if that URL is the same database as `DATABASE_URL`
(pooled and direct hosts count as the same), or if the database holds a filing whose id
does not start with `TEST-`. `neon.ts` marks `development` and `test` as long-lived, so the
7-day expiry for other new branches does not apply to them.

## Alternatives considered
- One branch for everything: simplest, but tests and experiments can change evaluation data.
- Separate Neon projects per environment: stronger isolation, but no copy-on-write branching
  from production, and three sets of credentials.
- Local PostgreSQL in Docker for tests: no network needed, but a second setup to maintain.
  CI already covers this case with its container.

## Consequences
- Three of the ten branches allowed per project on the Neon free plan are used.
  The 1 GB storage limit is shared by all branches of the project.
- `.env` holds two connection strings: `DATABASE_URL` (development) and `TEST_DATABASE_URL`.
- Writing to production needs an explicit choice. The loading scripts in step 3 must take the
  target environment as an argument; this will be designed with them.
