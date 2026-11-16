"""Insurance: the bank's eligibility rules, the consent record, proposals and signing."""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from seed.helpers import seed_id
from tests.conftest import API_KEY, TEST_API_KEY
from tests.fake_db import InMemoryRepository

PEOPLE = {
    "carolina": {"document_number": "33161803-9", "card_last4": "1164", "birth_year": 1991},
    "jorge": {"document_number": "30577215-1", "card_last4": "9052", "birth_year": 1948},
    "lucia": {"document_number": "34141421-0", "card_last4": "3378", "birth_year": 1995},
    "rosa": {"document_number": "90000017", "card_last4": "6410", "birth_year": 1983},
}


def headers_for(client: TestClient, key: str) -> dict[str, str]:
    response = client.post("/v1/identity/verify", json=PEOPLE[key], headers=API_KEY)
    return {**API_KEY, "X-Session-Token": response.json()["session_token"]}


def offer(client: TestClient, headers: dict, answer: str, product: str = "CARD_FRAUD") -> dict:
    body = {"product_code": product, "customer_response": answer}
    response = client.post("/v1/insurance/offers", json=body, headers=headers)
    assert response.status_code == 200
    return response.json()


def test_eligible_customer_gets_a_choice_of_products(client: TestClient, marta: dict) -> None:
    body = client.get("/v1/insurance/eligibility", headers=marta).json()
    assert body["eligible"] is True and body["reason_if_not"] is None
    assert [product["code"] for product in body["products"]] == ["CARD_FRAUD", "UNEMPLOYMENT"]
    assert body["products"][0] == {
        "code": "CARD_FRAUD",
        "name": "Protección de tarjeta y asistencia",
        "monthly_premium": 8990,
        "currency": "CLP",
        "coverage_summary": body["products"][0]["coverage_summary"],
        "quote_number": body["products"][0]["quote_number"],
        "coverage_limit": 1500000,
        "valid_until": body["products"][0]["valid_until"],
    }
    assert "la ley no pone a cargo del banco" in body["products"][0]["coverage_summary"]
    assert "no autorizados" not in body["products"][0]["coverage_summary"]


@pytest.mark.parametrize(
    ("person", "reason"),
    [("carolina", "already_insured"), ("jorge", "vulnerable_customer")],
)
def test_not_eligible_customers_get_a_reason(client: TestClient, person: str, reason: str) -> None:
    body = client.get("/v1/insurance/eligibility", headers=headers_for(client, person)).json()
    assert body == {"eligible": False, "products": [], "reason_if_not": reason}


def test_segment_rule(client: TestClient, repository: InMemoryRepository) -> None:
    repository.update("insurance_products", {"code": "CARD_FRAUD"}, {"eligible_segments": []})
    body = client.get("/v1/insurance/eligibility", headers=headers_for(client, "lucia")).json()
    assert body["eligible"] is False and body["reason_if_not"] == "segment_not_eligible"


def test_catalog_is_only_available_in_the_pilot_country(client: TestClient) -> None:
    headers = headers_for(client, "rosa")
    body = client.get("/v1/insurance/eligibility", headers=headers).json()
    assert body == {
        "eligible": False,
        "products": [],
        "reason_if_not": "not_available_in_country",
    }
    offer = {"product_code": "CARD_FRAUD", "customer_response": "accepted"}
    assert client.post("/v1/insurance/offers", json=offer, headers=headers).status_code == 409


