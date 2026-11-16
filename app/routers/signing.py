"""Signature page: the link in the proposal, for a customer who is not using the bank's app.

The customer opens the link, reads the proposal and signs. The page needs no
API key: the long random token in the link is what grants access to one
proposal. What a signature does is defined once, in `app/signature.py`.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import contracts, i18n, signature
from app.clock import bank_date, parse_time, utc_now
from app.config import Settings, get_settings
from app.db import Repository, Row, get_repository
from app.formatting import long_date, money

router = APIRouter(tags=["signing"])
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
# The audit trail records the route, never the token.
ENDPOINT = "/sign/{signing_token}"


def render(request: Request, repository: Repository, proposal: Row | None) -> HTMLResponse:
    """Render the page for a proposal, or a not-found page when the link is wrong."""
    language = i18n.pick_language(request)
    context = {
        "proposal": proposal,
        "lang": language,
        "t": i18n.TEXTS[language],
        "languages": i18n.switch_links(request),
    }
    if proposal is None:
        response = templates.TemplateResponse(request, "sign.html", context, 404)
        i18n.remember(request, response)
        return response
    product = repository.select("insurance_products", {"code": proposal["product_code"]})[0]
    policy = signature.policy_for(repository, proposal)
    name, cover = contracts.product_wording(product, language)
    start = long_date(bank_date(parse_time(policy["started_at"])), language) if policy else None
    context.update(
        status=signature.proposal_status(proposal, utc_now()),
        product_name=name,
        cover=cover,
        premium=money(product["monthly_premium"], product["currency"], language),
        customer=repository.select("customers", {"id": proposal["customer_id"]})[0],
        policy=policy,
        start=start,
    )
    response = templates.TemplateResponse(request, "sign.html", context)
    i18n.remember(request, response)
    return response


def find_proposal(repository: Repository, signing_token: str) -> Row | None:
    """Return the proposal behind a signing link, if any."""
    proposals = repository.select("proposals", {"signing_token": signing_token})
    return proposals[0] if proposals else None


@router.get("/sign/{signing_token}", response_class=HTMLResponse)
def show_proposal(
    signing_token: str,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
) -> HTMLResponse:
    """Show the proposal with a button to sign it, and record that it was seen."""
    proposal = find_proposal(repository, signing_token)
    if proposal is not None:
        proposal = signature.mark_viewed(repository, proposal, utc_now(), ENDPOINT)
    return render(request, repository, proposal)


@router.post("/sign/{signing_token}", response_class=HTMLResponse)
def sign_proposal(
    signing_token: str,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    """Sign the proposal and create the policy. Signing twice changes nothing.

    The audit row records the language the page was shown in.
    """
    proposal = find_proposal(repository, signing_token)
    if proposal is not None:
        language = i18n.pick_language(request)
        signature.sign(repository, settings, proposal, utc_now(), ENDPOINT, language=language)
        proposal = find_proposal(repository, signing_token)
    return render(request, repository, proposal)
