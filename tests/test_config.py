"""Tests for settings helpers. No database or network needed."""

from finrag.config import describe_database

NEON = "postgresql://owner:s3cret@ep-dawn-pond-123-pooler.c-9.us-east-2.aws.neon.tech/neondb?sslmode=require"


def test_neon_url_is_named_by_endpoint_and_pool():
    assert describe_database(NEON) == "ep-dawn-pond-123 (pooled), database neondb"


def test_direct_neon_url_is_not_marked_pooled():
    direct = NEON.replace("-pooler", "")
    assert describe_database(direct) == "ep-dawn-pond-123, database neondb"


def test_user_name_and_password_are_not_shown():
    text = describe_database(NEON)
    assert "owner" not in text
    assert "s3cret" not in text
    assert "sslmode" not in text


def test_local_url_shows_host():
    url = "postgresql://finrag:pw@localhost:5432/finrag_test"
    assert describe_database(url) == "localhost, database finrag_test"
