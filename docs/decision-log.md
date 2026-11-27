# Decision log

One line per decision that is worth recording but too small for an ADR
(for example, a parameter value, a retry limit, or a file format).
Significant decisions need an ADR instead; see [`docs/adr/README.md`](adr/README.md).
Add new entries at the bottom. Do not edit old entries; add a new entry that replaces them.

| Date | Decision | Reason | Commit or PR |
|------|----------|--------|--------------|
| 2026-11-27 | `init_db.py` and `check_setup.py` print their target as a Neon endpoint id (`describe_database`), never the URL | A `DATABASE_URL` exported in the shell overrode `.env`, and `check_setup.py` ran on production without any sign of it | feat/neon-environments |
