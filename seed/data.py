"""The single source of seed data.

`build_seed` returns every row, keyed by table. The seed script writes these
rows to the database, and the tests load the same rows into an in-memory
repository, so both always see the same story.
"""

from datetime import date, datetime, timedelta

from seed.helpers import seed_id
from seed.movements import BANK_TIMEZONE, at, build_transactions
from seed.people import build_accounts, build_cards, build_customers
from seed.registry import build_registry

# Every table, parents before children. Insert in this order, delete in reverse.
TABLES = [
    "insurance_products",
    "customers",
    "accounts",
    "cards",
    "transactions",
    "policies",
    "insurance_offers",
    "proposals",
    "cases",
    "verification_sessions",
    "verification_attempts",
    "audit_log",
    "registry_merchants",
]

# Tables whose primary key is not a generated `id`.
PRIMARY_KEYS = {"insurance_products": "code", "registry_merchants": "tax_id"}

FRAUD_PRODUCT = "CARD_FRAUD"

PRODUCTS = [
    {
        "code": FRAUD_PRODUCT,
        "name": "Card fraud protection",
        "monthly_premium": 2990,
        "currency": "CLP",
        "coverage_summary": "Refunds unauthorized card charges and covers card replacement.",
        "eligible_segments": ["mass", "preferred", "premium"],
        "active": True,
    },
    {
        "code": "UNEMPLOYMENT",
        "name": "Unemployment protection",
        "monthly_premium": 5490,
        "currency": "CLP",
        "coverage_summary": "Pays the card's minimum payment for up to six months of job loss.",
        "eligible_segments": ["preferred", "premium"],
        "active": True,
    },
    {
        "code": "PURCHASE",
        "name": "Purchase protection",
        "monthly_premium": 3990,
        "currency": "CLP",
        "coverage_summary": "Covers theft or accidental damage of card purchases for 90 days.",
        "eligible_segments": ["premium"],
        "active": True,
    },
]


def build_seed(
    today: date | None = None, demo_email: str = "", demo_chat_id: str = ""
) -> dict[str, list[dict]]:
    """Build all seed rows relative to `today` (defaults to the current date at the bank).

    Tables that start empty (offers, cases, sessions, audit) are present with
    no rows, so a reset clears them too.
    """
    today = today or datetime.now(BANK_TIMEZONE).date()
    rows: dict[str, list[dict]] = {table: [] for table in TABLES}
    rows["insurance_products"] = [dict(product) for product in PRODUCTS]
    rows["customers"] = build_customers(demo_email, demo_chat_id)
    rows["accounts"] = build_accounts(now_iso=at(today, 0, 0))
    rows["cards"] = build_cards(blocked_at_iso=at(today - timedelta(days=3), 16, 20))
    rows["transactions"] = build_transactions(today)
    rows["registry_merchants"] = build_registry()
    rows["policies"] = [
        {
            "id": seed_id("policy/carolina/fraud"),
            "customer_id": seed_id("customer/carolina"),
            "product_code": FRAUD_PRODUCT,
            "status": "active",
            "started_at": at(today - timedelta(days=200), 12, 0),
        }
    ]
    return rows
