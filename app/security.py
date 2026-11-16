"""Who may call the API.

Every `/v1` route requires the `X-API-Key` header, so only known callers reach
the bank core. The session check for customer endpoints is added with the
identity slice.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Header

from app.config import Settings, get_settings
from app.errors import ApiError


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Reject the request with HTTP 401 unless `X-API-Key` matches the configured key.

    If no key is configured the check fails closed: nothing gets through.
    `secrets.compare_digest` compares in constant time, so the response time
    does not reveal how many characters of a guess were right.
    """
    expected = settings.bank_api_key
    provided = x_api_key or ""
    if not expected or not secrets.compare_digest(provided.encode(), expected.encode()):
        raise ApiError(401, "invalid_api_key", "Missing or invalid X-API-Key header.")
