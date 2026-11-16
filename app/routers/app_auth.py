"""The bank's app, part one: the PIN screen, signing in and signing out.

These pages are public, like a phone app anyone can open. The first visit
asks for the ID number and the PIN. Once someone has signed in, the browser
remembers them and asks for the PIN only, with a way to sign in as someone
else. Nothing about a customer is shown before the PIN, except the first
name the app greets with.
"""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import app_session, audit, i18n
from app.clock import utc_now
from app.config import Settings, get_settings
from app.db import Repository, Row, get_repository
from app.routers.identity import normalize_document

router = APIRouter(tags=["app"], include_in_schema=False)
# What the PIN screen says after a failed attempt (a key of the text tables) and the status.
ERRORS = {"wrong": ("pin_wrong", 401), "locked": ("pin_locked", 429)}
# The full form never says which of the two was wrong, or whether the ID number is known.
FORM_ERRORS = {"wrong": ("login_wrong", 401), "locked": ("pin_locked", 429)}


def not_enrolled(request: Request) -> Response:
    """The page for a link that names no known customer."""
    return app_session.message(
        request, "not_enrolled_title", "not_enrolled_text", status=404, signed_in=False
    )


def dialable(phone_line: str) -> str:
    """Return a phone number as a `tel:` link wants it: the plus sign and the digits only."""
    return "".join(c for c in phone_line if c.isdigit() or c == "+")


def login_page(
    request: Request,
    customer: Row | None,
    target: str,
    error: str | None = None,
    status: int = 200,
    document: str = "",
    phone_line: str = "",
) -> Response:
    """Render the sign-in screen: PIN only for a known customer, else ID number and PIN.

    `phone_line` is the bank's phone number, shown as another way to reach the bank.
    """
    other = f"/app?{urlencode({'other': '1', 'next': target})}"
    context = {
        "customer": customer, "next": target, "error": error, "document": document, "other": other,
        "phone_line": phone_line.strip(), "phone_dial": dialable(phone_line),
    }  # fmt: skip
    # After a failed attempt the language links go back to the same kind of screen.
    back = {"u": customer["id"], "next": target} if customer else {"other": "1", "next": target}
    return app_session.page(request, "login", context, status, switch_to=("/app", back))


@router.get("/app", response_class=HTMLResponse)
def sign_in_screen(
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    u: str | None = None,
    next: str | None = None,
    other: str | None = None,
) -> Response:
    """Show the sign-in screen, or go straight in when a session is already open.

    A link from the bank names the customer (`u`). Without one, the browser's
    memory of the last sign-in decides. `other` asks for the full form.
    """
    target = app_session.safe_next(next)
    line = settings.bank_phone_line
    signed_in = app_session.current_customer(request, repository)
    if signed_in is not None and (u is None or u == signed_in["id"]):
        response = RedirectResponse(target, status_code=303)
        i18n.remember(request, response)
        return response
    if u is not None:
        customer = app_session.customer_by_id(repository, u)
        if customer is None:
            return not_enrolled(request)
        return login_page(request, customer, target, phone_line=line)
    customer = None if other else app_session.remembered_customer(request, repository)
    return login_page(request, customer, target, phone_line=line)


def who_signs_in(repository: Repository, fields: dict[str, str]) -> Row | None:
    """Return the customer a posted form names: by the hidden id, or by the typed ID number."""
    if "document" in fields:
        document = normalize_document(fields["document"])
        found = repository.select("customers", {"document_number": document}) if document else []
        return found[0] if found else None
    return app_session.customer_by_id(repository, fields.get("u"))


@router.post("/app/login", response_class=HTMLResponse)
def sign_in(
    request: Request,
    fields: Annotated[dict[str, str], Depends(app_session.form_fields)],
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Check the PIN. A correct one opens a session and remembers the customer."""
    target = app_session.safe_next(fields.get("next"))
    full_form = "u" not in fields
    typed = fields.get("document", "")[:20]
    customer = who_signs_in(repository, fields)
    line = settings.bank_phone_line
    if customer is None:
        if not full_form:
            return not_enrolled(request)
        # An unknown ID number gets the same answer as a wrong PIN.
        audit.record(repository, "/app/login", "POST", None, "app_login_unknown")
        return login_page(request, None, target, *FORM_ERRORS["wrong"], typed, line)
    now = utc_now()
    result = app_session.try_pin(repository, customer, fields.get("pin", ""), now)
    audit.record(repository, "/app/login", "POST", customer["id"], f"app_pin_{result}")
    if result != "ok":
        if full_form:
            return login_page(request, None, target, *FORM_ERRORS[result], typed, line)
        return login_page(request, customer, target, *ERRORS[result], phone_line=line)
    secure = settings.public_base_url.startswith("https://")
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        app_session.COOKIE,
        app_session.open_session(repository, customer, now),
        max_age=int(app_session.SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    response.set_cookie(
        app_session.REMEMBER_COOKIE,
        customer["id"],
        max_age=app_session.REMEMBER_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    return response


@router.get("/app/login", include_in_schema=False)
@router.get("/app/logout", include_in_schema=False)
def back_to_the_sign_in_screen() -> Response:
    """Send a browser that asks for these addresses directly to the sign-in screen.

    Both addresses only take a posted form. A reload or the back button after a
    wrong PIN asks for them with GET, and that must not end on an error.
    """
    return RedirectResponse("/app", status_code=303)


@router.post("/app/logout")
def sign_out(
    request: Request, repository: Annotated[Repository, Depends(get_repository)]
) -> Response:
    """Close the session and forget who it was: the next visit starts at the full form."""
    token = request.cookies.get(app_session.COOKIE)
    if token:
        repository.update("app_sessions", {"token": token}, {"expires_at": utc_now().isoformat()})
    response = RedirectResponse("/app", status_code=303)
    response.delete_cookie(app_session.COOKIE)
    response.delete_cookie(app_session.REMEMBER_COOKIE)
    return response
