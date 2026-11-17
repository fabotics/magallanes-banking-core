"""Run a whole sale and check, in the CRM itself, that each step arrived.

Usage:
    python scripts/crm_check.py           run, check, then delete the test sale
    python scripts/crm_check.py --keep    leave the sale in the CRM

The bank runs here in memory, on seed data, so no database is touched. Only
the CRM is real. The main demo customer is verified, hears the offer, gets
the proposal and signs it in the app. After each step the Opportunity is read
back from the CRM: its stages must be Offered, Proposal Sent, Signed, and
after the signature it must be the first row of the list view.
"""

import argparse
import sys
from pathlib import Path

from fastapi.testclient import TestClient

# Make `app` importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import crm  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from seed.data import build_seed  # noqa: E402
from seed.helpers import app_pin, seed_id  # noqa: E402
from tests.fake_db import InMemoryRepository  # noqa: E402

PIN_SECRET = "crm-check"
DANIEL = {"document_number": "35.628.194-2", "card_last4": "5519", "birth_year": 1992}
SIGNATURE = {
    **{f"initial_{page}": "yes" for page in range(1, 5)},
    "signature_name": "Daniel Keller",
    "accept": "yes",
}
EXPECTED = ["Offered", "Proposal Sent", "Signed"]


def stage_in_crm(settings: Settings, offer_id: str) -> str:
    """Read the stage of the offer's Opportunity from the CRM."""
    path = f"/sobjects/Opportunity/Offer_Reference__c/{offer_id}"
    return crm.call(settings, "GET", path, params={"fields": "StageName"})["StageName"]


def top_of_the_view(settings: Settings) -> str:
    """Return the name of the first row of the list view, as the CRM orders it."""
    path = "/ui-api/list-records/Opportunity/Voice_agent_funnel"
    rows = crm.call(settings, "GET", path, params={"pageSize": 1})["records"]
    return rows[0]["fields"]["Name"]["value"]


def run(settings: Settings, keep: bool) -> bool:
    """Walk the sale and return whether the CRM showed every step."""
    repository = InMemoryRepository(build_seed(pin_secret=PIN_SECRET))
    app = create_app(repository)
    quiet = settings.model_copy(
        update={"bank_api_key": "check", "telegram_bot_token": "", "resend_api_key": "",
                "app_pin_secret": PIN_SECRET, "transactions_delay_seconds": 0}
    )  # fmt: skip
    app.dependency_overrides[get_settings] = lambda: quiet
    client = TestClient(app)
    key = {"X-API-Key": "check"}

    token = client.post("/v1/identity/verify", json=DANIEL, headers=key).json()["session_token"]
    session = {**key, "X-Session-Token": token}
    offer = {"product_code": "CARD_FRAUD", "outcome": "sent"}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=session).json()["offer_id"]
    seen = [stage_in_crm(settings, offer_id)]
    body = {"offer_id": offer_id}
    number = client.post("/v1/insurance/proposals", json=body, headers=session).json()
    seen.append(stage_in_crm(settings, offer_id))
    daniel = seed_id("customer/daniel")
    client.post("/app/login", data={"u": daniel, "pin": app_pin(PIN_SECRET, "daniel")})
    client.post(f"/app/proposals/{number['proposal_number']}", data=SIGNATURE)
    seen.append(stage_in_crm(settings, offer_id))
    first = top_of_the_view(settings)
    contacts = crm.query(
        settings, f"SELECT Name FROM Contact WHERE Customer_Reference__c = '{daniel}'"
    )

    print(f"stages in the CRM:      {seen}")
    print(f"first row of the view:  {first}")
    print(f"contact:                {[row['Name'] for row in contacts]}")
    if not keep:
        for kind in ("Opportunity", "Lead"):
            crm.call(settings, "DELETE", f"/sobjects/{kind}/Offer_Reference__c/{offer_id}")
        print("the test sale was deleted from the CRM, the contact stays")
    return seen == EXPECTED and first.startswith("Daniel Keller") and len(contacts) == 1


def main() -> None:
    """Parse the arguments, run the check and set the exit code."""
    parser = argparse.ArgumentParser(description="Check the CRM mirror with one whole sale.")
    parser.add_argument("--keep", action="store_true", help="leave the test sale in the CRM")
    args = parser.parse_args()
    settings = get_settings()
    if not crm.enabled(settings):
        sys.exit("SALESFORCE_INSTANCE_URL and SALESFORCE_CLIENT_ID are not set.")
    ok = run(settings, args.keep)
    print("all steps arrived" if ok else "FAIL: the CRM does not show the sale as expected")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
