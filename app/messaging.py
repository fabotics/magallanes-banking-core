"""Outgoing messages to the customer's messaging channel (Telegram).

Sending is optional. Without `TELEGRAM_BOT_TOKEN` nothing is sent and the
caller is told so, which keeps local runs and tests offline.
"""

import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

# The bot token is part of the request URL. The HTTP library logs URLs at
# INFO level, so its logger is kept at WARNING to keep the token out of logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(settings: Settings, chat_id: str, text: str) -> bool:
    """Send one text message. Return True only if Telegram accepted it."""
    if not settings.telegram_bot_token:
        return False
    try:
        response = httpx.post(
            TELEGRAM_URL.format(token=settings.telegram_bot_token),
            # Link previews are off: a preview would open the links in the message.
            json={
                "chat_id": chat_id,
                "text": text,
                "link_preview_options": {"is_disabled": True},
            },
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        # Only the error type is logged: the full error text contains the URL with the token.
        logger.warning("telegram message could not be sent: %s", type(error).__name__)
        return False
    return True
