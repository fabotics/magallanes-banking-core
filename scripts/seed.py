"""Load the seed data into the database.

Usage:
    python scripts/seed.py            print the row count of every table
    python scripts/seed.py --reset    wipe every table, then load the seed rows
    python scripts/seed.py --pins     print the app PIN of every seed customer

A reset also clears verification attempts, sessions, pending confirmations
and proposals, and restores every app PIN, so a locked test customer is
unlocked again. Needs SUPABASE_URL and SUPABASE_SECRET_KEY in `.env`.
"""

import argparse
import sys
from pathlib import Path

# Make `app` and `seed` importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import Repository, build_repository  # noqa: E402
from seed.data import PRIMARY_KEYS, TABLES, build_seed  # noqa: E402
from seed.helpers import app_pin  # noqa: E402
from seed.people import PEOPLE  # noqa: E402


def reset(repository: Repository, demo_email: str, demo_chat_id: str, pin_secret: str = "") -> None:
    """Delete all rows, children first, then insert the seed rows, parents first."""
    for table in reversed(TABLES):
        repository.delete_all(table, PRIMARY_KEYS.get(table, "id"))
    seed = build_seed(demo_email=demo_email, demo_chat_id=demo_chat_id, pin_secret=pin_secret)
    for table, rows in seed.items():
        repository.insert_many(table, rows)


def print_counts(repository: Repository) -> None:
    """Print how many rows each table holds."""
    for table in TABLES:
        print(f"{table:24} {len(repository.select(table)):4}")


def print_pins(pin_secret: str) -> None:
    """Print the app PIN of every seed customer. They exist only if a secret is set."""
    if not pin_secret:
        sys.exit("APP_PIN_SECRET is not set, so no customer has an app PIN.")
    for person in PEOPLE:
        print(f"{person[3]:14} {app_pin(pin_secret, person[0])}")


def main() -> None:
    """Parse the arguments and run."""
    parser = argparse.ArgumentParser(description="Seed the banking core database.")
    parser.add_argument("--reset", action="store_true", help="wipe and reload all tables")
    parser.add_argument("--pins", action="store_true", help="print each customer's app PIN")
    args = parser.parse_args()

    settings = get_settings()
    if args.pins:
        return print_pins(settings.app_pin_secret)
    repository = build_repository(settings)
    if args.reset:
        reset(
            repository,
            settings.demo_customer_email,
            settings.demo_telegram_chat_id,
            settings.app_pin_secret,
        )
        print("Reset done.")
    print_counts(repository)


if __name__ == "__main__":
    main()
