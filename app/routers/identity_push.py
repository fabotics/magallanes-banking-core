"""Identity confirmation in the bank's app: the first choice, ahead of the spoken check.

The caller asks for a confirmation, the customer approves or denies it in the
app, and the caller reads the result. An approval opens the same 15 minute
session as the spoken check. Lockout and audit work the same way on both paths.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app import audit, confirmations, crm_sync, overview, waiting
from app.clock import utc_now
from app.config import Settings, get_settings
from app.db import Repository, get_repository
from app.errors import ApiError
from app.routers.identity import (
    MAX_FAILED_ATTEMPTS,
    heard_document,
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
    """Create a pending confirmation and notify the customer.

    For an ID number the answer never says whether it is known. When only the
    channel names the customer and it names nobody, the answer is
    `not_identified`, so the caller asks for the ID number instead of waiting
    for an approval that cannot come.
    """
    now = utc_now()
    spoken = heard_document(repository, body.customer_id or "")
    customer, document, named_by = confirmations.named_customer(
        repository, body.customer_ref, body.phone, spoken
    )
    audit.note(
        request,
        conversation_id=body.conversation_id,
        document=audit.mask(document),
        named_by=named_by,
    )
    if named_by == "nobody":
        audit.note(request, outcome="channel_names_nobody")
        return PushResponse(status="not_identified")
    if recent_failures(repository, document, now) >= MAX_FAILED_ATTEMPTS:
        audit.note(request, outcome="locked")
        return PushResponse(status="locked")

    confirmation = confirmations.create(repository, document, customer, body.conversation_id, now)
    notified = customer is not None and confirmations.notify(
        settings, customer, confirmation, body.language
    )
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
    settings: Annotated[Settings, Depends(get_settings)],
    wait: waiting.Wait = 0,
) -> PushStatusResponse:
    """Say where the confirmation stands. Once approved, hand over the session.

    With `wait`, the answer is held while the request is pending, so the
    caller learns of the customer's answer without asking again. An approval
    of any request of the same conversation counts. While there is none,
    `next_step` says what to do: ask the customer how they are getting on,
    send a new request when this one ran out of time, or, after many checks
    or a denial, offer another way.
    """
    filters = {"id": str(request_id)}
    found = repository.select(confirmations.TABLE, filters)
    if not found:
        raise ApiError(404, "request_not_found", "No such confirmation request.")
    first = confirmations.is_first(repository, found[0])
    earlier = confirmations.checks_so_far(repository, request.url.path)
    confirmation = waiting.until_settled(
        lambda: confirmations.answered(
            repository, repository.select(confirmations.TABLE, filters)[0]
        ),
        lambda row: confirmations.current_status(row, utc_now()) != "pending",
        wait if earlier < confirmations.MAX_CHECKS else 0,
    )
    now = utc_now()
    status = confirmations.current_status(confirmation, now)
    audit.note(
        request,
        customer_id=confirmation["customer_id"],
        conversation_id=confirmation["conversation_id"],
        outcome=f"push_{status}",
    )
    if status != "approved":
        step = confirmations.next_step(status, first, earlier + 1)
        audit.note(request, check=earlier + 1, next_step=step)
        return PushStatusResponse(
            status=status, next_step=step, instruction=confirmations.NEXT_STEPS[step]
        )

    customer = repository.select("customers", {"id": confirmation["customer_id"]})[0]
    token = confirmation["session_token"]
    if token is None:
        # The first read after the approval opens the session. Later reads return the same one.
        token = open_session(repository, customer, confirmation["conversation_id"], now)
        repository.update(confirmations.TABLE, {"id": confirmation["id"]}, {"session_token": token})
        crm_sync.noted(request, crm_sync.customer_verified(settings, customer))
    return PushStatusResponse(
        status="approved",
        session_token=token,
        first_name=customer["first_name"],
        overview=overview.after_verification(repository, customer),
        review_route=overview.first_route(customer),
    )
