"""Outgoing email through the Resend HTTP API.

Sending is optional. Without `RESEND_API_KEY` nothing is sent and the caller
is told so, which keeps local runs and tests offline.
"""

import logging

import httpx

from app.config import Settings
from app.db import Row
from app.formatting import money

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"


def mask_email(address: str) -> str:
    """Hide the mailbox name: `marta.rojas@example.com` becomes `m***@example.com`."""
    name, _, domain = address.partition("@")
    return f"{name[:1]}***@{domain}"


def proposal_email(product: Row, signing_url: str | None) -> str:
    """Write the email body: product details, plus the signing link when there is one."""
    premium = money(product["monthly_premium"], product["currency"])
    html = (
        f"<p><strong>{product['name']}</strong></p>"
        f"<p>{product['coverage_summary']}</p>"
        f"<p>Prima mensual: {premium}.</p>"
    )
    if signing_url:
        html += (
            f'<p><a href="{signing_url}">Revisar y firmar la propuesta</a></p>'
            "<p>Nada queda contratado hasta que usted firme.</p>"
        )
    return html


def policy_email(product: Row, policy: Row, start: str) -> str:
    """Write the confirmation the customer keeps once the proposal is signed."""
    premium = money(product["monthly_premium"], product["currency"])
    return (
        f"<p>Su seguro <strong>{product['name']}</strong> quedó contratado.</p>"
        f"<p>Póliza: {policy['policy_number']}<br>"
        f"Vigente desde: {start}<br>"
        f"Prima mensual: {premium}</p>"
        f"<p>{product['coverage_summary']}</p>"
        "<p>Puede darlo de baja en cualquier momento desde la app.</p>"
    )


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
