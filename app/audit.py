"""Audit trail: one `audit_log` row for every `/v1` and `/mcp` call.

Endpoints describe what happened with `note(...)`. The middleware writes the
row after the response is ready. Secrets, session tokens and full document
numbers are never passed to `note`, and the query string is never recorded.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool

from app import db
from app.clock import utc_now
from app.config import get_settings

logger = logging.getLogger(__name__)

# Paths that need the API key. Calls to them are recorded.
AUDITED_PREFIXES = ("/v1", "/mcp")


def note(
    request: Request,
    customer_id: str | None = None,
    conversation_id: str | None = None,
    outcome: str | None = None,
    **detail: Any,
) -> None:
    """Remember facts about this call for its audit row. Later calls add to earlier ones."""
    audit = getattr(request.state, "audit", None)
    if audit is None:
        audit = {"detail": {}}
        request.state.audit = audit
    if customer_id:
        audit["customer_id"] = customer_id
    if conversation_id:
        audit["conversation_id"] = conversation_id
    if outcome:
        audit["outcome"] = outcome
    audit["detail"].update(detail)


def mask(value: str) -> str:
    """Hide all but the last four characters, for example `*****9268`."""
    return "*" * max(len(value) - 4, 0) + value[-4:]


def default_outcome(status_code: int) -> str:
    """Name the result of a call from its HTTP status when the endpoint did not."""
    if status_code < 400:
        return "ok"
    if status_code in (401, 403):
        return "denied"
    return "error"


def build_row(request: Request, status_code: int) -> db.Row:
    """Assemble the audit row from the request, the status and the endpoint's notes."""
    audit = getattr(request.state, "audit", {"detail": {}})
    return {
        "at": utc_now().isoformat(),
        "endpoint": request.url.path,
        "method": request.method,
        "customer_id": audit.get("customer_id"),
        "conversation_id": audit.get("conversation_id"),
        "outcome": audit.get("outcome") or default_outcome(status_code),
        "detail": {"status_code": status_code, **audit["detail"]},
    }


async def audit_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Run the request, then record it. A failed audit write never breaks the response."""
    response = await call_next(request)
    if request.url.path.startswith(AUDITED_PREFIXES):
        row = build_row(request, response.status_code)
        try:
            repository = db.repository_for(request.app, get_settings())
            # The repository is blocking, so it runs in a worker thread.
            await run_in_threadpool(repository.insert, "audit_log", row)
        except Exception:
            logger.exception("audit write failed for %s", request.url.path)
    return response
