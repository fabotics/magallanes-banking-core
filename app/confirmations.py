"""App confirmations: the customer proves who they are by approving a request in the bank's app.

A caller on the phone can read out data that someone else also knows. An
approval inside the bank's own app, behind the customer's PIN, is a stronger
proof, so it is the first choice and the spoken check is the fallback.

A confirmation is pending for 90 seconds. The app shows a six digit code that
also travels in the notification, so the customer can see both belong to the
same request. The code is never returned through the API: the agent on the
call must not be able to read it aloud.
"""

import secrets
import uuid
from datetime import datetime, timedelta

from app.app_session import app_link
from app.clock import parse_time
from app.config import Settings
from app.db import Repository, Row
from app.messaging import send_telegram

CONFIRMATION_LIFETIME = timedelta(seconds=90)
TABLE = "identity_confirmations"


def normalize_phone(value: str) -> str:
    """Keep the digits of a phone number, with a leading plus: `+56955501426`."""
    return "+" + "".join(character for character in value if character.isdigit())


def named_customer(
    repository: Repository, reference: str | None, phone: str | None, document: str
) -> tuple[Row | None, str]:
    """Return the customer a request names, and the key its failed attempts count under.

    A known customer always counts under their document number, so the lockout
    is one and the same whichever way they were named. An unknown reference or
    phone counts under itself.
    """
    if reference:
        try:
            filters, key = {"id": str(uuid.UUID(reference))}, f"ref:{reference[:40]}"
        except ValueError:
            return None, f"ref:{reference[:40]}"
    elif phone:
        filters, key = {"phone": normalize_phone(phone)}, f"phone:{normalize_phone(phone)}"
    else:
        filters, key = {"document_number": document}, document
    customers = repository.select("customers", filters)
    return (customers[0], customers[0]["document_number"]) if customers else (None, key)


def create(
    repository: Repository,
    document: str,
    customer: Row | None,
    conversation_id: str | None,
    now: datetime,
) -> Row:
    """Store a pending confirmation. An unknown document gets one too, which simply expires."""
    return repository.insert(
        TABLE,
        {
            "customer_id": customer["id"] if customer else None,
            "document_number": document,
            "code": f"{secrets.randbelow(1_000_000):06d}",
            "status": "pending",
            "conversation_id": conversation_id,
            "session_token": None,
            "created_at": now.isoformat(),
            "expires_at": (now + CONFIRMATION_LIFETIME).isoformat(),
        },
    )


def current_status(confirmation: Row, now: datetime) -> str:
    """Return pending, approved, denied or expired. Expiry is computed, not stored."""
    if confirmation["status"] == "pending" and parse_time(confirmation["expires_at"]) <= now:
        return "expired"
    return confirmation["status"]


def notify(settings: Settings, customer: Row, confirmation: Row) -> bool:
    """Tell the customer, on their messaging channel, that a confirmation is waiting."""
    if not customer["telegram_chat_id"]:
        return False
    link = app_link(settings, customer, f"/app/confirmations/{confirmation['id']}")
    text = (
        "Banco Magallanes\n"
        "Alguien en una llamada con Banco Magallanes pide confirmar su identidad. "
        f"Código {confirmation['code']}\n\n"
        f"Abra la app para aprobar o rechazar: {link}\n"
        "Si usted no está en una llamada con el banco, rechace la solicitud."
    )
    return send_telegram(settings, customer["telegram_chat_id"], text)


def decide(repository: Repository, confirmation: Row, approved: bool, now: datetime) -> Row:
    """Record the customer's answer. Only a pending request can be answered, and only once.

    The answer also counts as a verification attempt, so a denied request
    moves the document towards the same lockout as a failed spoken check.
    """
    if current_status(confirmation, now) != "pending":
        return confirmation
    repository.insert(
        "verification_attempts",
        {
            "document_number": confirmation["document_number"],
            "success": approved,
            "conversation_id": confirmation["conversation_id"],
            "created_at": now.isoformat(),
        },
    )
    values = {"status": "approved" if approved else "denied", "decided_at": now.isoformat()}
    return repository.update(TABLE, {"id": confirmation["id"]}, values)[0]
