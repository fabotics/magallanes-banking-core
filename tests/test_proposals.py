"""Proposals after they are sent: the link in the chat, the status, the signature, the policy."""

from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.clock import bank_date, utc_now
from app.config import Settings, get_settings
from app.formatting import long_date, money
from tests.conftest import API_KEY, BOT_TOKEN, TEST_API_KEY
from tests.fake_db import InMemoryRepository

PROPOSALS = "/v1/insurance/proposals"


def send(client: TestClient, marta: dict, answer: str = "accepted") -> dict:
    """Log an offer with this answer and ask for its proposal."""
    offer = {"product_code": "CARD_FRAUD", "customer_response": answer}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=marta).json()["offer_id"]
    response = client.post(PROPOSALS, json={"offer_id": offer_id}, headers=marta)
    assert response.status_code == 200
    return response.json()


def status(client: TestClient, marta: dict, number: str) -> dict:
    response = client.get(f"{PROPOSALS}/{number}", headers=marta)
    assert response.status_code == 200
    return response.json()


def signing_path(proposal: dict) -> str:
    return proposal["signing_url"].removeprefix("http://localhost:8000")


def test_a_new_proposal_is_pending(client: TestClient, marta: dict) -> None:
    proposal = send(client, marta)
    assert proposal["message_sent"] is False
    assert status(client, marta, proposal["proposal_number"]) == {
        "proposal_number": proposal["proposal_number"],
        "status": "pending",
    }


def test_the_signing_link_goes_to_the_chat_with_product_and_premium(
    client: TestClient,
    repository: InMemoryRepository,
    marta: dict,
    with_bot: None,
    telegram: list[dict],
) -> None:
    proposal = send(client, marta)
    assert proposal["message_sent"] is True and len(telegram) == 1
    text = telegram[0]["json"]["text"]
    assert f"next=/app/proposals/{proposal['proposal_number']}" in text
    assert proposal["signing_url"] not in text
    assert "Protección de tarjeta y asistencia" in text and "$10.790" in text
    # Asking again returns the same proposal and sends it to the customer again.
    offer_id = repository.select("insurance_offers")[0]["id"]
    again = client.post(PROPOSALS, json={"offer_id": offer_id}, headers=marta).json()
    assert again["proposal_number"] == proposal["proposal_number"] and len(telegram) == 2
    assert again["message_sent"] is True and telegram[1]["json"]["text"] == text


def test_asking_for_the_details_sends_the_link_to_the_chat_too(
    client: TestClient, marta: dict, with_bot: None, telegram: list[dict]
) -> None:
    assert send(client, marta, "info_requested")["message_sent"] is True
    assert len(telegram) == 1


def test_signing_gives_the_policy_number_and_start_date(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    proposal = send(client, marta)
    page = client.post(signing_path(proposal))
    result = status(client, marta, proposal["proposal_number"])
    policy = repository.select("policies", {"policy_number": result["policy_number"]})[0]
    assert result == {
        "proposal_number": proposal["proposal_number"],
        "status": "signed",
        "policy_number": policy["policy_number"],
        "start_date": bank_date(utc_now()).isoformat(),
    }
    assert policy["policy_number"].startswith("PZ-") and policy["status"] == "active"
    assert policy["policy_number"] in page.text


def test_a_signature_is_confirmed_by_email_and_in_the_chat(
    app: FastAPI,
    client: TestClient,
    repository: InMemoryRepository,
    marta: dict,
    with_bot: None,
    telegram: list[dict],
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        bank_api_key=TEST_API_KEY,
        telegram_bot_token=BOT_TOKEN,
        resend_api_key="test-email-key",
    )
    proposal = send(client, marta)
    telegram.clear()
    client.post(signing_path(proposal))
    number = repository.select("policies", {"product_code": "CARD_FRAUD"})[-1]["policy_number"]
    email, message = telegram
    assert "api.resend.com" in email["url"] and number in email["json"]["html"]
    assert number in message["json"]["text"] and "Vigente desde" in message["json"]["text"]


def test_sent_viewed_and_signed_are_audited_once_each(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    proposal = send(client, marta)
    path = signing_path(proposal)
    client.get(path)
    client.get(path)
    client.post(path)
    client.post(path)
    outcomes = [row["outcome"] for row in repository.select("audit_log")]
    assert outcomes[-3:] == ["proposal_sent", "proposal_viewed", "proposal_signed"]
    assert proposal["signing_url"].rsplit("/", 1)[1] not in str(repository.select("audit_log"))


def test_a_proposal_expires_when_its_quote_would(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    proposal = send(client, marta)
    old = (utc_now() - timedelta(days=15, minutes=1)).isoformat()
    repository.update(
        "proposals", {"proposal_number": proposal["proposal_number"]}, {"created_at": old}
    )
    assert status(client, marta, proposal["proposal_number"])["status"] == "expired"
    page = client.post(signing_path(proposal))
    assert "ya no está vigente" in page.text
    assert repository.select("policies", {"customer_id": proposal_customer(repository)}) == []


def proposal_customer(repository: InMemoryRepository) -> str:
    return repository.select("proposals")[0]["customer_id"]


def test_only_the_owner_with_a_session_can_read_the_status(client: TestClient, marta: dict) -> None:
    number = send(client, marta)["proposal_number"]
    assert client.get(f"{PROPOSALS}/{number}", headers=API_KEY).status_code == 401
    verify = {"document_number": "32.718.281-1", "card_last4": "7730", "birth_year": 1979}
    token = client.post("/v1/identity/verify", json=verify, headers=API_KEY).json()["session_token"]
    other = client.get(f"{PROPOSALS}/{number}", headers={**API_KEY, "X-Session-Token": token})
    assert other.status_code == 404 and other.json()["error"] == "proposal_not_found"


def test_amounts_and_dates_are_written_the_local_way() -> None:
    assert money(2990, "CLP") == "$2.990"
    assert money(1284500.0, "CLP") == "$1.284.500"
    assert money(12.5, "PEN") == "PEN 12.50"
    assert long_date(date(2026, 11, 16)) == "16 de noviembre de 2026"
