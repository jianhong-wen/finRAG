# ADR 0004: Manage the Neon project with the Neon CLI and neon.ts

Date: 2026-11-27. Status: accepted.

## Context
ADR 0001 chose PostgreSQL on Neon. The connection string was to be copied by hand from the
Neon dashboard into `.env`. Manual copying is easy to get wrong, and the project settings
were not recorded in the repository.

## Decision
Use the Neon CLI (npm package `neon`, from `neondatabase/neon-pkgs`) to link the repository to
the Neon project and to write the environment variables:
`neon init` creates `neon.ts` (the branch policy) and `package.json` (its dependencies);
`neon deploy` applies the policy and writes `DATABASE_URL` and `DATABASE_URL_UNPOOLED` to `.env`.
The Python code is unchanged: it still reads `DATABASE_URL` and connects with psycopg.
The Neon serverless driver is not used, because it is meant for JavaScript runtimes.

## Alternatives considered
- Copy the connection string by hand: no extra tools, but error-prone and not recorded.
- Neon's older CLI (`neonctl`) only: no `neon.ts` policy file.

## Consequences
- `neon.ts`, `package.json` and `package-lock.json` are committed.
  `.env`, `.env.local`, `.neon` and `node_modules/` are ignored.
- Node.js is needed to set up the project, in addition to Python.
- `neon deploy` writes to `.env` only if the file exists; otherwise it writes `.env.local`,
  which `config.py` does not read. The README tells the user to create `.env` first.
- The first verification ran the database tests against the `production` branch. They use
  synthetic rows and delete them, but tests should move to a separate Neon branch.
  This will be decided in a later ADR or decision-log entry.
