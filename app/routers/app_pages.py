"""The bank's app, part two: home and identity confirmations.

Every page needs the session opened with the PIN. A visitor without one is
sent to the PIN screen and comes back to the same page afterwards.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app import app_session, audit, confirmations, contracts, i18n, signature
from app.clock import bank_date, parse_time, utc_now
from app.db import Repository, Row, get_repository
from app.formatting import card_label, long_date, money

router = APIRouter(tags=["app"], include_in_schema=False)
CONFIRMATION_ENDPOINT = "/app/confirmations/{request_id}"
GONE = ("gone_title", "request_gone")
# Result of a request: title and text (keys of the text tables) and the tone of the message.
ANSWERS = {
    "approved": ("approved_title", "approved_text", "ok"),
    "denied": ("denied_title", "denied_text", "error"),
    "expired": ("expired_title", "expired_text", "muted"),
}


def named(repository: Repository, rows: list[Row], language: str) -> list[Row]:
    """Add the product name and the formatted premium to proposal or policy rows."""
    catalog = {row["code"]: row for row in repository.select("insurance_products")}
    for row in rows:
        product = catalog[row["product_code"]]
        row["product_name"] = contracts.product_wording(product, language)[0]
        row["premium"] = money(product["monthly_premium"], product["currency"], language)
    return rows


@router.get("/app/home", response_class=HTMLResponse)
def home(request: Request, repository: Annotated[Repository, Depends(get_repository)]) -> Response:
    """Show who is signed in, their card, and what is waiting for them."""
    customer = app_session.current_customer(request, repository)
    if customer is None:
        return app_session.to_login(request)
    now = utc_now()
    language = i18n.pick_language(request)
    owned = {"customer_id": customer["id"]}
    waiting = repository.select(confirmations.TABLE, {**owned, "status": "pending"})
    proposals = repository.select("proposals", {**owned, "status": "sent"})
    policies = repository.select("policies", {**owned, "status": "active"})
    for policy in policies:
        policy["start"] = long_date(bank_date(parse_time(policy["started_at"])), language)
    cards = repository.select("cards", owned)
    label = card_label(cards[0], language) if cards else ""
    context = {
        "signed_in": True,
        "customer": customer,
        "card": {**cards[0], "label": label[:1].upper() + label[1:]} if cards else None,
        "confirmations": [c for c in waiting if confirmations.current_status(c, now) == "pending"],
        "proposals": named(
            repository,
            [
                p
                for p in proposals
                if p["signing_token"] and signature.proposal_status(p, now) == "pending"
            ],
            language,
        ),
        "policies": named(repository, policies, language),
    }
    return app_session.page(request, "home", context)


def find_confirmation(repository: Repository, customer: Row, request_id: uuid.UUID) -> Row | None:
    """Return the customer's own confirmation request, if it exists."""
    filters = {"id": str(request_id), "customer_id": customer["id"]}
    found = repository.select(confirmations.TABLE, filters)
    return found[0] if found else None


@router.get(CONFIRMATION_ENDPOINT, response_class=HTMLResponse)
def show_confirmation(
    request_id: uuid.UUID,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
) -> Response:
    """Show the code with the two answers, or what became of the request."""
    customer = app_session.current_customer(request, repository)
    if customer is None:
        return app_session.to_login(request)
    confirmation = find_confirmation(repository, customer, request_id)
    if confirmation is None:
        return app_session.message(request, *GONE)
    status = confirmations.current_status(confirmation, utc_now())
    if status != "pending":
        return app_session.message(request, *ANSWERS[status])
    return app_session.page(request, "confirm", {"signed_in": True, "confirmation": confirmation})


@router.post(CONFIRMATION_ENDPOINT, response_class=HTMLResponse)
def answer_confirmation(
    request_id: uuid.UUID,
    request: Request,
    fields: Annotated[dict[str, str], Depends(app_session.form_fields)],
    repository: Annotated[Repository, Depends(get_repository)],
) -> Response:
    """Record the customer's answer. Only the exact word `approve` approves."""
    customer = app_session.current_customer(request, repository)
    if customer is None:
        return app_session.to_login(request)
    confirmation = find_confirmation(repository, customer, request_id)
    if confirmation is None:
        return app_session.message(request, *GONE)
    now = utc_now()
    if confirmations.current_status(confirmation, now) == "pending":
        approved = fields.get("decision") == "approve"
        confirmation = confirmations.decide(repository, confirmation, approved, now)
        outcome = f"confirmation_{confirmation['status']}"
        audit.record(repository, CONFIRMATION_ENDPOINT, "POST", customer["id"], outcome)
    return app_session.message(request, *ANSWERS[confirmations.current_status(confirmation, now)])
