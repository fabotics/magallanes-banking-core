"""Insurance: eligibility and the consent record.

Two rules live here, in code. The bank decides what may be offered, not the
agent. Every offer and the customer's answer are stored.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app import audit
from app.clock import utc_now
from app.db import Repository, Row, get_repository
from app.errors import ApiError
from app.schemas_insurance import (
    EligibilityResponse,
    OfferedProduct,
    OfferRequest,
    OfferResponse,
)
from app.security import require_session, session_from_request

# The insurance catalog is priced and approved for the pilot market only.
PILOT_COUNTRY = "CL"

router = APIRouter(tags=["insurance"])


def eligible_products(repository: Repository, customer: Row) -> tuple[list[Row], str | None]:
    """Return the products the customer may be offered, or the reason there are none.

    The catalog exists in the pilot country only. Vulnerable customers are
    never offered a product here: they go to a human advisor. Otherwise a
    product qualifies when it is active, open to the customer's segment, and
    not already held.
    """
    if customer["country"] != PILOT_COUNTRY:
        return [], "not_available_in_country"
    if customer["is_vulnerable"]:
        return [], "vulnerable_customer"
    policies = repository.select("policies", {"customer_id": customer["id"], "status": "active"})
    held = {policy["product_code"] for policy in policies}
    catalog = repository.select("insurance_products", {"active": True})
    for_segment = [p for p in catalog if customer["segment"] in p["eligible_segments"]]
    available = [p for p in for_segment if p["code"] not in held]
    if available:
        return available, None
    return [], "already_insured" if for_segment else "segment_not_eligible"


def session_customer(repository: Repository, session: Row) -> Row:
    """Return the customer row behind a session."""
    return repository.select("customers", {"id": session["customer_id"]})[0]


@router.get("/insurance/eligibility", response_model=EligibilityResponse)
def check_eligibility(
    request: Request,
    session: Annotated[Row, Depends(session_from_request)],
    repository: Annotated[Repository, Depends(get_repository)],
) -> EligibilityResponse:
    """Say which insurance products the bank pre-approves for this customer."""
    products, reason = eligible_products(repository, session_customer(repository, session))
    audit.note(request, outcome="eligible" if products else reason)
    return EligibilityResponse(
        eligible=bool(products),
        products=[OfferedProduct(**product) for product in products],
        reason_if_not=reason,
    )


@router.post("/insurance/offers", response_model=OfferResponse)
def log_offer(
    body: OfferRequest,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    x_session_token: Annotated[str | None, Header()] = None,
) -> OfferResponse:
    """Store one offer and the customer's answer. This row is the consent record."""
    session = require_session(request, repository, x_session_token or body.session_token)
    products, _ = eligible_products(repository, session_customer(repository, session))
    if body.product_code not in {product["code"] for product in products}:
        raise ApiError(409, "not_eligible", "The bank has not approved this product for them.")
    offer = repository.insert(
        "insurance_offers",
        {
            "customer_id": session["customer_id"],
            "product_code": body.product_code,
            "conversation_id": body.conversation_id or session["conversation_id"],
            "customer_response": body.customer_response,
            "created_at": utc_now().isoformat(),
        },
    )
    audit.note(request, outcome=f"offer_{body.customer_response}", product=body.product_code)
    return OfferResponse(offer_id=offer["id"], logged_at=offer["created_at"])
