"""Dashboard metrics, computed from rows the API itself wrote during simulated conversations."""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.clock import utc_now
from dashboard.metrics import compute_metrics, load_rows, recent_cases, share
from tests.conftest import API_KEY, MARTA
from tests.fake_db import InMemoryRepository

PEDRO = {"document_number": "32718281-1", "card_last4": "7730", "birth_year": 1979}


def verify(client: TestClient, who: dict, conversation: str) -> dict:
    body = {**who, "conversation_id": conversation}
    token = client.post("/v1/identity/verify", json=body, headers=API_KEY).json()["session_token"]
    return {**API_KEY, "X-Session-Token": token}


def resolved_with_accepted_offer(client: TestClient) -> None:
    headers = verify(client, MARTA, "conv-resolved")
    client.get("/v1/cards/transactions", headers=headers)
    offer = {"product_code": "CARD_FRAUD", "customer_response": "accepted"}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=headers).json()["offer_id"]
    proposal = client.post("/v1/insurance/proposals", json={"offer_id": offer_id}, headers=headers)
    client.post(proposal.json()["signing_url"].removeprefix("http://localhost:8000"))


def fraud_call(client: TestClient) -> None:
    headers = verify(client, PEDRO, "conv-fraud")
    client.post("/v1/cards/block", json={"card_last4": "7730", "reason": "fraud"}, headers=headers)
    client.post("/v1/cases", json={"type": "fraud", "summary": "Not mine"}, headers=headers)


def failed_identity_then_handoff(client: TestClient) -> None:
    wrong = {**MARTA, "birth_year": 1900, "conversation_id": "conv-failed"}
    client.post("/v1/identity/verify", json=wrong, headers=API_KEY)
    case = {"type": "handoff", "summary": "Not verified", "conversation_id": "conv-failed"}
    client.post("/v1/cases", json=case, headers=API_KEY)


def test_metrics_for_three_conversations(
    client: TestClient, repository: InMemoryRepository
) -> None:
    resolved_with_accepted_offer(client)
    fraud_call(client)
    failed_identity_then_handoff(client)
    metrics = compute_metrics(load_rows(repository))

    assert metrics["conversations"] == 3
    assert metrics["verified"] == 2 and metrics["verification_rate"] == 66.7
    assert metrics["resolved"] == 1 and metrics["resolution_rate"] == 33.3
    assert metrics["escalated"] == 2 and metrics["escalation_rate"] == 66.7
    assert metrics["cases_by_type"] == {"fraud": 1, "handoff": 1}
    assert metrics["cards_blocked"] == 1
    assert metrics["offers_made"] == 1 and metrics["offer_rate"] == 50.0
    assert metrics["offers_by_answer"] == {"accepted": 1} and metrics["acceptance_rate"] == 100.0
    assert metrics["proposals_sent"] == 1 and metrics["proposals_signed"] == 1
    assert metrics["signing_rate"] == 100.0


def test_an_empty_database_gives_zeros_not_errors(repository: InMemoryRepository) -> None:
    metrics = compute_metrics(load_rows(repository))
    assert metrics["conversations"] == 0 and metrics["resolution_rate"] == 0.0
    assert metrics["cases_by_type"] == {} and metrics["acceptance_rate"] == 0.0
    assert share(1, 0) == 0.0


def test_period_filter_leaves_out_old_rows(
    client: TestClient, repository: InMemoryRepository
) -> None:
    fraud_call(client)
    long_ago = (utc_now() - timedelta(days=40)).isoformat()
    repository.update("cases", {"type": "fraud"}, {"created_at": long_ago})
    assert compute_metrics(load_rows(repository, days=7))["cases_total"] == 0
    assert compute_metrics(load_rows(repository, days=None))["cases_total"] == 1


def test_recent_cases_show_no_customer_data(
    client: TestClient, repository: InMemoryRepository
) -> None:
    fraud_call(client)
    failed_identity_then_handoff(client)
    cases = recent_cases(load_rows(repository))
    assert [case["type"] for case in cases] == ["handoff", "fraud"]
    assert set(cases[0]) == {"case_number", "type", "priority", "status", "created_at"}
