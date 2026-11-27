"""Tests for the guards that keep database tests off real data. No database needed."""

from tests._db_guard import database_identity, real_data_problem, same_database

DEV = "postgresql://u:p@ep-dev-123-pooler.c-9.us-east-2.aws.neon.tech/neondb?sslmode=require"
DEV_DIRECT = "postgresql://u:p@ep-dev-123.c-9.us-east-2.aws.neon.tech/neondb?sslmode=require"
TEST = "postgresql://u:p@ep-test-456-pooler.c-9.us-east-2.aws.neon.tech/neondb?sslmode=require"


def test_pooled_and_direct_urls_are_the_same_database():
    assert database_identity(DEV) == database_identity(DEV_DIRECT)


def test_test_url_equal_to_development_url_is_rejected():
    assert same_database(DEV, [DEV_DIRECT, None])


def test_separate_test_branch_is_accepted():
    assert not same_database(TEST, [DEV, DEV_DIRECT])


def test_missing_other_urls_are_ignored():
    assert not same_database(TEST, [None, ""])


def test_same_host_but_other_database_is_accepted():
    other_db = DEV.replace("/neondb", "/finrag_test")
    assert not same_database(other_db, [DEV])


def test_real_filings_are_reported():
    message = real_data_problem(3)
    assert message is not None
    assert "3 filing(s)" in message


def test_synthetic_only_database_is_accepted():
    assert real_data_problem(0) is None
