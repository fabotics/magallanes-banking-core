"""Signature page: a minimal stand-in for the bank's own e-signature app.

The customer opens the link from the proposal, reads it and signs. Signing
marks the proposal as signed and creates the policy. The page needs no API
key: the long random token in the link is what grants access to one proposal.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.clock import utc_now
from app.db import Repository, Row, get_repository

router = APIRouter(tags=["signing"])
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def render(request: Request, repository: Repository, proposal: Row | None) -> HTMLResponse:
    """Render the page for a proposal, or a not-found page when the link is wrong."""
    if proposal is None:
        return templates.TemplateResponse(request, "sign.html", {"proposal": None}, 404)
    context = {
        "proposal": proposal,
        "product": repository.select("insurance_products", {"code": proposal["product_code"]})[0],
        "customer": repository.select("customers", {"id": proposal["customer_id"]})[0],
    }
    return templates.TemplateResponse(request, "sign.html", context)


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
    """Show the proposal with a button to sign it."""
    return render(request, repository, find_proposal(repository, signing_token))


@router.post("/sign/{signing_token}", response_class=HTMLResponse)
def sign_proposal(
    signing_token: str,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
) -> HTMLResponse:
    """Sign the proposal and create the policy. Signing twice changes nothing."""
    proposal = find_proposal(repository, signing_token)
    if proposal is not None and proposal["status"] == "sent":
        now = utc_now().isoformat()
        values = {"status": "signed", "signed_at": now}
        proposal = repository.update("proposals", {"id": proposal["id"]}, values)[0]
        repository.insert(
            "policies",
            {
                "customer_id": proposal["customer_id"],
                "product_code": proposal["product_code"],
                "status": "active",
                "started_at": now,
            },
        )
        # This page is outside `/v1`, so it writes its own audit row. The token is not recorded.
        repository.insert(
            "audit_log",
            {
                "at": now,
                "endpoint": "/sign/{signing_token}",
                "method": "POST",
                "customer_id": proposal["customer_id"],
                "conversation_id": None,
                "outcome": "proposal_signed",
                "detail": {"proposal_number": proposal["proposal_number"]},
            },
        )
    return render(request, repository, proposal)
