"""The two write endpoints: a reversible card block, and cases for the bank's staff."""

import re

from fastapi.testclient import TestClient

from seed.helpers import seed_id
from tests.conftest import API_KEY
from tests.fake_db import InMemoryRepository

BLOCK = {"card_last4": "4821", "reason": "suspected fraud"}
FRAUD_IDS = [seed_id("transaction/pedro/fraud-1"), seed_id("transaction/pedro/fraud-2")]


def pedro_headers(client: TestClient) -> dict[str, str]:
    body = {"document_number": "32718281-1", "card_last4": "7730", "birth_year": 1979}
    token = client.post("/v1/identity/verify", json=body, headers=API_KEY).json()["session_token"]
    return {**API_KEY, "X-Session-Token": token}


def test_block_changes_the_card_and_returns_a_reference(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    response = client.post("/v1/cards/block", json=BLOCK, headers=marta)
    assert response.status_code == 200
    body = response.json()
    assert body["card_status"] == "blocked_temporary"
    assert re.fullmatch(r"BLK-\d{8}-4821", body["reference"])
    assert "temporary" in body["how_to_unblock"]
    card = repository.select("cards", {"last4": "4821"})[0]
    assert card["status"] == "blocked_temporary" and card["block_reason"] == "suspected fraud"


def test_blocking_twice_returns_the_same_state(client: TestClient, marta: dict) -> None:
    first = client.post("/v1/cards/block", json=BLOCK, headers=marta).json()
    second = client.post("/v1/cards/block", json=BLOCK, headers=marta)
    assert second.status_code == 200 and second.json() == first


def test_block_accepts_the_token_in_the_body(client: TestClient, marta_token: str) -> None:
    body = {**BLOCK, "session_token": marta_token}
    assert client.post("/v1/cards/block", json=body, headers=API_KEY).status_code == 200


def test_block_needs_a_session_and_the_customers_own_card(client: TestClient, marta: dict) -> None:
    assert client.post("/v1/cards/block", json=BLOCK, headers=API_KEY).status_code == 401
    other = client.post("/v1/cards/block", json={**BLOCK, "card_last4": "7730"}, headers=marta)
    assert other.status_code == 404 and other.json()["error"] == "card_not_found"


def test_fraud_case_is_high_priority_and_marks_the_transactions(
    client: TestClient, repository: InMemoryRepository
) -> None:
    body = {"type": "fraud", "summary": "Two charges at night", "transaction_ids": FRAUD_IDS}
    response = client.post("/v1/cases", json=body, headers=pedro_headers(client))
    assert response.status_code == 200
    assert re.fullmatch(r"MG-\d{4}-\d{6}", response.json()["case_number"])
    assert response.json()["queue"] == "fraud_operations" and response.json()["sla_hours"] == 24
    case = repository.select("cases")[0]
    assert case["priority"] == "high" and case["customer_id"] == seed_id("customer/pedro")
    assert case["transaction_ids"] == FRAUD_IDS
    assert all(repository.select("transactions", {"id": i})[0]["is_disputed"] for i in FRAUD_IDS)


def test_a_case_cannot_name_another_customers_transaction(client: TestClient, marta: dict) -> None:
    body = {"type": "fraud", "summary": "Not mine", "transaction_ids": FRAUD_IDS}
    response = client.post("/v1/cases", json=body, headers=marta)
    assert response.status_code == 404 and response.json()["error"] == "transaction_not_found"


def test_handoff_without_a_session_carries_no_customer_data(
    client: TestClient, repository: InMemoryRepository
) -> None:
    body = {
        "type": "handoff",
        "summary": "Could not verify identity, wants a person",
        "transaction_ids": FRAUD_IDS,
        "conversation_id": "conv-9",
    }
    response = client.post("/v1/cases", json=body, headers=API_KEY)
    assert response.status_code == 200 and response.json()["queue"] == "contact_center"
    case = repository.select("cases")[0]
    assert case["customer_id"] is None and case["transaction_ids"] == []
    assert case["conversation_id"] == "conv-9"


def test_handoff_with_a_session_attaches_the_customer(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    client.post("/v1/cases", json={"type": "handoff", "summary": "Upset"}, headers=marta)
    case = repository.select("cases")[0]
    assert case["customer_id"] == seed_id("customer/marta")
    assert case["conversation_id"] == "conv-test"


def test_other_case_types_need_a_session(client: TestClient) -> None:
    for case_type in ("fraud", "complaint", "callback"):
        body = {"type": case_type, "summary": "No session"}
        assert client.post("/v1/cases", json=body, headers=API_KEY).status_code == 401


def test_callback_gets_a_default_window_and_bad_types_are_rejected(
    client: TestClient, marta: dict
) -> None:
    callback = client.post("/v1/cases", json={"type": "callback", "summary": "Call"}, headers=marta)
    assert callback.json()["queue"] == "advisors" and "09:00" in callback.json()["callback_window"]
    bad = client.post("/v1/cases", json={"type": "transfer", "summary": "x"}, headers=marta)
    assert bad.status_code == 422


def test_writes_are_audited_with_their_reference(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    client.post("/v1/cards/block", json=BLOCK, headers=marta)
    client.post("/v1/cases", json={"type": "complaint", "summary": "Slow"}, headers=marta)
    block, case = repository.select("audit_log")[-2:]
    assert block["outcome"] == "card_blocked" and block["detail"]["card_last4"] == "4821"
    assert case["outcome"] == "case_created" and case["detail"]["case_number"].startswith("MG-")
