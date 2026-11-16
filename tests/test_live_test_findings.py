"""What two real conversations got wrong, each pinned by a test.

One verified customer per conversation, days and hours ready-made on the
bank's clock, and a summary even when the customer hangs up.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import confirmations
from app.clock import utc_now
from seed.helpers import app_pin, seed_id
from tests.conftest import API_KEY, PIN_SECRET
from tests.fake_db import InMemoryRepository

TALK = "conversation-1"
EMMA_ID, MARTA_ID = seed_id("customer/emma"), seed_id("customer/marta")


def verify_in_app(client: TestClient, repository: InMemoryRepository, **named: str) -> dict:
    """Ask for a confirmation, approve it as the customer would, and return the session header."""
    pushed = client.post(
        "/v1/identity/push", json={**named, "conversation_id": TALK}, headers=API_KEY
    ).json()
    row = repository.select(confirmations.TABLE, {"id": pushed["request_id"]})[0]
    confirmations.decide(repository, row, True, utc_now())
    result = client.get(f"/v1/identity/push/{pushed['request_id']}", headers=API_KEY).json()
    return {**API_KEY, "X-Session-Token": result["session_token"]}


def home_of(client: TestClient, key: str) -> str:
    """Sign in to the app as a seed customer and return their home page."""
    client.post("/app/logout")
    client.post(
        "/app/login", data={"u": seed_id(f"customer/{key}"), "pin": app_pin(PIN_SECRET, key)}
    )
    return client.get("/app/home").text


def test_a_second_verification_replaces_the_first_and_the_proposal_follows_it(
    client: TestClient, repository: InMemoryRepository
) -> None:
    # Verified by the phone the call comes from, then by the ID number of another customer.
    emma = verify_in_app(client, repository, phone="+56955503589")
    marta = verify_in_app(client, repository, customer_id="31.415.926-8")
    assert client.get("/v1/customers/me", headers=emma).status_code == 401
    assert client.get("/v1/customers/me", headers=marta).json()["first_name"] == "Marta"

    offer = {"product_code": "CARD_FRAUD", "customer_response": "info_requested"}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=marta).json()["offer_id"]
    body = {"offer_id": offer_id}
    sent = client.post("/v1/insurance/proposals", json=body, headers=marta).json()
    row = repository.select("proposals", {"proposal_number": sent["proposal_number"]})[0]
    assert row["customer_id"] == MARTA_ID
    link = f"/app/proposals/{sent['proposal_number']}"
    assert link in home_of(client, "marta") and link not in home_of(client, "emma")


def test_another_conversation_keeps_its_own_session(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    verify_in_app(client, repository, customer_id="35.897.932-7")
    assert client.get("/v1/customers/me", headers=marta).status_code == 200


def test_charges_carry_the_day_and_hour_at_the_bank_and_are_added_up(
    client: TestClient, marta: dict
) -> None:
    answer = client.get("/v1/cards/transactions", headers=marta).json()
    assert answer["timezone"] == "America/Santiago"
    (evening,) = answer["repeated_charges"]
    assert evening["count"] == 4 and evening["total"] == 34900
    assert evening["first_time"] == "21:52" and evening["last_time"] == "23:58"
    (day,), (posted,) = evening["purchased_on"], evening["posted_on"]
    assert day.startswith("Saturday ") and posted.startswith("Monday ")
    rounds = [row for row in answer["transactions"] if row["merchant_tax_id"]]
    assert {row["purchased_on"] for row in rounds} == {day}
    assert all(row["transaction_at"].endswith(("-03:00", "-04:00")) for row in rounds)


def ended(client: TestClient, body: dict) -> dict:
    return client.post("/v1/notifications/conversation-ended", json=body, headers=API_KEY).json()


def test_a_customer_who_hangs_up_still_gets_what_the_bank_recorded(
    client: TestClient, repository: InMemoryRepository, with_bot: None, telegram: list[dict]
) -> None:
    marta = verify_in_app(client, repository, customer_id="31.415.926-8")
    case = {
        "type": "complaint",
        "category": "service",
        "summary": "Reclamo",
        "conversation_id": TALK,
    }
    number = client.post("/v1/cases", json=case, headers=marta).json()["case_number"]
    offer = {"product_code": "CARD_FRAUD", "customer_response": "accepted"}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=marta).json()["offer_id"]
    sent = client.post("/v1/insurance/proposals", json={"offer_id": offer_id}, headers=marta).json()
    before = len(telegram)
    # The notice may carry the ID at the top or inside `data`.
    assert ended(client, {"data": {"conversation_id": TALK}}) == {"sent": True}
    text = telegram[-1]["json"]["text"]
    assert number in text and sent["proposal_number"] in text and len(telegram) == before + 1
    assert ended(client, {"conversation_id": TALK}) == {"sent": False, "reason": "already_sent"}


def test_no_closing_summary_without_a_verified_customer_or_after_the_agents_own(
    app: FastAPI,
    client: TestClient,
    repository: InMemoryRepository,
    with_bot: None,
    telegram: list[dict],
) -> None:
    assert ended(client, {"conversation_id": "nobody"}) == {"sent": False, "reason": "not_verified"}
    assert ended(client, {}) == {"sent": False, "reason": "not_verified"}
    marta = verify_in_app(client, repository, customer_id="31.415.926-8")
    nothing = {"sent": False, "reason": "nothing_recorded"}
    assert ended(client, {"conversation_id": TALK}) == nothing
    client.post("/v1/notifications/call-summary", json={"summary": "Listo."}, headers=marta)
    assert ended(client, {"conversation_id": TALK}) == {"sent": False, "reason": "already_sent"}
