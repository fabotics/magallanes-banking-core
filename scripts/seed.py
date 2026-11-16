"""Load the seed data into the database.

Usage:
    python scripts/seed.py            print the row count of every table
    python scripts/seed.py --reset    wipe every table, then load the seed rows

A reset also clears verification attempts and sessions, so a locked test
customer is unlocked again. Needs SUPABASE_URL and SUPABASE_SECRET_KEY in `.env`.
"""

import argparse
import sys
from pathlib import Path

# Make `app` and `seed` importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import Repository, get_repository  # noqa: E402
from seed.data import TABLES, build_seed  # noqa: E402


def key_column(table: str) -> str:
    """Return the primary key column of a table."""
    return "code" if table == "insurance_products" else "id"


def reset(repository: Repository, demo_email: str) -> None:
    """Delete all rows, children first, then insert the seed rows, parents first."""
    for table in reversed(TABLES):
        repository.delete_all(table, key_column(table))
    for table, rows in build_seed(demo_email=demo_email).items():
        repository.insert_many(table, rows)


def print_counts(repository: Repository) -> None:
    """Print how many rows each table holds."""
    for table in TABLES:
        print(f"{table:24} {len(repository.select(table)):4}")


def main() -> None:
    """Parse the arguments and run."""
    parser = argparse.ArgumentParser(description="Seed the banking core database.")
    parser.add_argument("--reset", action="store_true", help="wipe and reload all tables")
    args = parser.parse_args()

    settings = get_settings()
    repository = get_repository(settings)
    if args.reset:
        reset(repository, settings.demo_customer_email)
        print("Reset done.")
    print_counts(repository)


if __name__ == "__main__":
    main()
