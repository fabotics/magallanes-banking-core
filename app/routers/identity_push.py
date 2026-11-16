"""Identity confirmation in the bank's app: the first choice, ahead of the spoken check.

The caller asks for a confirmation, the customer approves or denies it in the
app, and the caller reads the result. An approval opens the same 15 minute
session as the spoken check. Lockout and audit work the same way on both paths.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app import audit, confirmations
from app.clock import utc_now
from app.config import Settings, get_settings
from app.db import Repository, get_repository
from app.errors import ApiError
from app.routers.identity import (
    MAX_FAILED_ATTEMPTS,
    normalize_document,
    open_session,
    recent_failures,
)
from app.schemas_identity import PushRequest, PushResponse, PushStatusResponse

router = APIRouter(tags=["identity"])


@router.post("/identity/push", response_model=PushResponse, response_model_exclude_none=True)
def request_confirmation(
    body: PushRequest,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PushResponse:
    """Create a pending confirmation and notify the customer. Never says if they exist."""
    now = utc_now()
    document = normalize_document(body.customer_id)
    audit.note(request, conversation_id=body.conversation_id, document=audit.mask(document))
    if recent_failures(repository, document, now) >= MAX_FAILED_ATTEMPTS:
        audit.note(request, outcome="locked")
        return PushResponse(status="locked")

    customers = repository.select("customers", {"document_number": document})
    customer = customers[0] if customers else None
    confirmation = confirmations.create(repository, document, customer, body.conversation_id, now)
    notified = customer is not None and confirmations.notify(settings, customer, confirmation)
    audit.note(
        request,
        customer_id=customer["id"] if customer else None,
        outcome="push_requested",
        notified=notified,
    )
    return PushResponse(
        status="pending",
        request_id=confirmation["id"],
        expires_in_seconds=int(confirmations.CONFIRMATION_LIFETIME.total_seconds()),
    )


@router.get(
    "/identity/push/{request_id}",
    response_model=PushStatusResponse,
    response_model_exclude_none=True,
)
def confirmation_status(
    request_id: uuid.UUID,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
) -> PushStatusResponse:
    """Say where the confirmation stands. Once approved, hand over the session."""
    found = repository.select(confirmations.TABLE, {"id": str(request_id)})
    if not found:
        raise ApiError(404, "request_not_found", "No such confirmation request.")
    confirmation = found[0]
    now = utc_now()
    status = confirmations.current_status(confirmation, now)
    audit.note(
        request,
        customer_id=confirmation["customer_id"],
        conversation_id=confirmation["conversation_id"],
        outcome=f"push_{status}",
    )
    if status != "approved":
        return PushStatusResponse(status=status)

    customer = repository.select("customers", {"id": confirmation["customer_id"]})[0]
    token = confirmation["session_token"]
    if token is None:
        # The first read after the approval opens the session. Later reads return the same one.
        token = open_session(repository, customer, confirmation["conversation_id"], now)
        repository.update(confirmations.TABLE, {"id": confirmation["id"]}, {"session_token": token})
    return PushStatusResponse(
        status="approved", session_token=token, first_name=customer["first_name"]
    )
