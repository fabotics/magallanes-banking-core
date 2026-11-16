"""Notifications: send the customer a written summary of the call.

The summary goes to the messaging channel the bank has on file for the
verified customer. The caller never chooses the destination.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app import audit, notices
from app.config import Settings, get_settings
from app.db import Repository, get_repository
from app.messaging import send_telegram
from app.schemas_notifications import CallSummaryRequest, CallSummaryResponse
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
