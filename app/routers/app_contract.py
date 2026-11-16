"""The bank's app, part three: the contract the customer reads, initials and signs.

The signature is checked on the server: initials on every page, the full name
typed as the signature, and the final confirmation. The audit row of the
signature records the language the contract was shown in and the fingerprint
of that wording. What a signature then does is defined once, in
`app/signature.py`, and is the same as on the signing link.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app import app_session, contracts, i18n, signature
from app.clock import bank_date, parse_time, utc_now
from app.config import Settings, get_settings
from app.db import Repository, Row, get_repository
from app.formatting import long_date

router = APIRouter(tags=["app"], include_in_schema=False)
PROPOSAL_ENDPOINT = "/app/proposals/{proposal_number}"
GONE = ("gone_title", "proposal_gone")


def find_proposal(repository: Repository, customer: Row, number: str) -> Row | None:
    """Return the customer's own proposal that can be signed, if it exists."""
    filters = {"proposal_number": number, "customer_id": customer["id"]}
    found = repository.select("proposals", filters)
    return found[0] if found and found[0]["signing_token"] else None


def build_contract(repository: Repository, customer: Row, proposal: Row, language: str) -> dict:
    """Build the contract for this proposal in one language."""
    product = repository.select("insurance_products", {"code": proposal["product_code"]})[0]
    cards = repository.select("cards", {"customer_id": customer["id"]})
    issued = bank_date(parse_time(proposal["created_at"]))
    card = cards[0] if cards else None
    return contracts.build(language, proposal, product, customer, card, issued)


def signed_page(request: Request, repository: Repository, proposal: Row) -> Response:
    """The success screen: policy number, start date, and where the details are going."""
    language = i18n.pick_language(request)
    words = i18n.TEXTS[language]
    policy = signature.policy_for(repository, proposal)
    start = long_date(bank_date(parse_time(policy["started_at"])), language)
    details = [(words["policy"], policy["policy_number"]), (words["since"], start)]
    document_hash = signature.signing_record(repository, proposal).get("document_hash")
    if document_hash:
        details.append((words["document_print"], document_hash[:16]))
    note = words["signed_note"]
    return app_session.message(
        request, "signed_title", "signed_text", "ok", details=details, note=note
    )


def contract_page(
    request: Request, repository: Repository, customer: Row, proposal: Row,
    language: str, error: str | None = None, typed_name: str = "",
) -> Response:  # fmt: skip
    """Render the contract with the customer's details filled in."""
    context = {
        "signed_in": True, "lang": language, "customer": customer, "proposal": proposal,
        "contract": build_contract(repository, customer, proposal, language),
        "total": contracts.PAGES, "initials": contracts.initials(customer),
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
        return app_session.message(request, *GONE)
    proposal = signature.mark_viewed(repository, proposal, utc_now(), PROPOSAL_ENDPOINT)
    return contract_page(request, repository, customer, proposal, i18n.pick_language(request))


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
        return app_session.message(request, *GONE)

    # The form says which language it was shown in. That is the one the customer read.
    language = i18n.known(fields.get("lang"), i18n.pick_language(request))
    typed = fields.get("signature_name", "")
    pages = range(1, contracts.PAGES + 1)
    error = None
    if not all(fields.get(f"initial_{number}") == "yes" for number in pages):
        error = "missing_initials"
    elif not contracts.name_matches(typed, customer):
        error = "name_mismatch"
    elif fields.get("accept") != "yes":
        error = "missing_accept"
    if error:
        return contract_page(request, repository, customer, proposal, language, error, typed)
    contract = build_contract(repository, customer, proposal, language)
    signature.sign(
        repository, settings, proposal, now, PROPOSAL_ENDPOINT,
        language=language, document_hash=contracts.fingerprint(contract),
    )  # fmt: skip
    return signed_page(request, repository, find_proposal(repository, customer, proposal_number))