def test_every_offer_is_stored_as_the_consent_record(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    declined = offer(client, marta, "declined")
    accepted = offer(client, marta, "accepted", product="UNEMPLOYMENT")
    rows = repository.select("insurance_offers")
    assert [row["id"] for row in rows] == [declined["offer_id"], accepted["offer_id"]]
    assert [row["customer_response"] for row in rows] == ["declined", "accepted"]
    assert rows[0]["customer_id"] == seed_id("customer/marta")
    assert rows[0]["conversation_id"] == "conv-test" and declined["logged_at"]


def test_an_offer_the_bank_did_not_approve_is_refused(client: TestClient) -> None:
    body = {"product_code": "CARD_FRAUD", "customer_response": "accepted"}
    response = client.post(
        "/v1/insurance/offers", json=body, headers=headers_for(client, "carolina")
    )
    assert response.status_code == 409 and response.json()["error"] == "not_eligible"
    assert client.post("/v1/insurance/offers", json=body, headers=API_KEY).status_code == 401


def test_accepted_offer_gets_a_proposal_with_a_signing_link(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    offer_id = offer(client, marta, "accepted")["offer_id"]
    response = client.post("/v1/insurance/proposals", json={"offer_id": offer_id}, headers=marta)
    assert response.status_code == 200
    body = response.json()
    stored = repository.select("proposals")[0]
    assert body["proposal_number"].startswith("PR-")
    assert body["signing_url"] == f"http://localhost:8000/sign/{stored['signing_token']}"
    assert body["sent_to"] == "m***@example.com" and body["email_sent"] is False
    again = client.post("/v1/insurance/proposals", json={"offer_id": offer_id}, headers=marta)
    assert again.json() == body and len(repository.select("proposals")) == 1


def test_info_request_gets_details_without_a_signing_link(client: TestClient, marta: dict) -> None:
    offer_id = offer(client, marta, "info_requested")["offer_id"]
    body = client.post("/v1/insurance/proposals", json={"offer_id": offer_id}, headers=marta).json()
    assert "signing_url" not in body and body["proposal_number"].startswith("PR-")


def test_declined_or_foreign_offers_get_no_proposal(client: TestClient, marta: dict) -> None:
    declined = offer(client, marta, "declined")["offer_id"]
    response = client.post("/v1/insurance/proposals", json={"offer_id": declined}, headers=marta)
    assert response.status_code == 409 and response.json()["error"] == "offer_declined"
    accepted = offer(client, marta, "accepted")["offer_id"]
    other = client.post(
        "/v1/insurance/proposals", json={"offer_id": accepted}, headers=headers_for(client, "rosa")
    )
    assert other.status_code == 404 and other.json()["error"] == "offer_not_found"


def test_email_is_sent_only_when_a_key_is_configured(
    app: FastAPI, client: TestClient, marta: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        sent.append(kwargs["json"])
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, bank_api_key=TEST_API_KEY, resend_api_key="test-email-key"
    )
    offer_id = offer(client, marta, "accepted")["offer_id"]
    body = client.post("/v1/insurance/proposals", json={"offer_id": offer_id}, headers=marta).json()
    assert body["email_sent"] is True and len(sent) == 1
    assert sent[0]["to"] == ["marta.rojas@example.com"] and body["signing_url"] in sent[0]["html"]


def test_signing_the_proposal_creates_the_policy(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    offer_id = offer(client, marta, "accepted")["offer_id"]
    url = client.post("/v1/insurance/proposals", json={"offer_id": offer_id}, headers=marta).json()[
        "signing_url"
    ]
    path = url.removeprefix("http://localhost:8000")

    page = client.get(path)
    assert page.status_code == 200 and "Firmar propuesta" in page.text
    assert "Protección de tarjeta y asistencia" in page.text and "Marta" in page.text

    signed = client.post(path)
    assert signed.status_code == 200 and "Propuesta firmada" in signed.text
    client.post(path)
    policies = repository.select("policies", {"customer_id": seed_id("customer/marta")})
    assert [policy["product_code"] for policy in policies] == ["CARD_FRAUD"]
    assert repository.select("proposals")[0]["status"] == "signed"
    assert repository.select("audit_log")[-1]["outcome"] == "proposal_signed"

    eligibility = client.get("/v1/insurance/eligibility", headers=marta).json()
    assert [product["code"] for product in eligibility["products"]] == ["UNEMPLOYMENT"]


def test_unknown_signing_link_is_a_404_page(client: TestClient) -> None:
    for response in (client.get("/sign/nope"), client.post("/sign/nope")):
        assert response.status_code == 404 and "Enlace no válido" in response.text
