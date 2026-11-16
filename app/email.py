"""Outgoing email through the Resend HTTP API.

Sending is optional. Without `RESEND_API_KEY` nothing is sent and the caller
is told so, which keeps local runs and tests offline.
"""

import logging

import httpx

from app.config import Settings
from app.db import Row

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"


def mask_email(address: str) -> str:
    """Hide the mailbox name: `marta.rojas@example.com` becomes `m***@example.com`."""
    name, _, domain = address.partition("@")
    return f"{name[:1]}***@{domain}"


def proposal_email(product: Row, signing_url: str | None) -> str:
    """Write the email body: product details, plus the signing link when there is one."""
    html = (
        f"<p>{product['name']}: {product['coverage_summary']}</p>"
        f"<p>{product['monthly_premium']} {product['currency']} per month.</p>"
    )
    if signing_url:
        html += f'<p><a href="{signing_url}">Review and sign your proposal</a></p>'
    return html


def send_email(settings: Settings, to: str, subject: str, html: str) -> bool:
    """Send one email. Return True only if the provider accepted it."""
    if not settings.resend_api_key:
        return False
    try:
        response = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.email_from, "to": [to], "subject": subject, "html": html},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("email could not be sent")
        return False
    return True
