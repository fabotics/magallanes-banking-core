"""The signed-in state of the bank's app: which customer, the PIN check, the session cookie.

The app is a set of web pages that stand in for a bank's phone app. A phone
app is enrolled to one customer, so the link names the customer and the PIN
proves it is them. Three wrong PINs lock the app for one minute.
"""

import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import i18n
from app.clock import parse_time, utc_now
from app.config import Settings
from app.db import Repository, Row
from app.pins import pin_matches

COOKIE = "mg_app"
SESSION_LIFETIME = timedelta(minutes=10)
MAX_WRONG_PINS = 3
LOCK_TIME = timedelta(minutes=1)
HOME = "/app/home"

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def page(
    request: Request,
    name: str,
    context: dict[str, Any],
    status: int = 200,
    switch_to: tuple[str, dict[str, str]] | None = None,
) -> HTMLResponse:
    """Render an app page in the visitor's language.

    Pages hold customer data, so they are never cached or framed. `switch_to`
    is the address and parameters the language links point to, for a page that
    answers a form.
    """
    language = context.get("lang") or i18n.pick_language(request)
    context = {
        "lang": language,
        "t": i18n.TEXTS[language],
        "languages": i18n.switch_links(request, *(switch_to or ())),
        **context,
    }
    response = templates.TemplateResponse(request, f"app/{name}.html", context, status)
    i18n.remember(request, response)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def message(
    request: Request, title: str, text: str, tone: str = "muted", status: int = 200, **extra: Any
) -> HTMLResponse:
    """Render the one-message page for results and dead ends.

    `title` and `text` are keys of the text tables, so the page comes out in
    the visitor's language.
    """
    words = i18n.TEXTS[i18n.pick_language(request)]
    context = {"title": words[title], "text": words[text], "tone": tone, **extra}
    context.setdefault("signed_in", True)
    return page(request, "message", context, status)


async def form_fields(request: Request) -> dict[str, str]:
    """Read a posted HTML form into a dictionary, keeping the first value of each field."""
    body = (await request.body()).decode()
    return {name: values[0] for name, values in parse_qs(body).items()}


def safe_next(target: str | None) -> str:
    """Only ever redirect inside the app, whatever the link says."""
    if target and target.startswith("/app/") and "//" not in target and "\\" not in target:
        return target
    return HOME


def to_login(request: Request) -> RedirectResponse:
    """Send a visitor without a session to the PIN screen, and back here afterwards."""
    response = RedirectResponse(f"/app?next={quote(request.url.path)}", status_code=303)
    i18n.remember(request, response)
    return response


def app_link(settings: Settings, customer: Row, path: str, language: str | None = None) -> str:
    """Build a link that opens this customer's app on a page, through the PIN screen.

    With a language, the link carries it, so the app opens in that language.
    """
    base = settings.public_base_url.rstrip("/")
    link = f"{base}/app?u={customer['id']}&next={quote(path)}"
    return f"{link}&lang={language}" if language else link


def enrolled_customer(
    repository: Repository, settings: Settings, customer_id: str | None
) -> Row | None:
    """Return the customer this app belongs to: named in the link, else the demo customer."""
    if customer_id:
        try:
            filters = {"id": str(uuid.UUID(customer_id))}
        except ValueError:
            return None
    else:
        filters = {"document_number": settings.demo_app_document}
    customers = repository.select("customers", filters)
    return customers[0] if customers else None


def try_pin(repository: Repository, customer: Row, pin: str, now: datetime) -> str:
    """Check a PIN and keep count of wrong ones. Return ok, wrong or locked."""
    locked_until = customer["app_locked_until"]
    if locked_until and parse_time(locked_until) > now:
        return "locked"
    if pin_matches(pin, customer["id"], customer["app_pin_hash"]):
        values = {"app_failed_pins": 0, "app_locked_until": None}
        repository.update("customers", {"id": customer["id"]}, values)
        return "ok"
    failures = customer["app_failed_pins"] + 1
    if failures >= MAX_WRONG_PINS:
        values = {"app_failed_pins": 0, "app_locked_until": (now + LOCK_TIME).isoformat()}
        repository.update("customers", {"id": customer["id"]}, values)
        return "locked"
    repository.update("customers", {"id": customer["id"]}, {"app_failed_pins": failures})
    return "wrong"


def open_session(repository: Repository, customer: Row, now: datetime) -> str:
    """Open a ten minute app session and return its token, which goes into the cookie."""
    token = secrets.token_urlsafe(32)
    repository.insert(
        "app_sessions",
        {
            "token": token,
            "customer_id": customer["id"],
            "created_at": now.isoformat(),
            "expires_at": (now + SESSION_LIFETIME).isoformat(),
        },
    )
    return token


def current_customer(request: Request, repository: Repository) -> Row | None:
    """Return the signed-in customer, or None when there is no valid session cookie."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    sessions = repository.select("app_sessions", {"token": token})
    if not sessions or parse_time(sessions[0]["expires_at"]) <= utc_now():
        return None
    return repository.select("customers", {"id": sessions[0]["customer_id"]})[0]
