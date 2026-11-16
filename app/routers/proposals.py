"""Proposals: what the customer receives after an offer, and whether they signed it.

A proposal exists only for an offer the customer accepted or asked details
about. It goes out at once: by email with the signing link, and to the
customer's chat with a link to the contract in the bank's app, so the customer
can sign while still on the call. Nothing is contracted until
they sign, and the agent can only read the result, never sign for them.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app import audit, quotes, signature, waiting
from app.app_session import app_link
from app.clock import bank_date, parse_time, utc_now
from app.config import Settings, get_settings
from app.db import Repository, Row, get_repository
from app.email import mask_email, proposal_email, send_email
from app.errors import ApiError
from app.formatting import money
from app.messaging import send_telegram
from app.schemas_insurance import ProposalRequest, ProposalResponse, ProposalStatusResponse
from app.security import require_session, session_from_request

router = APIRouter(tags=["insurance"])


def signing_link(settings: Settings, proposal: Row) -> str | None:
    """Return the address of the signing page, or None for a proposal that is only details."""
    if not proposal["signing_token"]:
        return None
    return f"{settings.public_base_url.rstrip('/')}/sign/{proposal['signing_token']}"


def send_to_messaging(settings: Settings, customer: Row, product: Row, proposal: Row) -> bool:
    """Send a link to the contract in the app, with the product and premium, to the chat."""
    if not proposal["signing_token"] or not customer["telegram_chat_id"]:
        return False
    link = app_link(settings, customer, f"/app/proposals/{proposal['proposal_number']}")
    text = (
        "Banco Magallanes\n"
        f"Su propuesta de {product['name']} está lista para firmar.\n"
        f"Prima mensual: {money(product['monthly_premium'], product['currency'])}\n\n"
        f"Revise y firme en la app: {link}\n"
        "Nada queda contratado hasta que usted firme."
    )
    return send_telegram(settings, customer["telegram_chat_id"], text)


@router.post(
    "/insurance/proposals", response_model=ProposalResponse, response_model_exclude_none=True
)
def create_proposal(
    body: ProposalRequest,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_session_token: Annotated[str | None, Header()] = None,
) -> ProposalResponse:
    """Create the proposal for an offer and send it. Asking twice returns the same proposal."""
    session = require_session(request, repository, x_session_token or body.session_token)
    filters = {"id": body.offer_id, "customer_id": session["customer_id"]}
    offers = repository.select("insurance_offers", filters)
    if not offers:
        raise ApiError(404, "offer_not_found", "No such offer for this customer.")
    offer = offers[0]
    if offer["customer_response"] == "declined":
        raise ApiError(409, "offer_declined", "The customer declined this offer.")

    customer = repository.select("customers", {"id": session["customer_id"]})[0]
    existing = repository.select("proposals", {"offer_id": offer["id"]})
    email_sent = message_sent = False
    if existing:
        proposal = existing[0]
    else:
        accepted = offer["customer_response"] == "accepted"
        proposal = repository.insert(
            "proposals",
            {
                "offer_id": offer["id"],
                "customer_id": customer["id"],
                "product_code": offer["product_code"],
                "quote_number": offer.get("quote_number"),
                "proposal_number": f"PR-{utc_now().year}-{secrets.token_hex(3).upper()}",
                "signing_token": secrets.token_urlsafe(24) if accepted else None,
                "status": "sent",
                "sent_to": mask_email(customer["email"]),
                "created_at": utc_now().isoformat(),
                "viewed_at": None,
            },
        )
    link = signing_link(settings, proposal)
    if not existing:
        product = quotes.for_proposal(repository, proposal)
        subject = f"Banco Magallanes: {product['name']}"
        email_sent = send_email(settings, customer["email"], subject, proposal_email(product, link))
        message_sent = send_to_messaging(settings, customer, product, proposal)

    audit.note(
        request,
        outcome="proposal_sent",
        proposal_number=proposal["proposal_number"],
        email_sent=email_sent,
        message_sent=message_sent,
    )
    return ProposalResponse(
        proposal_number=proposal["proposal_number"],
        quote_number=proposal.get("quote_number"),
        signing_url=link,
        sent_to=proposal["sent_to"],
        email_sent=email_sent,
        message_sent=message_sent,
    )


@router.get(
    "/insurance/proposals/{proposal_id}",
    response_model=ProposalStatusResponse,
    response_model_exclude_none=True,
)
def proposal_status(
    proposal_id: str,
    request: Request,
    session: Annotated[Row, Depends(session_from_request)],
    repository: Annotated[Repository, Depends(get_repository)],
    wait: waiting.Wait = 0,
) -> ProposalStatusResponse:
    """Say whether the customer has signed. Once signed, give the policy number and start date.

    With `wait`, the answer is held while the proposal is unsigned, so the
    caller learns of the signature without asking again.
    """
    filters = {"proposal_number": proposal_id, "customer_id": session["customer_id"]}
    if not repository.select("proposals", filters):
        raise ApiError(404, "proposal_not_found", "No such proposal for this customer.")
    proposal = waiting.until_settled(
        lambda: repository.select("proposals", filters)[0],
        lambda row: signature.proposal_status(row, utc_now()) != "pending",
        wait,
    )
    status = signature.proposal_status(proposal, utc_now())
    audit.note(request, outcome=f"proposal_{status}", proposal_number=proposal["proposal_number"])
    policy = signature.policy_for(repository, proposal) if status == "signed" else None
    if policy is None:
        return ProposalStatusResponse(proposal_number=proposal["proposal_number"], status=status)
    return ProposalStatusResponse(
        proposal_number=proposal["proposal_number"],
        status=status,
        policy_number=policy["policy_number"],
        start_date=bank_date(parse_time(policy["started_at"])).isoformat(),
    )
