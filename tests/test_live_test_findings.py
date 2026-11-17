"""What two real conversations got wrong, each pinned by a test.

One verified customer per conversation, days and hours ready-made on the
bank's clock, and a summary even when the customer hangs up.
"""

import pytest
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


def test_an_id_number_heard_with_noise_still_names_the_customer(
    client: TestClient, repository: InMemoryRepository
) -> None:
    # What speech recognition wrote for 35.628.194-2 in a real call.
    pushed = client.post(
        "/v1/identity/push", json={"customer_id": "35628194@, uh, -2"}, headers=API_KEY
    ).json()
    row = repository.select(confirmations.TABLE, {"id": pushed["request_id"]})[0]
    assert row["customer_id"] == seed_id("customer/daniel")
    said = {"document_number": "3, 35 628 194 dash 2", "card_last4": "5519", "birth_year": 1992}
    # A stray digit makes another number: the bank never guesses which digits were meant.
    assert (
        client.post("/v1/identity/verify", json=said, headers=API_KEY).json()["verified"] is False
    )
    said["document_number"] = "uh, 35.628.194 - 2, yes"
    assert client.post("/v1/identity/verify", json=said, headers=API_KEY).json()["verified"] is True
    # An ID with letters in it keeps them, and a final K is kept as the check digit.
    sofia = {"customer_id": "rogs900514mdfbrf04"}
    pushed = client.post("/v1/identity/push", json=sofia, headers=API_KEY).json()
    row = repository.select(confirmations.TABLE, {"id": pushed["request_id"]})[0]
    assert row["customer_id"] == seed_id("customer/sofia")


def test_the_bank_counts_the_checks_and_says_what_to_do_next(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    held: list[int] = []

    def no_waiting(read, settled, seconds):  # noqa: ANN001, ANN202
        held.append(seconds)
        return read()

    monkeypatch.setattr("app.waiting.until_settled", no_waiting)

    def check(request_id: str) -> dict:
        return client.get(f"/v1/identity/push/{request_id}?wait=10", headers=API_KEY).json()

    named = {"customer_id": "35.628.194-2", "conversation_id": TALK}
    first = client.post("/v1/identity/push", json=named, headers=API_KEY).json()["request_id"]
    assert check(first)["next_step"] == "check_again"
    second_check = check(first)
    assert second_check["next_step"] == "send_new_confirmation"
    assert "sending a new one" in second_check["instruction"]
    # After the cap the answer comes at once: the request is not held any more.
    assert check(first)["next_step"] == "send_new_confirmation" and held == [10, 10, 0]
    # The new confirmation gets one check, then the other way is offered.
    again = client.post("/v1/identity/push", json=named, headers=API_KEY).json()["request_id"]
    only_check = check(again)
    assert only_check["status"] == "pending" and only_check["next_step"] == "offer_other_way"
    assert "three spoken security questions" in only_check["instruction"]
    assert check(again)["next_step"] == "offer_other_way" and held == [10, 10, 0, 10, 0]


def test_an_approval_still_arrives_after_the_cap(
    client: TestClient, repository: InMemoryRepository
) -> None:
    named = {"customer_id": "35.628.194-2", "conversation_id": TALK}
    request_id = client.post("/v1/identity/push", json=named, headers=API_KEY).json()["request_id"]
    for _ in range(3):
        client.get(f"/v1/identity/push/{request_id}", headers=API_KEY)
    row = repository.select(confirmations.TABLE, {"id": request_id})[0]
    confirmations.decide(repository, row, True, utc_now())
    answer = client.get(f"/v1/identity/push/{request_id}", headers=API_KEY).json()
    assert answer["status"] == "approved" and "next_step" not in answer


def review(client: TestClient, session: dict, outcome: str) -> dict:
    return client.post("/v1/cards/review", json={"outcome": outcome}, headers=session).json()


def test_the_bank_decides_where_the_conversation_goes_after_the_answer(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    # Recognised and eligible: the offer always comes next.
    said = review(client, marta, "recognised")
    assert said["review_route"] == "offer" and "offer comes next" in said["next_step"]
    assert review(client, marta, "not_recognised")["review_route"] == "fraud"
    assert review(client, marta, "wants_person")["review_route"] == "handoff"
    unsure = client.post("/v1/cards/review", json={"outcome": "unsure"}, headers=marta)
    assert unsure.status_code == 422
    no_session = client.post("/v1/cards/review", json={"outcome": "recognised"}, headers=API_KEY)
    assert no_session.status_code == 401
    outcomes = [row["outcome"] for row in repository.select("audit_log")]
    assert "charges_recognised" in outcomes and "charges_not_recognised" in outcomes


@pytest.mark.parametrize(
    ("document", "why"),
    [
        ("33.161.803-9", "already holds the card cover"),
        ("34.141.421-0", "her only card is blocked"),
        ("90000017", "the catalog is not sold in her country"),
    ],
)
def test_no_offer_follows_when_the_bank_has_nothing_to_offer(
    client: TestClient, repository: InMemoryRepository, document: str, why: str
) -> None:
    session = verify_in_app(client, repository, customer_id=document)
    assert review(client, session, "recognised")["review_route"] == "wrap_up", why


def test_a_vulnerable_customer_goes_to_a_person_right_after_verification(
    client: TestClient, repository: InMemoryRepository
) -> None:
    pushed = client.post(
        "/v1/identity/push", json={"customer_id": "30.577.215-1"}, headers=API_KEY
    ).json()
    row = repository.select(confirmations.TABLE, {"id": pushed["request_id"]})[0]
    confirmations.decide(repository, row, True, utc_now())
    answer = client.get(f"/v1/identity/push/{pushed['request_id']}", headers=API_KEY).json()
    assert answer["review_route"] == "handoff"


def test_a_case_opened_too_early_can_be_taken_back(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    charges = client.get("/v1/cards/transactions", headers=marta).json()["transactions"]
    disputed = [row["id"] for row in charges if row["merchant_tax_id"]]
    case = {"type": "fraud", "category": "service", "summary": "No reconoce cargos.",
            "transaction_ids": disputed}  # fmt: skip
    number = client.post("/v1/cases", json=case, headers=marta).json()["case_number"]
    assert all(repository.select("transactions", {"id": i})[0]["is_disputed"] for i in disputed)

    taken_back = client.post(f"/v1/cases/{number}/withdraw", headers=marta).json()
    assert taken_back == {"case_number": number, "status": "withdrawn"}
    stored = repository.select("cases", {"case_number": number})[0]
    assert stored["status"] == "closed" and "Retirado por el cliente" in stored["summary"]
    assert not any(repository.select("transactions", {"id": i})[0]["is_disputed"] for i in disputed)
    # Asking again is harmless, and nobody can take back another customer's case.
    assert client.post(f"/v1/cases/{number}/withdraw", headers=marta).status_code == 200
    assert stored["summary"].count("Retirado") == 1
    emma = verify_in_app(client, repository, customer_id="35.897.932-7")
    assert client.post(f"/v1/cases/{number}/withdraw", headers=emma).status_code == 404
