"""Who may call the API, and on behalf of which customer.

Two layers. Every `/v1` route requires the `X-API-Key` header, so only known
callers reach the bank core. Customer endpoints also require a session token
issued by identity verification, so no account data leaves before the
customer has proven who they are.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Header, Query, Request, Security
from fastapi.security import APIKeyHeader

from app import audit
from app.clock import parse_time, utc_now
from app.config import Settings, get_settings
from app.db import Repository, Row, get_repository
from app.errors import ApiError

# Declaring the header as a security scheme gives `/docs` its Authorize button. The scheme
# only reads the header: `require_api_key` decides, so the error keeps the API's own shape.
api_key_header = APIKeyHeader(
    name="X-API-Key", auto_error=False, description="The key of a known caller."
)


def api_key_matches(settings: Settings, provided: str | None) -> bool:
    """Compare a key with the configured one.

    If no key is configured the check fails closed: nothing gets through.
    `secrets.compare_digest` compares in constant time, so the response time
    does not reveal how many characters of a guess were right.
    """
    expected = settings.bank_api_key
    if not expected or not provided:
        return False
    return secrets.compare_digest(provided.encode(), expected.encode())


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Security(api_key_header)] = None,
) -> None:
    """Reject the request with HTTP 401 unless `X-API-Key` matches the configured key."""
    if not api_key_matches(settings, x_api_key):
        raise ApiError(401, "invalid_api_key", "Missing or invalid X-API-Key header.")


def require_api_key_or_bearer(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Like `require_api_key`, but also accepts the key as `Authorization: Bearer <key>`.

    Some MCP clients only offer a bearer token field.
    """
    scheme, _, token = (authorization or "").partition(" ")
    bearer = token.strip() if scheme.lower() == "bearer" else None
    if not api_key_matches(settings, x_api_key or bearer):
        raise ApiError(401, "invalid_api_key", "Missing or invalid API key.")


def find_session(repository: Repository, token: str | None) -> Row | None:
    """Return the session for this token if it exists and has not expired."""
    if not token:
        return None
    sessions = repository.select("verification_sessions", {"token": token})
    if not sessions or parse_time(sessions[0]["expires_at"]) <= utc_now():
        return None
    return sessions[0]


def require_session(request: Request, repository: Repository, token: str | None) -> Row:
    """Return the valid session for this token, or answer HTTP 401.

    Also tells the audit trail which customer and conversation the call is for.
    """
    session = find_session(repository, token)
    if session is None:
        raise ApiError(
            401, "identity_not_verified", "Verify the customer's identity before this request."
        )
    audit.note(
        request,
        customer_id=session["customer_id"],
        conversation_id=session["conversation_id"],
    )
    return session


def session_from_request(
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
    x_session_token: Annotated[
        str | None, Header(description="Session token from identity verification. Preferred.")
    ] = None,
    session_token: Annotated[
        str | None,
        Query(description="Same token as a query parameter, if headers are not an option."),
    ] = None,
) -> Row:
    """Dependency for read endpoints: take the token from the header, else from the query."""
    return require_session(request, repository, x_session_token or session_token)
