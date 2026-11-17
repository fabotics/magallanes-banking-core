"""What the customer concluded about their charges, and taking a case back.

A doubt is not a fraud report. The caller records the customer's answer only
after the charges were explained: recognised, or not recognised. And when a
case was opened too early and the customer then recognises the charges, the
caller withdraws it, so nobody at the bank works on a case that is not one.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app import audit, crm_sync
from app.config import Settings, get_settings
from app.db import Repository, Row, get_repository
from app.errors import ApiError
from app.schemas_cases import ReviewRequest, ReviewResponse, WithdrawResponse
from app.security import require_session, session_from_request

router = APIRouter(tags=["cases"])
WITHDRAWN = " [Retirado por el cliente: reconoció los cargos.]"
# What the caller does next, said in a sentence so it does not have to decide.
NEXT = {
    "recognised": "The customer recognises the charges. No block and no case. Go on.",
    "not_recognised": "The customer does not recognise the charges after the explanation. "
    "Propose the temporary block and the fraud case now.",
}


@router.post("/cards/review", response_model=ReviewResponse)
def record_review(
    body: ReviewRequest,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    x_session_token: Annotated[str | None, Header()] = None,
) -> ReviewResponse:
    """Record whether the customer recognises the charges that were explained to them."""
    require_session(request, repository, x_session_token or body.session_token)
    audit.note(request, outcome=f"charges_{body.outcome}")
    return ReviewResponse(outcome=body.outcome, next_step=NEXT[body.outcome])


@router.post("/cases/{case_number}/withdraw", response_model=WithdrawResponse)
def withdraw_case(
    case_number: str,
    request: Request,
    session: Annotated[Row, Depends(session_from_request)],
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WithdrawResponse:
    """Close a case the customer takes back, and clear the dispute on its charges.

    Only the customer's own case, and asking twice is harmless. A card that was
    blocked stays blocked: the customer lifts the block in the app.
    """
    owned = {"case_number": case_number, "customer_id": session["customer_id"]}
    cases = repository.select("cases", owned)
    if not cases:
        raise ApiError(404, "case_not_found", "No such case for this customer.")
    case = cases[0]
    if case["status"] == "open":
        closed = {"status": "closed", "summary": case["summary"] + WITHDRAWN}
        repository.update("cases", {"id": case["id"]}, closed)
        for transaction_id in case["transaction_ids"]:
            repository.update("transactions", {"id": transaction_id}, {"is_disputed": False})
    audit.note(request, outcome="case_withdrawn", case_number=case_number)
    crm_sync.noted(request, crm_sync.case_withdrawn(settings, case_number))
    return WithdrawResponse(case_number=case_number, status="withdrawn")
