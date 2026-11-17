"""Naming the customer by channel, and holding a status request until the answer comes."""

import pytest
from fastapi.testclient import TestClient

from app import confirmations, waiting
from app.clock import utc_now
from seed.helpers import seed_id
from tests.conftest import API_KEY
from tests.fake_db import InMemoryRepository

URL = "/v1/identity/push"
MARTA_ID = seed_id("customer/marta")


def push(client: TestClient, **named: str) -> dict:
    response = client.post(URL, json=named, headers=API_KEY)
    assert response.status_code == 200
    return response.json()


def stored(repository: InMemoryRepository, request_id: str) -> dict:
    return repository.select(confirmations.TABLE, {"id": request_id})[0]


@pytest.mark.parametrize(
    "named",
    [
        {"customer_ref": MARTA_ID},
        {"phone": "+56955501426"},
        {"phone": "+56 9 5550 1426"},
        {"customer_id": "31.415.926-8"},
    ],
)
def test_the_three_ways_of_naming_reach_the_same_customer(
    client: TestClient, repository: InMemoryRepository, named: dict
) -> None:
    row = stored(repository, push(client, **named)["request_id"])
    assert row["customer_id"] == MARTA_ID and row["document_number"] == "314159268"


@pytest.mark.parametrize(
    "named",
    [
        {"customer_ref": "not-a-reference"},
        {"phone": "+56900000000"},
        {"phone": "none"},
        {"conversation_id": "c"},
        # A phone call: the platform puts the caller's number in both places.
        {"customer_ref": "+56900000000", "phone": "+56900000000"},
    ],
)
def test_a_channel_that_names_nobody_is_told_so_at_once(
    client: TestClient, repository: InMemoryRepository, named: dict
) -> None:
    assert push(client, **named) == {"status": "not_identified"}
    assert repository.select(confirmations.TABLE) == []


def test_an_unknown_id_number_still_gets_the_same_answer_as_a_known_one(
    client: TestClient, repository: InMemoryRepository
) -> None:
    result = push(client, customer_id="1-9")
    assert result["status"] == "pending" and result["expires_in_seconds"] == 300
    assert stored(repository, result["request_id"])["customer_id"] is None


@pytest.mark.parametrize(
    "named",
    [
        # Inside the app: the reference names the customer, and there is no phone.
        {"customer_ref": MARTA_ID},
        # A phone call: the reference is the caller's number, so the phone decides.
        {"customer_ref": "+56955501426", "phone": "+56955501426"},
        # The ID number the customer said wins over what the channel carries.
        {"customer_id": "31.415.926-8", "customer_ref": seed_id("customer/emma")},
    ],
)
def test_a_caller_may_send_all_it_has_and_the_bank_picks(
    client: TestClient, repository: InMemoryRepository, named: dict
) -> None:
    row = stored(repository, push(client, **named)["request_id"])
    assert row["customer_id"] == MARTA_ID


def test_a_denial_by_phone_counts_towards_the_same_lockout(
    client: TestClient, repository: InMemoryRepository
) -> None:
    for _ in range(3):
        row = stored(repository, push(client, phone="+56955501426")["request_id"])
        confirmations.decide(repository, row, False, utc_now())
    assert push(client, customer_id="31.415.926-8") == {"status": "locked"}


def test_wait_returns_as_soon_as_the_customer_approves(
    client: TestClient, repository: InMemoryRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_id = push(client, customer_ref=MARTA_ID)["request_id"]
    naps = []

    def approve_during_the_first_nap(seconds: float) -> None:
        naps.append(seconds)
        confirmations.decide(repository, stored(repository, request_id), True, utc_now())

    monkeypatch.setattr(waiting, "sleep", approve_during_the_first_nap)
    body = client.get(f"{URL}/{request_id}?wait=20", headers=API_KEY).json()
    assert body["status"] == "approved" and body["first_name"] == "Marta"
    assert naps == [waiting.STEP_SECONDS]


def test_wait_gives_up_when_the_time_is_over(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_id = push(client, customer_ref=MARTA_ID)["request_id"]
    clock = [0.0]
    monkeypatch.setattr(waiting, "monotonic", lambda: clock[0])
    monkeypatch.setattr(waiting, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    assert client.get(f"{URL}/{request_id}?wait=5", headers=API_KEY).json()["status"] == "pending"
    assert clock[0] == 5.0
    assert client.get(f"{URL}/{request_id}?wait=21", headers=API_KEY).status_code == 422


def test_wait_on_a_proposal_returns_when_it_is_signed(
    client: TestClient, repository: InMemoryRepository, marta: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    offer = {"product_code": "CARD_FRAUD", "customer_response": "accepted"}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=marta).json()["offer_id"]
    sent = client.post("/v1/insurance/proposals", json={"offer_id": offer_id}, headers=marta).json()
    link = sent["signing_url"].removeprefix("http://localhost:8000")
    monkeypatch.setattr(waiting, "sleep", lambda seconds: client.post(link))
    url = f"/v1/insurance/proposals/{sent['proposal_number']}?wait=20"
    body = client.get(url, headers=marta).json()
    assert body["status"] == "signed" and body["policy_number"].startswith("PZ-")
