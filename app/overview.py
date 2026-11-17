"""Everything a caller needs right after the customer is verified, in one answer.

A voice agent that verifies the customer and then asks for the profile and for
the card movements makes three calls in a row, and the customer waits through
each one. So the answer to a successful verification already carries the
profile and what the statement shows. What explains the charges (the day
they were really made) is a separate question, asked when the customer doubts.
"""

from datetime import timedelta

from app import statement
from app.clock import parse_time, utc_now
from app.db import Repository, Row
from app.schemas import (
    CardTransaction,
    ChargesExplained,
    CustomerProfile,
    HeldProduct,
    Overview,
    StatementCharge,
    StatementView,
    TransactionsResponse,
)

RECENT_DAYS = 30


def held_products(repository: Repository, customer_id: str) -> list[HeldProduct]:
    """List the customer's accounts, cards and active insurance policies."""
    products = []
    for account in repository.select("accounts", {"customer_id": customer_id}):
        name = f"{account['type']} account in {account['currency']}"
        products.append(HeldProduct(kind="account", name=name, status="active"))
    for card in repository.select("cards", {"customer_id": customer_id}):
        name = f"{card['brand']} {card['type']} card ending {card['last4']}"
        products.append(HeldProduct(kind="card", name=name, status=card["status"]))
    catalog = {row["code"]: row["name"] for row in repository.select("insurance_products")}
    for policy in repository.select("policies", {"customer_id": customer_id, "status": "active"}):
        name = catalog[policy["product_code"]]
        products.append(HeldProduct(kind="insurance", name=name, status="active"))
    return products


def profile(repository: Repository, customer: Row) -> CustomerProfile:
    """Return who the customer is and what they hold."""
    return CustomerProfile(
        first_name=customer["first_name"],
        segment=customer["segment"],
        country=customer["country"],
        preferred_language=customer["preferred_language"],
        is_vulnerable=customer["is_vulnerable"],
        products=held_products(repository, customer["id"]),
    )


def to_transaction(row: Row, card_last4: str) -> CardTransaction:
    """Shape a stored transaction for an answer. Foreign charges keep their original amount.

    Days and hours are given on the bank's clock, also in words.
    """
    fields = {
        "id": row["id"],
        "card_last4": card_last4,
        "amount": row["amount"],
        "currency": row["currency"],
        "descriptor": row["descriptor"],
        "merchant_tax_id": row["merchant_tax_id"],
        "channel": row["channel"],
        "country": row["country"],
        **statement.local_fields(row),
        "status": row["status"],
    }
    if row["original_currency"]:
        fields["original_amount"] = row["original_amount"]
        fields["original_currency"] = row["original_currency"]
    return CardTransaction(**fields)


def movements(
    repository: Repository, customer_id: str, days: int = RECENT_DAYS, status: str = "all"
) -> TransactionsResponse:
    """Return the customer's recent card movements, newest first, with repeats added up."""
    since = utc_now() - timedelta(days=days)
    transactions = []
    for card in repository.select("cards", {"customer_id": customer_id}):
        for row in repository.select("transactions", {"card_id": card["id"]}):
            is_recent = parse_time(row["transaction_at"]) >= since
            if is_recent and status in ("all", row["status"]):
                transactions.append(to_transaction(row, card["last4"]))
    transactions.sort(key=lambda item: parse_time(item.transaction_at), reverse=True)
    return TransactionsResponse(
        count=len(transactions),
        timezone=statement.TIMEZONE_NAME,
        repeated_charges=statement.repeated_charges([item.model_dump() for item in transactions]),
        transactions=transactions,
    )


WHY = (
    "Card purchases often post a day or two later, when the merchant sends them to the bank, "
    "so a purchase made on one day can show under a later one."
)


def statement_views(
    charges: TransactionsResponse,
) -> tuple[list[StatementView], list[ChargesExplained]]:
    """Split the repeated charges into what the statement shows and what explains it."""
    views, explained = [], []
    for group in charges.repeated_charges:
        same = [item for item in charges.transactions if item.descriptor == group.descriptor]
        same.sort(key=lambda item: parse_time(item.transaction_at))
        lines = [
            StatementCharge(time=statement.clock_12(item.purchased_time), amount=item.amount)
            for item in same
        ]
        posted = (group.posted_on or group.purchased_on)[-1].split()[0]
        views.append(
            StatementView(
                descriptor=group.descriptor,
                merchant_tax_id=group.merchant_tax_id,
                count=group.count,
                posted_weekday=posted,
                charges=lines,
                total=group.total,
                currency=group.currency,
            )  # fmt: skip
        )
        explained.append(
            ChargesExplained(
                descriptor=group.descriptor,
                merchant_tax_id=group.merchant_tax_id,
                purchased_on=group.purchased_on,
                first_time=statement.clock_12(group.first_time),
                last_time=statement.clock_12(group.last_time),
                posted_on=group.posted_on,
                why_the_dates_differ=WHY,
            )  # fmt: skip
        )
    return views, explained


def after_verification(repository: Repository, customer: Row) -> Overview:
    """Return the profile and the statement of a customer who was just verified.

    Only what the statement shows. When the purchases were really made is not
    here: see `explained`.
    """
    turn_1, _ = statement_views(movements(repository, customer["id"]))
    return Overview(customer=profile(repository, customer), turn_1=turn_1)


def explained(repository: Repository, customer_id: str) -> list[ChargesExplained]:
    """Return when the customer's repeated charges were really made and why the dates differ."""
    return statement_views(movements(repository, customer_id))[1]


def first_route(customer: Row) -> str:
    """Return where the conversation goes after verification: the review, or a person."""
    return "handoff" if customer["is_vulnerable"] else "review"
