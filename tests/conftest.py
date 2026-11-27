"""Shared test fixtures.

Database tests insert SYNTHETIC rows only (company "SampleCo", fiscal year 2099)
and delete them afterwards. They run only against TEST_DATABASE_URL (the Neon
'test' branch or the CI container) and are skipped when it is not set.
"""

import os

import pytest

from tests._db_guard import (
    REAL_FILINGS_QUERY,
    SYNTHETIC_PREFIX,
    real_data_problem,
    same_database,
)

# Tests must not download models or call the network.
os.environ.setdefault("EMBED_BACKEND", "hash")

FILING_ID = "TEST-SAMPLE-0001"
AUDIT_TAG = "pytest"


@pytest.fixture(scope="session")
def sample_db():
    """Apply the schema and load synthetic sample data for one test session.

    Runs only against TEST_DATABASE_URL, never against DATABASE_URL (ADR 0005).
    """
    import finrag.config  # noqa: F401  (loads .env, so DATABASE_URL is known)

    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("TEST_DATABASE_URL is not set")
    other_urls = [os.environ.get("DATABASE_URL"), os.environ.get("DATABASE_URL_UNPOOLED")]
    if same_database(test_url, other_urls):
        pytest.fail("TEST_DATABASE_URL points to the same database as DATABASE_URL")

    from finrag.db import apply_schema, connect
    from finrag.sample_data import delete_sample_data, insert_sample_data

    patch = pytest.MonkeyPatch()
    patch.setenv("DATABASE_URL", test_url)  # finrag.db connects through DATABASE_URL
    try:
        yield from _load_sample_data(apply_schema, connect, insert_sample_data, delete_sample_data)
    finally:
        patch.undo()


def _load_sample_data(apply_schema, connect, insert_sample_data, delete_sample_data):
    apply_schema()
    with connect() as conn:
        real = conn.execute(REAL_FILINGS_QUERY, (SYNTHETIC_PREFIX + "%",)).fetchone()["n"]
        problem = real_data_problem(real)
        if problem:
            pytest.fail(problem)
        delete_sample_data(conn, FILING_ID, AUDIT_TAG)  # leftovers from an interrupted run
        insert_sample_data(conn, FILING_ID)
        try:
            yield conn
        finally:
            delete_sample_data(conn, FILING_ID, AUDIT_TAG)
