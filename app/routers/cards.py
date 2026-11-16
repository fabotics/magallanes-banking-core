"""Cards: recent transactions and the temporary block, for the verified customer.

The block is the only state change the API allows on a card, and it is
reversible. No endpoint moves money.
"""

import time
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request

from app import audit, statement
from app.clock import BANK_TIMEZONE, parse_time, utc_now
from app.config import Settings, get_settings
from app.db import Repository, Row, get_repository
from app.errors import ApiError
from app.schemas import (
    BlockCardRequest,
    BlockCardResponse,
    CardTransaction,
    TransactionsResponse,
)
from app.security import require_session, session_from_request

router = APIRouter(tags=["cards"])


def to_transaction(row: Row, card_last4: str) -> CardTransaction:
    """Shape a stored transaction for the response. Foreign charges keep their original amount.

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
    return TransactionsResponse(
        count=len(transactions),
        timezone=str(BANK_TIMEZONE),
        repeated_charges=statement.repeated_charges([item.model_dump() for item in transactions]),
        transactions=transactions,
    )


def block_reference(card: Row) -> str:
    """Build the reference the agent reads back, for example `BLK-20261116-4821`."""
    blocked_on = parse_time(card["blocked_at"]).strftime("%Y%m%d")
    return f"BLK-{blocked_on}-{card['last4']}"


@router.post("/cards/block", response_model=BlockCardResponse)
def block_card(
    body: BlockCardRequest,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    x_session_token: Annotated[str | None, Header()] = None,
) -> BlockCardResponse:
    """Block one of the customer's cards temporarily.

    Only an active card changes state. Asking again for a card that is already
    blocked returns its current state, so a repeated call is harmless.
    """
    session = require_session(request, repository, x_session_token or body.session_token)
    filters = {"customer_id": session["customer_id"], "last4": body.card_last4.strip()}
    cards = repository.select("cards", filters)
    if not cards:
        raise ApiError(404, "card_not_found", "The customer has no card ending in those digits.")
    card = cards[0]
    if card["status"] == "active":
        values = {
            "status": "blocked_temporary",
            "blocked_at": utc_now().isoformat(),
            "block_reason": body.reason,
        }
        card = repository.update("cards", {"id": card["id"]}, values)[0]
        audit.note(request, outcome="card_blocked")
    else:
        audit.note(request, outcome="already_blocked")
    audit.note(request, card_last4=card["last4"])

    how_to_unblock = "The block is temporary. The customer can lift it in the bank's app."
    if card["status"] == "blocked":
        how_to_unblock = "This card is blocked for good. The customer must request a new one."
    return BlockCardResponse(
        card_status=card["status"],
        reference=block_reference(card),
        how_to_unblock=how_to_unblock,
    )
