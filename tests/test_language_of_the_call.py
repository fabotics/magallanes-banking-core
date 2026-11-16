"""Messages, emails and links follow the language of the call, else the customer's own."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import notices
from app.config import Settings, get_settings
from seed.helpers import seed_id
from tests.conftest import API_KEY, BOT_TOKEN, EMMA, MARTA, TEST_API_KEY
from tests.fake_db import InMemoryRepository

EMMA_ID = seed_id("customer/emma")


@pytest.fixture
def sending(app: FastAPI, repository: InMemoryRepository, telegram: list[dict]) -> list[dict]:
    """Chat and email are both configured, and both demo customers have a chat."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        bank_api_key=TEST_API_KEY,
        telegram_bot_token=BOT_TOKEN,
        resend_api_key="test-email-key",
    )
    for key in ("emma", "marta"):
        repository.update(
            "customers", {"id": seed_id(f"customer/{key}")}, {"telegram_chat_id": "42"}
        )
    return telegram


def session(client: TestClient, person: dict) -> dict:
    token = client.post("/v1/identity/verify", json=person, headers=API_KEY).json()["session_token"]
    return {**API_KEY, "X-Session-Token": token}


def proposal(client: TestClient, headers: dict, **extra: str) -> dict:
    offer = {"product_code": "CARD_FRAUD", "customer_response": "accepted"}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=headers).json()["offer_id"]
    body = {"offer_id": offer_id, **extra}
    return client.post("/v1/insurance/proposals", json=body, headers=headers).json()


def texts(sent: list[dict]) -> list[str]:
    return [call["json"].get("text") or call["json"]["html"] for call in sent]


def test_the_english_speaker_is_a_customer_like_any_other(client: TestClient) -> None:
    headers = session(client, EMMA)
    profile = client.get("/v1/customers/me", headers=headers).json()
    assert profile["first_name"] == "Emma" and profile["preferred_language"] == "en"
    products = client.get("/v1/insurance/eligibility", headers=headers).json()["products"]
    card = next(product for product in products if product["code"] == "CARD_FRAUD")
    # Her own quote: the premium segment pays less and has a higher limit.
    assert card["monthly_premium"] == 8490 and card["coverage_limit"] == 2_000_000


def test_her_confirmation_request_is_in_english_with_an_english_link(
    client: TestClient, sending: list[dict]
) -> None:
    body = {"customer_ref": EMMA_ID}
    request_id = client.post("/v1/identity/push", json=body, headers=API_KEY).json()["request_id"]
    (text,) = texts(sending)
    assert "is asking to confirm your identity. Code" in text
    assert f"/app?u={EMMA_ID}&next=/app/confirmations/{request_id}&lang=en" in text


def test_the_language_of_the_call_wins_over_the_language_on_file(
    client: TestClient, sending: list[dict]
) -> None:
    body = {"customer_id": MARTA["document_number"], "language": "en"}
    client.post("/v1/identity/push", json=body, headers=API_KEY)
    client.post(
        "/v1/identity/push", json={"customer_ref": EMMA_ID, "language": "es"}, headers=API_KEY
    )
    english, spanish = texts(sending)
    assert "Open the app to approve or reject" in english and "&lang=en" in english
    assert "Abra la app para aprobar o rechazar" in spanish and "&lang=es" in spanish
    refused = client.post(
        "/v1/identity/push", json={"customer_ref": EMMA_ID, "language": "fr"}, headers=API_KEY
    )
    assert refused.status_code == 422


def test_her_proposal_and_policy_arrive_in_english(client: TestClient, sending: list[dict]) -> None:
    headers = session(client, EMMA)
    sent = proposal(client, headers)
    email, message = texts(sending)
    assert "Card protection and assistance" in email and "Monthly premium: CLP 8,490" in email
    assert f"{sent['signing_url']}?lang=en" in email and "Review and sign the proposal" in email
    assert "Your Card protection and assistance proposal is ready to sign" in message
    assert f"next=/app/proposals/{sent['proposal_number']}&lang=en" in message
    sending.clear()
    signing_path = sent["signing_url"].removeprefix("http://localhost:8000")
    client.post(f"{signing_path}?lang=en")
    email, message = texts(sending)
    assert "insurance is now active" in email and "In force from" in message
    assert sending[0]["json"]["subject"].startswith("Banco Magallanes: your policy PZ-")


def test_the_spanish_speaker_still_gets_spanish(client: TestClient, sending: list[dict]) -> None:
    headers = session(client, MARTA)
    sent = proposal(client, headers)
    email, message = texts(sending)
    assert "Protección de tarjeta y asistencia" in email and "Prima mensual: $8.990" in email
    assert "está lista para firmar" in message and "&lang=es" in message
    assert f"{sent['signing_url']}?lang=es" in email


def test_the_summary_is_headed_in_the_language_of_the_call(
    client: TestClient, sending: list[dict]
) -> None:
    url = "/v1/notifications/call-summary"
    client.post(url, json={"summary": "You recognised the charges."}, headers=session(client, EMMA))
    marta = session(client, MARTA)
    client.post(url, json={"summary": "Reconoció los cargos."}, headers=marta)
    client.post(url, json={"summary": "All fine.", "language": "en"}, headers=marta)
    first, second, third = texts(sending)
    assert first.startswith("Banco Magallanes\nSummary of your call:\n\nYou recognised")
    assert "Resumen de tu llamada:" in second and "Summary of your call:" in third


def test_an_unknown_language_on_file_falls_back_to_spanish() -> None:
    assert notices.language_for({"preferred_language": "pt"}) == "es"
    assert notices.language_for({"preferred_language": "pt"}, "en") == "en"
    assert notices.language_for({}) == "es"
