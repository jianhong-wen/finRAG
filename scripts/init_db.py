"""Create the tables and indexes (safe to run more than once).

Usage:  python scripts/init_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finrag.config import database_url, describe_database  # noqa: E402
from finrag.db import apply_schema  # noqa: E402

if __name__ == "__main__":
    print(f"Target: {describe_database(database_url())}")
    tables = apply_schema()
    print("Schema applied. Tables:", ", ".join(tables))
