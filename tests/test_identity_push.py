"""Identity confirmation in the app: request, answer, session, expiry and lockout."""

from datetime import timedelta

from fastapi.testclient import TestClient

from app import confirmations
from app.clock import utc_now
from seed.helpers import seed_id
from tests.conftest import API_KEY, MARTA
from tests.fake_db import InMemoryRepository

URL = "/v1/identity/push"
DOCUMENT = MARTA["document_number"]


def request_push(client: TestClient, customer_id: str = DOCUMENT) -> dict:
    body = {"customer_id": customer_id, "conversation_id": "conv-1"}
    response = client.post(URL, json=body, headers=API_KEY)
    assert response.status_code == 200
    return response.json()


def status(client: TestClient, request_id: str) -> dict:
    response = client.get(f"{URL}/{request_id}", headers=API_KEY)
    assert response.status_code == 200
    return response.json()


def answer(repository: InMemoryRepository, request_id: str, approved: bool) -> None:
    """Answer the request the way the customer app does."""
    confirmation = repository.select(confirmations.TABLE, {"id": request_id})[0]
    confirmations.decide(repository, confirmation, approved, utc_now())


def test_a_request_is_pending_for_five_minutes_and_hides_the_code(
    client: TestClient, repository: InMemoryRepository
) -> None:
    result = request_push(client)
    assert result == {
        "status": "pending",
        "request_id": result["request_id"],
        "expires_in_seconds": 300,
    }
    row = repository.select(confirmations.TABLE, {"id": result["request_id"]})[0]
    assert row["customer_id"] == seed_id("customer/marta")
    assert len(row["code"]) == 6 and row["code"].isdigit()
    assert status(client, result["request_id"])["status"] == "pending"


def test_the_customer_is_notified_with_the_code_and_a_link_into_the_app(
    client: TestClient, repository: InMemoryRepository, with_bot: None, telegram: list[dict]
) -> None:
    result = request_push(client)
    row = repository.select(confirmations.TABLE, {"id": result["request_id"]})[0]
    text = telegram[0]["json"]["text"]
    assert telegram[0]["json"]["chat_id"] == "42"
    assert f"Código {row['code']}" in text
    assert f"/app?u={row['customer_id']}&next=/app/confirmations/{result['request_id']}" in text


def test_an_approval_opens_the_same_session_as_the_spoken_check(
    client: TestClient, repository: InMemoryRepository
) -> None:
    request_id = request_push(client)["request_id"]
    answer(repository, request_id, approved=True)
    result = status(client, request_id)
    overview = result.pop("overview")
    assert result.pop("review_route") == "review"
    assert result == {
        "status": "approved",
        "session_token": result["session_token"],
        "first_name": "Marta",
    }
    assert overview["customer"]["segment"] == "preferred"
    # First what the statement shows: no merchant and no day of purchase in it.
    (shown,), (explained,) = overview["turn_1"], overview["reveal"]
    assert shown["total"] == 34900 and shown["posted_weekday"] == "Monday"
    assert [line["time"] for line in shown["charges"]] == [
        "9:52 pm",
        "10:37 pm",
        "11:14 pm",
        "11:58 pm",
    ]
    assert "Saturday" not in str(shown) and "tax" not in str(shown)
    # Then what explains it, for when the customer asks.
    assert explained["purchased_on"][0].startswith("Saturday ")
    assert explained["merchant_tax_id"] == "66871234-7"
    assert "post a day or two later" in explained["why_the_dates_differ"]
    headers = {**API_KEY, "X-Session-Token": result["session_token"]}
    assert client.get("/v1/customers/me", headers=headers).status_code == 200
    # Asking again returns the same session instead of opening a second one.
    assert status(client, request_id)["session_token"] == result["session_token"]
    sessions = repository.select("verification_sessions", {"conversation_id": "conv-1"})
    assert len(sessions) == 1


def test_a_denial_gives_no_session(client: TestClient, repository: InMemoryRepository) -> None:
    request_id = request_push(client)["request_id"]
    answer(repository, request_id, approved=False)
    assert status(client, request_id)["status"] == "denied"
    assert repository.select("verification_sessions") == []


def test_a_request_expires_and_cannot_be_approved_late(
    client: TestClient, repository: InMemoryRepository
) -> None:
    request_id = request_push(client)["request_id"]
    past = (utc_now() - timedelta(seconds=1)).isoformat()
    repository.update(confirmations.TABLE, {"id": request_id}, {"expires_at": past})
    answer(repository, request_id, approved=True)
    assert status(client, request_id)["status"] == "expired"
    assert repository.select("verification_attempts") == []


def test_an_answer_cannot_be_changed(client: TestClient, repository: InMemoryRepository) -> None:
    request_id = request_push(client)["request_id"]
    answer(repository, request_id, approved=False)
    answer(repository, request_id, approved=True)
    assert status(client, request_id)["status"] == "denied"


def test_an_unknown_document_gets_the_same_answer_and_no_message(
    client: TestClient, repository: InMemoryRepository, with_bot: None, telegram: list[dict]
) -> None:
    result = request_push(client, "11.111.111-1")
    assert result["status"] == "pending" and result["expires_in_seconds"] == 300
    assert telegram == []
    assert repository.select(confirmations.TABLE)[0]["customer_id"] is None


def test_three_denials_lock_both_paths(client: TestClient, repository: InMemoryRepository) -> None:
    for _ in range(3):
        answer(repository, request_push(client)["request_id"], approved=False)
    assert request_push(client) == {"status": "locked"}
    spoken = client.post("/v1/identity/verify", json=MARTA, headers=API_KEY).json()
    assert spoken["locked"] is True


def test_failed_spoken_checks_lock_the_app_path_too(client: TestClient) -> None:
    for _ in range(3):
        client.post("/v1/identity/verify", json={**MARTA, "card_last4": "0000"}, headers=API_KEY)
    assert request_push(client) == {"status": "locked"}


def test_unknown_and_malformed_request_ids(client: TestClient) -> None:
    missing = client.get(f"{URL}/00000000-0000-4000-8000-000000000000", headers=API_KEY)
    assert missing.status_code == 404
    assert missing.json()["error"] == "request_not_found"
    assert client.get(f"{URL}/not-a-uuid", headers=API_KEY).status_code == 422


def test_calls_are_audited_without_the_code(
    client: TestClient, repository: InMemoryRepository
) -> None:
    request_id = request_push(client)["request_id"]
    answer(repository, request_id, approved=True)
    status(client, request_id)
    rows = repository.select("audit_log")
    assert [row["outcome"] for row in rows] == ["push_requested", "push_approved"]
    code = repository.select(confirmations.TABLE)[0]["code"]
    assert code not in str(rows)
    assert rows[0]["detail"]["document"] == "*****9268"


def test_the_api_key_is_required(client: TestClient) -> None:
    assert client.post(URL, json={"customer_id": DOCUMENT}).status_code == 401
