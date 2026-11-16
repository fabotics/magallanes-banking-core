"""The bank's app, part four: talking to the bank's assistant from inside the app.

The page exists only behind the PIN. The conversation widget is not part of
this code: its embed snippet comes from the environment, and this page fills
in who the customer is. So the assistant can send the identity confirmation
straight to this app, without asking for a document number.

The customer reference is where the confirmation goes. It proves nothing by
itself: the approval in the app is still what verifies the customer.
"""

import html
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app import app_session, i18n
from app.clock import utc_now
from app.config import Settings, get_settings
from app.db import Repository, Row, get_repository
from app.routers.app_pages import waiting_items

router = APIRouter(tags=["app"], include_in_schema=False)
PLACEHOLDER = "{variables}"


def embed(settings: Settings, customer: Row) -> str:
    """Return the widget snippet with this customer's reference filled in."""
    variables = {"channel": "app", "channel_identity": customer["id"]}
    filled = html.escape(json.dumps(variables), quote=True)
    return settings.assistant_embed_html.replace(PLACEHOLDER, filled)


@router.get("/app/assistant", response_class=HTMLResponse)
def assistant(
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Show the page with the conversation widget, for a signed-in customer."""
    customer = app_session.current_customer(request, repository)
    if customer is None:
        return app_session.to_login(request)
    if not settings.assistant_embed_html:
        return app_session.message(request, "assistant_off_title", "assistant_off_text")
    context = {
        "signed_in": True,
        "assistant": True,
        "tab": "assistant",
        "embed": embed(settings, customer),
    }
    return app_session.page(request, "assistant", context)


@router.get("/app/assistant/waiting")
def waiting(
    request: Request, repository: Annotated[Repository, Depends(get_repository)]
) -> JSONResponse:
    """List what is waiting for the customer, for the page to draw without reloading."""
    customer = app_session.current_customer(request, repository)
    if customer is None:
        return JSONResponse({"error": "signed_out"}, status_code=401)
    language = i18n.pick_language(request)
    confirmations, proposals = waiting_items(repository, customer, language, utc_now())
    body = {
        "confirmations": [{"id": item["id"], "code": item["code"]} for item in confirmations],
        "proposals": [
            {
                "number": item["proposal_number"],
                "name": item["product_name"],
                "premium": item["premium"],
            }
            for item in proposals
        ],
    }
    return JSONResponse(body, headers={"Cache-Control": "no-store"})
