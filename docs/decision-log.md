# Decision log

One line per decision that is worth recording but too small for an ADR
(for example, a parameter value, a retry limit, or a file format).
Significant decisions need an ADR instead; see [`docs/adr/README.md`](adr/README.md).
Add new entries at the bottom. Do not edit old entries; add a new entry that replaces them.

| Date | Decision | Reason | Commit or PR |
|------|----------|--------|--------------|
| 2026-11-27 | `init_db.py` and `check_setup.py` print their target as a Neon endpoint id (`describe_database`), never the URL | A `DATABASE_URL` exported in the shell overrode `.env`, and `check_setup.py` ran on production without any sign of it | feat/neon-environments |
| 2026-11-27 | Minimum Python is 3.12 | The pinned numpy 2.5.5 needs 3.12 and pre-commit 4.7.0 needs 3.11; the Mac and CI already use 3.12 | chore/code-standards |
| 2026-11-27 | Pin direct dependencies to exact versions (`==`), taken from the tested Mac environment | Results must be reproducible; transitive dependencies are not locked yet | chore/code-standards |
| 2026-11-27 | `mypy --strict`, ruff C90 (max complexity 10) and D101-D103 (docstrings); `exploration/` is exempt from docstrings | Enforce the code standards by tools instead of review | chore/code-standards |
| 2026-11-27 | Synthetic sample data lives in `finrag.sample_data` and uses the invented alias tag `SampleCoTotalRevenue` | Cleanup deleted the alias of the real XBRL tag `Revenues` | chore/code-standards |
