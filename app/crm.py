"""A small client for the CRM (Salesforce), where the insurance sale is mirrored.

The bank core is the record that counts. The CRM gets a copy, so the sales
team sees the funnel where it already works. Mirroring is optional: without
`SALESFORCE_INSTANCE_URL` nothing is sent, which keeps local runs and tests
offline. The app signs in as itself, with the OAuth client credentials flow.
"""

import logging
import time
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)
# A request to the CRM never holds up the answer to the caller for longer than this.
TIMEOUT_SECONDS = 8
TOKEN_LIFETIME_SECONDS = 20 * 60
# The access token is kept between requests while the process lives.
signed_in: dict[str, Any] = {}


class CrmError(Exception):
    """The CRM refused a request or could not be reached."""


def enabled(settings: Settings) -> bool:
    """Say whether a CRM is configured."""
    return bool(settings.salesforce_instance_url and settings.salesforce_client_id)


def instance(settings: Settings) -> str:
    """Return the address of the CRM, with `https://` and no trailing slash."""
    address = settings.salesforce_instance_url.strip().rstrip("/")
    return address if address.startswith("http") else f"https://{address}"


def access_token(settings: Settings) -> str:
    """Return a valid access token, signing in again when the kept one is old."""
    if signed_in.get("until", 0) > time.monotonic():
        return signed_in["token"]
    form = {
        "grant_type": "client_credentials",
        "client_id": settings.salesforce_client_id,
        "client_secret": settings.salesforce_client_secret,
    }
    address = f"{instance(settings)}/services/oauth2/token"
    response = httpx.request("POST", address, data=form, timeout=TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise CrmError(f"sign-in refused with status {response.status_code}")
    signed_in["token"] = response.json()["access_token"]
    signed_in["until"] = time.monotonic() + TOKEN_LIFETIME_SECONDS
    return signed_in["token"]


def call(settings: Settings, method: str, path: str, **request: Any) -> Any:
    """Send one request to the CRM's REST API and return the JSON answer, if any.

    `path` starts after the API version, for example `/sobjects/Contact`.
    """
    version = settings.salesforce_api_version
    version = version if version.startswith("v") else f"v{version}"
    address = f"{instance(settings)}/services/data/{version}{path}"
    try:
        headers = {"Authorization": f"Bearer {access_token(settings)}"}
        response = httpx.request(
            method, address, headers=headers, timeout=TIMEOUT_SECONDS, **request
        )
    except httpx.HTTPError as error:
        raise CrmError(f"{method} {path}: {type(error).__name__}") from error
    if response.status_code == 401:
        # The kept token was ended on the other side: forget it, the next call signs in again.
        signed_in.clear()
    if response.status_code >= 400:
        raise CrmError(f"{method} {path}: status {response.status_code} {response.text[:300]}")
    return response.json() if response.content else None


def query(settings: Settings, soql: str) -> list[dict]:
    """Run a query and return its records (the first page, up to 2000)."""
    return call(settings, "GET", "/query", params={"q": soql})["records"]


def upsert(settings: Settings, kind: str, key_field: str, key: str, fields: dict) -> dict:
    """Create or update the record whose external ID field has this value.

    Returns `{"id": ..., "created": True or False}`.
    """
    return call(settings, "PATCH", f"/sobjects/{kind}/{key_field}/{key}", json=fields)
