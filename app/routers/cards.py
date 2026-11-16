"""Cards: recent transactions for the verified customer."""

import time
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from app import audit
from app.clock import parse_time, utc_now
from app.config import Settings, get_settings
from app.db import Repository, Row, get_repository
from app.schemas import CardTransaction, TransactionsResponse
from app.security import session_from_request

router = APIRouter(tags=["cards"])


def to_transaction(row: Row, card_last4: str) -> CardTransaction:
    """Shape a stored transaction for the response. Foreign charges keep their original amount."""
    fields = {
        "id": row["id"],
        "card_last4": card_last4,
        "amount": row["amount"],
        "currency": row["currency"],
        "descriptor": row["descriptor"],
        "merchant_tax_id": row["merchant_tax_id"],
        "channel": row["channel"],
        "country": row["country"],
        "transaction_at": row["transaction_at"],
        "posted_at": row["posted_at"],
        "status": row["status"],
    }
    if row["original_currency"]:
        fields["original_amount"] = row["original_amount"]
        fields["original_currency"] = row["original_currency"]
    return CardTransaction(**fields)


@router.get(
    "/cards/transactions",
    response_model=TransactionsResponse,
    response_model_exclude_unset=True,
)
def get_transactions(
    request: Request,
    session: Annotated[Row, Depends(session_from_request)],
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    days: Annotated[int, Query(ge=1, le=90, description="How many days back to look.")] = 30,
    status: Annotated[Literal["all", "pending", "posted"], Query()] = "all",
) -> TransactionsResponse:
    """Return the customer's recent card movements across all cards, newest first.

    The short wait imitates a call to a legacy middleware, so the caller has to
    cope with a slow tool. It is configurable and off in tests.
    """
    time.sleep(settings.transactions_delay_seconds)
    since = utc_now() - timedelta(days=days)
    transactions = []
    for card in repository.select("cards", {"customer_id": session["customer_id"]}):
        for row in repository.select("transactions", {"card_id": card["id"]}):
            is_recent = parse_time(row["transaction_at"]) >= since
            status_matches = status == "all" or row["status"] == status
            if is_recent and status_matches:
                transactions.append(to_transaction(row, card["last4"]))
    transactions.sort(key=lambda item: parse_time(item.transaction_at), reverse=True)
    audit.note(request, count=len(transactions))
    return TransactionsResponse(count=len(transactions), transactions=transactions)
