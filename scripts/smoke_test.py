"""Walk the golden path against a running instance and print every status code.

Usage:
    python scripts/smoke_test.py --base-url http://localhost:8000

Reads BANK_API_KEY from the environment or `.env`. It uses the seeded demo
customer and exits with code 1 if any step answers with an unexpected status.
It writes a few rows (a confirmation request, an offer, a proposal, a case, audit rows),
sends the demo customer the matching messages, signs nothing and blocks no card.
It also proves the waiting path: a status request is held while the confirmation is
pending, and answers at once when the customer approves in the app during the wait.
The last step connects to `/mcp` with the MCP SDK client and calls the lookup tool.
"""

import argparse
import asyncio
import sys
import threading
import time
from pathlib import Path

import httpx

# Make `app` importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from scripts.mcp_check import check as check_mcp  # noqa: E402
from seed.helpers import app_pin, seed_id  # noqa: E402

DEMO_CUSTOMER = {"document_number": "31.415.926-8", "card_last4": "4821", "birth_year": 1986}
CONVERSATION = "smoke-test"


class Smoke:
    """Calls the API and keeps count of the steps that did not answer as expected."""

    def __init__(self, base_url: str, api_key: str) -> None:
        headers = {"X-API-Key": api_key}
        self.client = httpx.Client(base_url=base_url, headers=headers, timeout=30)
        self.failures = 0

    def step(self, name: str, expected: int, method: str, path: str, **kwargs: object) -> dict:
        """Run one request, print its status, and return the JSON body if there is one."""
        response = self.client.request(method, path, **kwargs)
        verdict = "ok" if response.status_code == expected else f"FAIL, expected {expected}"
        print(f"{name:34} {method:4} {path:36.36} {response.status_code}  {verdict}")
        if response.status_code != expected:
            self.failures += 1
        is_json = response.headers.get("content-type", "").startswith("application/json")
        return response.json() if is_json else {}


def approve_in_app(base_url: str, request_id: str, pin: str, after: float) -> None:
    """Sign in to the app as the demo customer and approve the request, after a pause."""
    time.sleep(after)
    with httpx.Client(base_url=base_url, timeout=30) as app:
        app.post("/app/login", data={"u": seed_id("customer/marta"), "pin": pin})
        app.post(f"/app/confirmations/{request_id}", data={"decision": "approve"})


def waiting_path(smoke: Smoke, request_id: str) -> None:
    """Hold a status request while pending, then let an approval end the wait early."""
    path = f"/v1/identity/push/{request_id}"
    started = time.monotonic()
    held = smoke.step("wait is held while pending", 200, "GET", path, params={"wait": 3})
    took = time.monotonic() - started
    print(f"{'':34} status: {held.get('status')} after {took:.1f} s, then {held.get('next_step')}")
    pin_secret = get_settings().app_pin_secret
    if not pin_secret:
        return print(f"{'':34} no APP_PIN_SECRET: the approval during a wait is skipped")
    base_url = str(smoke.client.base_url)
    approval = (base_url, request_id, app_pin(pin_secret, "marta"), 2.0)
    threading.Thread(target=approve_in_app, args=approval).start()
    started = time.monotonic()
    answer = smoke.step("approval ends the wait", 200, "GET", path, params={"wait": 15})
    took = time.monotonic() - started
    print(f"{'':34} status: {answer.get('status')} after {took:.1f} s of a 15 s wait")
    if answer.get("status") != "approved" or took > 12:
        smoke.failures += 1


def run(smoke: Smoke) -> None:
    """The golden path: verify, read, check eligibility, record an offer, send details."""
    smoke.step("health", 200, "GET", "/health")
    smoke.step("no session is refused", 401, "GET", "/v1/accounts/balance")
    pushed = smoke.step(
        "confirmation request to the app", 200, "POST", "/v1/identity/push",
        json={"customer_id": DEMO_CUSTOMER["document_number"], "conversation_id": CONVERSATION},
    )  # fmt: skip
    waiting_path(smoke, pushed.get("request_id", ""))
    verified = smoke.step(
        "verify identity", 200, "POST", "/v1/identity/verify",
        json={**DEMO_CUSTOMER, "conversation_id": CONVERSATION},
    )  # fmt: skip
    session = {"X-Session-Token": verified.get("session_token", "")}

    smoke.step("profile", 200, "GET", "/v1/customers/me", headers=session)
    smoke.step("balances", 200, "GET", "/v1/accounts/balance", headers=session)
    smoke.step("transactions", 200, "GET", "/v1/cards/transactions", headers=session)
    smoke.step("merchant behind a tax ID", 200, "GET", "/v1/registry/merchants/66871234-7")
    smoke.step("eligibility", 200, "GET", "/v1/insurance/eligibility", headers=session)
    offer = smoke.step(
        "offer: accepted", 200, "POST", "/v1/insurance/offers", headers=session,
        json={"product_code": "CARD_FRAUD", "customer_response": "accepted"},
    )  # fmt: skip
    proposal = smoke.step(
        "proposal with a signing link", 200, "POST", "/v1/insurance/proposals", headers=session,
        json={"offer_id": offer.get("offer_id", "")},
    )  # fmt: skip
    print(f"{'':34} email: {proposal.get('email_sent')}, chat: {proposal.get('message_sent')}")
    signed = smoke.step(
        "proposal is not signed yet", 200, "GET",
        f"/v1/insurance/proposals/{proposal.get('proposal_number')}", headers=session,
    )  # fmt: skip
    print(f"{'':34} status: {signed.get('status')}")
    smoke.step(
        "handoff without a session", 200, "POST", "/v1/cases",
        json={"type": "handoff", "summary": "Smoke test", "conversation_id": CONVERSATION},
    )  # fmt: skip
    summary = smoke.step(
        "call summary to messaging", 200, "POST", "/v1/notifications/call-summary",
        headers=session, json={"summary": "Smoke test: the call summary channel works."},
    )  # fmt: skip
    print(f"{'':34} sent: {summary.get('sent')}, channel: {summary.get('channel')}")
    smoke.step("unknown signing link", 404, "GET", "/sign/not-a-real-token")


def mcp_tool_works(base_url: str, api_key: str) -> bool:
    """Connect to `/mcp` with the MCP client, list the tools and call the lookup."""
    try:
        return asyncio.run(check_mcp(base_url, api_key))
    except Exception as error:
        print(f"mcp: FAIL, {type(error).__name__}: {error}")
        return False


def main() -> None:
    """Parse the arguments, run the steps and set the exit code."""
    parser = argparse.ArgumentParser(description="Smoke test for a running banking core.")
    parser.add_argument("--base-url", required=True, help="for example http://localhost:8000")
    args = parser.parse_args()

    api_key = get_settings().bank_api_key
    if not api_key:
        sys.exit("BANK_API_KEY is not set in the environment or in .env")
    base_url = args.base_url.rstrip("/")
    smoke = Smoke(base_url, api_key)
    run(smoke)
    failures = smoke.failures + (0 if mcp_tool_works(base_url, api_key) else 1)
    print("all steps ok" if failures == 0 else f"{failures} step(s) failed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
