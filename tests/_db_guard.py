"""Guards that keep the database tests away from development and production data.

The database tests insert and delete rows. They must run only against a database
that holds synthetic data (see ADR 0005).
"""

from urllib.parse import urlsplit

SYNTHETIC_PREFIX = "TEST-"
REAL_FILINGS_QUERY = "select count(*) as n from filings where filing_id not like %s"


def database_identity(url: str) -> tuple[str, str]:
    """Return (host, database name) for a PostgreSQL URL.

    Neon's pooled and direct hosts differ only by "-pooler" in the first label,
    so both forms of the same branch give the same identity.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    first, _, rest = host.partition(".")
    first = first.removesuffix("-pooler")
    host = f"{first}.{rest}" if rest else first
    return host, parts.path.lstrip("/")


def same_database(test_url: str, other_urls: list[str | None]) -> bool:
    """True if test_url points to the same database as any of other_urls."""
    target = database_identity(test_url)
    return any(url and database_identity(url) == target for url in other_urls)


def real_data_problem(real_filings: int) -> str | None:
    """Return an error message if the test database holds non-synthetic filings."""
    if real_filings > 0:
        return (
            f"The test database holds {real_filings} filing(s) whose id does not start with "
            f"'{SYNTHETIC_PREFIX}'. Point TEST_DATABASE_URL at the Neon 'test' branch."
        )
    return None
