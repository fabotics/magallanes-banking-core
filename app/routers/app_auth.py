"""The bank's app, part one: the PIN screen, signing in and signing out.

These pages are public, like a phone app anyone can open. Nothing about the
customer is shown before the PIN, except the first name the app greets with.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import app_session, audit
from app.clock import utc_now
from app.config import Settings, get_settings
from app.db import Repository, get_repository

router = APIRouter(tags=["app"], include_in_schema=False)
NOT_ENROLLED = {
    "title": "App no disponible",
    "text": "Esta app no está asociada a un cliente. Abra el enlace que le envió el banco.",
}
ERRORS = {
    "wrong": ("PIN incorrecto. Revise e intente de nuevo.", 401),
    "locked": ("Demasiados intentos. Espere un minuto e intente de nuevo.", 429),
}


@router.get("/app", response_class=HTMLResponse)
def pin_screen(
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    u: str | None = None,
    next: str | None = None,
) -> Response:
    """Show the PIN screen, or go straight in when a session is already open."""
    target = app_session.safe_next(next)
    if app_session.current_customer(request, repository) is not None:
        return RedirectResponse(target, status_code=303)
    customer = app_session.enrolled_customer(repository, settings, u)
    if customer is None:
        return app_session.page(request, "message", NOT_ENROLLED, 404)
    return app_session.page(request, "login", {"customer": customer, "next": target})


@router.post("/app/login", response_class=HTMLResponse)
def sign_in(
    request: Request,
    fields: Annotated[dict[str, str], Depends(app_session.form_fields)],
    repository: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Check the PIN. A correct one opens a session and sets the cookie."""
    target = app_session.safe_next(fields.get("next"))
    customer = app_session.enrolled_customer(repository, settings, fields.get("u"))
    if customer is None:
        return app_session.page(request, "message", NOT_ENROLLED, 404)
    now = utc_now()
    result = app_session.try_pin(repository, customer, fields.get("pin", ""), now)
    audit.record(repository, "/app/login", "POST", customer["id"], f"app_pin_{result}")
    if result != "ok":
        error, status = ERRORS[result]
        context = {"customer": customer, "next": target, "error": error}
        return app_session.page(request, "login", context, status)
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        app_session.COOKIE,
        app_session.open_session(repository, customer, now),
        max_age=int(app_session.SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.public_base_url.startswith("https://"),
    )
    return response


@router.post("/app/logout")
def sign_out(
    request: Request, repository: Annotated[Repository, Depends(get_repository)]
) -> Response:
    """Close the session and forget the cookie."""
    token = request.cookies.get(app_session.COOKIE)
    if token:
        repository.update("app_sessions", {"token": token}, {"expires_at": utc_now().isoformat()})
    response = RedirectResponse("/app", status_code=303)
    response.delete_cookie(app_session.COOKIE)
    return response
