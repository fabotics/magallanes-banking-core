"""Cases: work handed to the bank's staff.

A case is how the agent passes context to a person: a fraud report, a handoff,
a complaint or a callback request. A handoff is allowed without a verified
session, so a customer who fails identity is never left at a dead end, but
then no customer data is attached to it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app import audit
from app.clock import utc_now
from app.db import Repository, Row, get_repository
from app.errors import ApiError
from app.schemas import CaseRequest, CaseResponse
from app.security import find_session, require_session

# Which team receives each type of case, and the hours they have to answer.
ROUTING = {
    "fraud": ("fraud_operations", 24),
    "handoff": ("contact_center", 1),
    "complaint": ("customer_care", 72),
    "callback": ("advisors", 24),
}
DEFAULT_CALLBACK_WINDOW = "Next business day, between 09:00 and 13:00"

router = APIRouter(tags=["cases"])


def customer_transaction_ids(repository: Repository, customer_id: str) -> set[str]:
    """Return the ids of every transaction on the customer's cards."""
    ids = set()
    for card in repository.select("cards", {"customer_id": customer_id}):
        for transaction in repository.select("transactions", {"card_id": card["id"]}):
            ids.add(transaction["id"])
    return ids


def check_ownership(repository: Repository, customer_id: str, transaction_ids: list[str]) -> None:
    """Refuse a case that names a transaction the customer does not own."""
    unknown = set(transaction_ids) - customer_transaction_ids(repository, customer_id)
    if unknown:
        raise ApiError(404, "transaction_not_found", "A transaction is not on this customer.")


@router.post("/cases", response_model=CaseResponse, response_model_exclude_none=True)
def create_case(
    body: CaseRequest,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    x_session_token: Annotated[str | None, Header()] = None,
) -> CaseResponse:
    """Open a case and return its number, the receiving queue and the answer time."""
    token = x_session_token or body.session_token
    session: Row | None
    if body.type == "handoff":
        session = find_session(repository, token)
    else:
        session = require_session(request, repository, token)

    customer_id = session["customer_id"] if session else None
    transaction_ids = body.transaction_ids if session else []
    if customer_id:
        check_ownership(repository, customer_id, transaction_ids)
    callback_window = body.callback_window
    if body.type == "callback" and not callback_window:
        callback_window = DEFAULT_CALLBACK_WINDOW

    case = repository.insert(
        "cases",
        {
            "customer_id": customer_id,
            "type": body.type,
            "priority": body.priority or ("high" if body.type == "fraud" else "normal"),
            "status": "open",
            "summary": body.summary,
            "transaction_ids": transaction_ids,
            "conversation_id": body.conversation_id or (session or {}).get("conversation_id"),
            "callback_window": callback_window,
            "created_at": utc_now().isoformat(),
        },
    )
    if body.type == "fraud":
        for transaction_id in transaction_ids:
            repository.update("transactions", {"id": transaction_id}, {"is_disputed": True})

    queue, sla_hours = ROUTING[body.type]
    audit.note(
        request,
        customer_id=customer_id,
        conversation_id=case["conversation_id"],
        outcome="case_created",
        case_number=case["case_number"],
        case_type=body.type,
    )
    return CaseResponse(
        case_number=case["case_number"],
        queue=queue,
        sla_hours=sla_hours,
        callback_window=callback_window,
    )
