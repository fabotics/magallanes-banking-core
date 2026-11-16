"""Identity verification: the gate in front of all customer data.

The customer gives a document number, the last four digits of a card and a
birth year. A match opens a session that lasts 15 minutes. Three failures for
the same document within 15 minutes lock verification for that document.
"""

import secrets
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app import audit
from app.clock import parse_time, utc_now
from app.db import Repository, Row, get_repository
from app.schemas import VerifyRequest, VerifyResponse

MAX_FAILED_ATTEMPTS = 3
ATTEMPT_WINDOW = timedelta(minutes=15)
SESSION_LIFETIME = timedelta(minutes=15)

router = APIRouter(tags=["identity"])


def normalize_document(value: str) -> str:
    """Keep only letters and digits, upper case: `31.415.926-k` becomes `31415926K`."""
    return "".join(character for character in value if character.isalnum()).upper()


def recent_failures(repository: Repository, document: str, now: datetime) -> int:
    """Count failed attempts for a document in the window, since its last success."""
    attempts = repository.select("verification_attempts", {"document_number": document})
    recent = [a for a in attempts if parse_time(a["created_at"]) > now - ATTEMPT_WINDOW]
    failures = 0
    for attempt in sorted(recent, key=lambda a: parse_time(a["created_at"])):
        failures = 0 if attempt["success"] else failures + 1
    return failures


def find_customer(repository: Repository, document: str, body: VerifyRequest) -> Row | None:
    """Return the customer only if document, card digits and birth year all match."""
    customers = repository.select("customers", {"document_number": document})
    if not customers:
        return None
    customer = customers[0]
    cards = repository.select("cards", {"customer_id": customer["id"]})
    card_matches = any(card["last4"] == body.card_last4.strip() for card in cards)
    year_matches = customer["birth_date"].startswith(f"{body.birth_year}-")
    return customer if card_matches and year_matches else None


@router.post("/identity/verify", response_model=VerifyResponse, response_model_exclude_none=True)
def verify_identity(
    body: VerifyRequest,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
) -> VerifyResponse:
    """Verify the customer and open a session. A failure never says which field was wrong."""
    now = utc_now()
    document = normalize_document(body.document_number)
    audit.note(request, conversation_id=body.conversation_id, document=audit.mask(document))

    failures = recent_failures(repository, document, now)
    if failures >= MAX_FAILED_ATTEMPTS:
        audit.note(request, outcome="locked")
        return VerifyResponse(verified=False, locked=True, attempts_remaining=0)

    customer = find_customer(repository, document, body)
    repository.insert(
        "verification_attempts",
        {
            "document_number": document,
            "success": customer is not None,
            "conversation_id": body.conversation_id,
            "created_at": now.isoformat(),
        },
    )
    if customer is None:
        failures += 1
        locked = failures >= MAX_FAILED_ATTEMPTS
        audit.note(request, outcome="locked" if locked else "failed")
        return VerifyResponse(
            verified=False, locked=locked, attempts_remaining=MAX_FAILED_ATTEMPTS - failures
        )

    token = secrets.token_urlsafe(32)
    repository.insert(
        "verification_sessions",
        {
            "token": token,
            "customer_id": customer["id"],
            "conversation_id": body.conversation_id,
            "created_at": now.isoformat(),
            "expires_at": (now + SESSION_LIFETIME).isoformat(),
        },
    )
    audit.note(request, customer_id=customer["id"], outcome="verified")
    return VerifyResponse(verified=True, session_token=token, first_name=customer["first_name"])
