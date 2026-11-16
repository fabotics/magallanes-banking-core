"""Notifications: send the customer a written summary of the call.

The summary goes to the messaging channel the bank has on file for the
verified customer. The caller never chooses the destination. If a conversation
ends before the agent sent one, the bank writes its own from its records.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app import audit, closing, notices
from app.config import Settings, get_settings
from app.db import Repository, get_repository
from app.messaging import send_telegram
from app.schemas_notifications import (
    CallSummaryRequest,
    CallSummaryResponse,
    ClosingSummaryResponse,
    ConversationEnded,
)
from app.security import require_session

router = APIRouter(tags=["notifications"])


@router.post("/notifications/call-summary", response_model=CallSummaryResponse)
def send_call_summary(
    body: CallSummaryRequest,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_session_token: Annotated[str | None, Header()] = None,
) -> CallSummaryResponse:
    """Send the call summary to the customer's messaging channel, if they have one."""
    session = require_session(request, repository, x_session_token or body.session_token)
    customer = repository.select("customers", {"id": session["customer_id"]})[0]
    chat_id = customer["telegram_chat_id"]
    if not chat_id:
        audit.note(request, outcome="summary_no_channel")
        return CallSummaryResponse(sent=False, channel="none")

    language = notices.language_for(customer, body.language)
    text = notices.chat(language, "summary") + f"\n\n{body.summary}"
    sent = send_telegram(settings, chat_id, text)
    # The summary text is customer data, so only the result is recorded.
    audit.note(request, outcome="summary_sent" if sent else "summary_not_sent")
    return CallSummaryResponse(sent=sent, channel="telegram")


@router.post(
    "/notifications/conversation-ended",
    response_model=ClosingSummaryResponse,
    response_model_exclude_none=True,
)
def conversation_ended(
    body: ConversationEnded,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClosingSummaryResponse:
    """Send the bank's own summary when a conversation ended without one.

    Nothing is sent for a conversation where nobody was verified, where the
    agent already sent its summary, or where the bank recorded nothing.
    """
    conversation_id = body.named_conversation() or ""
    audit.note(request, conversation_id=conversation_id)
    customer = closing.verified_customer(repository, conversation_id) if conversation_id else None
    if customer is None:
        audit.note(request, outcome="closing_not_verified")
        return ClosingSummaryResponse(sent=False, reason="not_verified")
    audit.note(request, customer_id=customer["id"])
    if closing.already_sent(repository, conversation_id):
        audit.note(request, outcome="closing_already_sent")
        return ClosingSummaryResponse(sent=False, reason="already_sent")
    text = closing.summary(repository, conversation_id, customer)
    if text is None:
        audit.note(request, outcome="closing_nothing_recorded")
        return ClosingSummaryResponse(sent=False, reason="nothing_recorded")
    if not customer["telegram_chat_id"]:
        audit.note(request, outcome="closing_no_channel")
        return ClosingSummaryResponse(sent=False, reason="no_channel")
    sent = send_telegram(settings, customer["telegram_chat_id"], text)
    audit.note(request, outcome="closing_summary_sent" if sent else "closing_summary_not_sent")
    return ClosingSummaryResponse(sent=sent)
