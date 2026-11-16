"""Quotes: the price and the limit the bank gives one customer for one product.

The catalog holds a base premium. The bank's rules turn it into a personal
quote from what the bank knows about the customer: the segment and the age.
The agent reads the quote and never computes or changes it. A quote is valid
for 15 days, and the proposal and the contract carry its number.
"""

import secrets
from datetime import date, datetime, timedelta

from app.clock import bank_date, parse_time
from app.db import Repository, Row

QUOTE_LIFETIME = timedelta(days=15)
# Rule 1: the segment changes the premium and sets the limit per event.
SEGMENT_FACTOR = {"mass": 1.0, "preferred": 0.9, "premium": 0.85}
COVERAGE_LIMIT = {"mass": 300_000, "preferred": 500_000, "premium": 1_000_000}
# Rule 2: from this age the premium carries a surcharge.
SENIOR_AGE = 65
SENIOR_FACTOR = 1.15
ROUND_TO = 10


def age_on(birth_date: str, today: date) -> int:
    """Return the age in whole years on `today`."""
    born = date.fromisoformat(birth_date)
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def premium_for(product: Row, customer: Row, today: date) -> float:
    """Apply the bank's rules to the base premium and round to ten."""
    factor = SEGMENT_FACTOR[customer["segment"]]
    if age_on(customer["birth_date"], today) >= SENIOR_AGE:
        factor *= SENIOR_FACTOR
    return round(float(product["monthly_premium"]) * factor / ROUND_TO) * ROUND_TO


def current(repository: Repository, customer: Row, product: Row, now: datetime) -> Row:
    """Return the customer's valid quote for this product, creating it when there is none."""
    filters = {"customer_id": customer["id"], "product_code": product["code"]}
    for quote in repository.select("quotes", filters):
        if parse_time(quote["valid_until"]) > now:
            return quote
    return repository.insert(
        "quotes",
        {
            **filters,
            "quote_number": f"CT-{now.year}-{secrets.token_hex(3).upper()}",
            "monthly_premium": premium_for(product, customer, bank_date(now)),
            "currency": product["currency"],
            "coverage_limit": COVERAGE_LIMIT[customer["segment"]],
            "created_at": now.isoformat(),
            "valid_until": (now + QUOTE_LIFETIME).isoformat(),
        },
    )


def priced(repository: Repository, product: Row, quote_number: str | None) -> Row:
    """Return the product with the premium and limit of a quote in place of the catalog's.

    A proposal made from a quote must show the quoted price everywhere. A
    product without a quote (a policy that predates quotes) keeps the catalog
    price and has no limit to show.
    """
    found = repository.select("quotes", {"quote_number": quote_number}) if quote_number else []
    if not found:
        return {**product, "quote_number": None, "coverage_limit": None}
    quote = found[0]
    return {
        **product,
        "monthly_premium": quote["monthly_premium"],
        "quote_number": quote["quote_number"],
        "coverage_limit": quote["coverage_limit"],
    }


def for_proposal(repository: Repository, proposal: Row) -> Row:
    """Return the product of a proposal, priced with the proposal's quote."""
    product = repository.select("insurance_products", {"code": proposal["product_code"]})[0]
    return priced(repository, product, proposal.get("quote_number"))
