"""The bank's app, part four: talking to the bank's assistant from inside the app.

The page exists only behind the PIN. The conversation widget is not part of
this code: its embed snippet comes from the environment, and this page fills
in who the customer is and which language the app is in. So the assistant can
send the identity confirmation straight to this app, without asking for a
document number, and it speaks the language the customer reads.

The widget lives in a frame of its own that fills the Assistant view. A frame
is as narrow as a phone on any screen, and nothing inside it can cover the
app's header or its menu.

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
VARIABLES = "{variables}"
LANGUAGE = "{lang}"


def embed(settings: Settings, customer: Row, language: str) -> str:
    """Return the widget snippet with the customer's reference and the language filled in."""
    variables = {"channel": "app", "channel_identity": customer["id"]}
    filled = html.escape(json.dumps(variables), quote=True)
    return settings.assistant_embed_html.replace(VARIABLES, filled).replace(LANGUAGE, language)


@router.get("/app/assistant", response_class=HTMLResponse)
def assistant(
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Show the Assistant view: the frame with the widget, and what is waiting on top of it."""
    customer = app_session.current_customer(request, repository)
    if customer is None:
        return app_session.to_login(request)
    if not settings.assistant_embed_html:
        return app_session.message(request, "assistant_off_title", "assistant_off_text")
    context = {"signed_in": True, "assistant": True, "tab": "assistant"}
    return app_session.page(request, "assistant", context)


@router.get("/app/assistant/widget", response_class=HTMLResponse)
def widget(
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """The inside of the frame: the introduction and the widget, in the app's language."""
    customer = app_session.current_customer(request, repository)
    if customer is None or not settings.assistant_embed_html:
        return Response(status_code=404)
    language = i18n.pick_language(request)
    response = app_session.page(
        request, "assistant_widget", {"embed": embed(settings, customer, language)}
    )
    # Only the app itself may put this page in a frame.
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


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
