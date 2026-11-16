"""The bank's app, part three: the contract the customer reads, initials and signs.

The signature is checked on the server: initials on every page, the full name
typed as the signature, and the final confirmation. What a signature then does
is defined once, in `app/signature.py`, and is the same as on the signing link.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app import app_session, contracts, signature
from app.clock import bank_date, parse_time, utc_now
from app.config import Settings, get_settings
from app.db import Repository, Row, get_repository
from app.formatting import card_label, document, long_date, money

router = APIRouter(tags=["app"], include_in_schema=False)
PROPOSAL_ENDPOINT = "/app/proposals/{proposal_number}"
GONE = {"title": "No disponible", "text": "Esta propuesta no existe o ya no está vigente."}


def find_proposal(repository: Repository, customer: Row, number: str) -> Row | None:
    """Return the customer's own proposal that can be signed, if it exists."""
    filters = {"proposal_number": number, "customer_id": customer["id"]}
    found = repository.select("proposals", filters)
    return found[0] if found and found[0]["signing_token"] else None


def signed_page(request: Request, repository: Repository, proposal: Row) -> Response:
    """The success screen: policy number, start date, and where the details are going."""
    policy = signature.policy_for(repository, proposal)
    details = [
        ("Póliza", policy["policy_number"]),
        ("Vigente desde", long_date(bank_date(parse_time(policy["started_at"])))),
    ]
    note = "Los detalles van en camino a su correo y a su mensajería."
    text = "Su seguro quedó contratado."
    return app_session.message(request, "Firma recibida", text, "ok", details=details, note=note)


def contract_page(
    request: Request, repository: Repository, customer: Row, proposal: Row,
    error: str | None = None, typed_name: str = "",
) -> Response:  # fmt: skip
    """Render the contract with the customer's details filled in."""
    product = repository.select("insurance_products", {"code": proposal["product_code"]})[0]
    cards = repository.select("cards", {"customer_id": customer["id"]})
    cover, exclusions = contracts.clauses(product)
    context = {
        "signed_in": True, "customer": customer, "proposal": proposal, "product": product,
        "insurer": contracts.INSURER, "total": contracts.PAGES, "cover": cover,
        "exclusions": exclusions, "initials": contracts.initials(customer),
        "premium": money(product["monthly_premium"], product["currency"]),
        "document": document(customer["document_type"], customer["document_number"]),
        "card_label": card_label(cards[0]) if cards else "tarjeta del asegurado",
        "issued": long_date(bank_date(parse_time(proposal["created_at"]))),
        "error": error, "typed_name": typed_name,
    }  # fmt: skip
    return app_session.page(request, "contract", context, 422 if error else 200)


@router.get(PROPOSAL_ENDPOINT, response_class=HTMLResponse)
def show_contract(
    proposal_number: str,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
) -> Response:
    """Show the contract to read and sign, and record that it was seen."""
    customer = app_session.current_customer(request, repository)
    if customer is None:
        return app_session.to_login(request)
    proposal = find_proposal(repository, customer, proposal_number)
    status = signature.proposal_status(proposal, utc_now()) if proposal else "expired"
    if status == "signed":
        return signed_page(request, repository, proposal)
    if status == "expired":
        return app_session.message(request, **GONE)
    proposal = signature.mark_viewed(repository, proposal, utc_now(), PROPOSAL_ENDPOINT)
    return contract_page(request, repository, customer, proposal)


@router.post(PROPOSAL_ENDPOINT, response_class=HTMLResponse)
def sign_contract(
    proposal_number: str,
    request: Request,
    fields: Annotated[dict[str, str], Depends(app_session.form_fields)],
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Check initials, name and consent, then sign. The server checks, not only the browser."""
    customer = app_session.current_customer(request, repository)
    if customer is None:
        return app_session.to_login(request)
    proposal = find_proposal(repository, customer, proposal_number)
    now = utc_now()
    status = signature.proposal_status(proposal, now) if proposal else "expired"
    if status == "signed":
        return signed_page(request, repository, proposal)
    if status == "expired":
        return app_session.message(request, **GONE)

    typed = fields.get("signature_name", "")
    pages = range(1, contracts.PAGES + 1)
    error = None
    if not all(fields.get(f"initial_{number}") == "yes" for number in pages):
        error = "Faltan sus iniciales en una o más páginas."
    elif not contracts.name_matches(typed, customer):
        error = "El nombre de la firma no coincide con el del asegurado."
    elif fields.get("accept") != "yes":
        error = "Falta marcar la confirmación final."
    if error:
        return contract_page(request, repository, customer, proposal, error, typed)
    signature.sign(repository, settings, proposal, now, PROPOSAL_ENDPOINT)
    return signed_page(request, repository, find_proposal(repository, customer, proposal_number))
