"""The API key check that guards every `/v1` route."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from tests.conftest import TEST_API_KEY


def test_missing_key_is_rejected(client: TestClient) -> None:
    response = client.get("/v1/probe")
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_api_key"
    assert "message" in response.json()


def test_wrong_key_is_rejected(client: TestClient) -> None:
    response = client.get("/v1/probe", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_correct_key_is_accepted(client: TestClient) -> None:
    response = client.get("/v1/probe", headers={"X-API-Key": TEST_API_KEY})
    assert response.status_code == 200


def test_unconfigured_key_fails_closed(app: FastAPI) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, bank_api_key="")
    response = TestClient(app).get("/v1/probe", headers={"X-API-Key": ""})
    assert response.status_code == 401
