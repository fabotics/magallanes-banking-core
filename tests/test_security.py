"""The two checks in front of the API: the caller's key and the customer's session."""

from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.clock import utc_now
from app.config import Settings, get_settings
from seed.helpers import seed_id
from tests.conftest import API_KEY, MARTA
from tests.fake_db import InMemoryRepository


def test_missing_key_is_rejected(client: TestClient) -> None:
    response = client.post("/v1/identity/verify", json=MARTA)
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_api_key"
    assert "message" in response.json()


def test_wrong_key_is_rejected(client: TestClient) -> None:
    response = client.post("/v1/identity/verify", json=MARTA, headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_unconfigured_key_fails_closed(app: FastAPI) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, bank_api_key="")
    response = TestClient(app).post("/v1/identity/verify", json=MARTA, headers={"X-API-Key": ""})
    assert response.status_code == 401


def test_session_token_is_accepted_in_the_header(client: TestClient, marta_token: str) -> None:
    headers = {**API_KEY, "X-Session-Token": marta_token}
    response = client.get("/v1/customers/me", headers=headers)
    assert response.json()["first_name"] == "Marta"


def test_session_token_is_accepted_as_a_query_parameter(
    client: TestClient, marta_token: str
) -> None:
    response = client.get(f"/v1/customers/me?session_token={marta_token}", headers=API_KEY)
    assert response.status_code == 200


def test_missing_or_unknown_session_is_rejected(client: TestClient) -> None:
    for headers in (API_KEY, {**API_KEY, "X-Session-Token": "not-a-session"}):
        response = client.get("/v1/customers/me", headers=headers)
        assert response.status_code == 401
        assert response.json()["error"] == "identity_not_verified"


def test_expired_session_is_rejected(client: TestClient, repository: InMemoryRepository) -> None:
    an_hour_ago = utc_now() - timedelta(hours=1)
    repository.insert(
        "verification_sessions",
        {
            "token": "old-token",
            "customer_id": seed_id("customer/marta"),
            "conversation_id": None,
            "created_at": an_hour_ago.isoformat(),
            "expires_at": (an_hour_ago + timedelta(minutes=15)).isoformat(),
        },
    )
    response = client.get("/v1/customers/me", headers={**API_KEY, "X-Session-Token": "old-token"})
    assert response.status_code == 401


def test_unknown_path_and_bad_body_use_the_error_shape(client: TestClient) -> None:
    assert client.get("/nowhere").json()["error"] == "not_found"
    response = client.post("/v1/identity/verify", json={"card_last4": "4821"}, headers=API_KEY)
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert "document_number" in response.json()["message"]
