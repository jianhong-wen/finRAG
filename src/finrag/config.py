"""Settings read from environment variables (and from a local .env file)."""

import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()

EMBED_DIM = 384  # must match vector(384) in sql/schema.sql
EMBED_BACKEND = os.environ.get("EMBED_BACKEND", "fastembed")  # "hash" is for offline tests only
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MAX_TOOL_ROUNDS = 8


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and add your connection string."
        )
    return url


def describe_database(url: str) -> str:
    """Name the database a URL points to, without the user name or password.

    For Neon this is the endpoint id, which identifies the branch, for example
    "ep-dawn-pond-behjjail (pooled), database neondb".
    """
    parts = urlsplit(url)
    host = parts.hostname or "unknown host"
    first = host.split(".")[0]
    pooled = first.endswith("-pooler")
    endpoint = first.removesuffix("-pooler") if "neon.tech" in host else host
    database = parts.path.lstrip("/") or "default"
    return f"{endpoint}{' (pooled)' if pooled else ''}, database {database}"
