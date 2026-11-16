"""The bank's app after the PIN: answering identity confirmations and signing the contract."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import confirmations
from app.clock import utc_now
from seed.helpers import app_pin, seed_id
from tests.conftest import API_KEY, MARTA, PIN_SECRET
from tests.fake_db import InMemoryRepository

PUSH = "/v1/identity/push"
SIGNATURE = {
    "initial_1": "yes", "initial_2": "yes", "initial_3": "yes", "initial_4": "yes",
    "signature_name": "Marta Rojas Fuentes", "accept": "yes",
}  # fmt: skip


@pytest.fixture
def signed_in(client: TestClient) -> TestClient:
    """A client holding the app session of the golden-path customer."""
    client.post(
        "/app/login", data={"u": seed_id("customer/marta"), "pin": app_pin(PIN_SECRET, "marta")}
    )
    return client


def push(client: TestClient, document: str = MARTA["document_number"]) -> str:
    body = {"customer_id": document, "conversation_id": "conv-1"}
    return client.post(PUSH, json=body, headers=API_KEY).json()["request_id"]


def proposal(client: TestClient, marta: dict) -> dict:
    offer = {"product_code": "CARD_FRAUD", "customer_response": "accepted"}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=marta).json()["offer_id"]
    body = {"offer_id": offer_id}
    return client.post("/v1/insurance/proposals", json=body, headers=marta).json()


def test_approving_in_the_app_verifies_the_caller(
    signed_in: TestClient, repository: InMemoryRepository
) -> None:
    request_id = push(signed_in)
    assert f"/app/confirmations/{request_id}" in signed_in.get("/app/home").text
    page = signed_in.get(f"/app/confirmations/{request_id}")
    code = repository.select(confirmations.TABLE, {"id": request_id})[0]["code"]
    assert code in page.text and "Aprobar" in page.text and "Rechazar" in page.text

    done = signed_in.post(f"/app/confirmations/{request_id}", data={"decision": "approve"})
    assert "Identidad confirmada" in done.text
    result = signed_in.get(f"{PUSH}/{request_id}", headers=API_KEY).json()
    assert result["status"] == "approved" and result["first_name"] == "Marta"
    audit = repository.select("audit_log", {"outcome": "confirmation_approved"})
    assert len(audit) == 1 and code not in str(audit)
    # The request is answered, so it leaves the home page and cannot be answered again.
    assert request_id not in signed_in.get("/app/home").text
    again = signed_in.post(f"/app/confirmations/{request_id}", data={"decision": "deny"})
    assert "Identidad confirmada" in again.text


@pytest.mark.parametrize("decision", ["deny", "", "APPROVE"])
def test_anything_but_approve_is_a_denial(signed_in: TestClient, decision: str) -> None:
    request_id = push(signed_in)
    done = signed_in.post(f"/app/confirmations/{request_id}", data={"decision": decision})
    assert "Solicitud rechazada" in done.text
    assert signed_in.get(f"{PUSH}/{request_id}", headers=API_KEY).json() == {"status": "denied"}


def test_an_expired_request_cannot_be_approved(
    signed_in: TestClient, repository: InMemoryRepository
) -> None:
    request_id = push(signed_in)
    past = (utc_now() - timedelta(seconds=1)).isoformat()
    repository.update(confirmations.TABLE, {"id": request_id}, {"expires_at": past})
    assert request_id not in signed_in.get("/app/home").text
    done = signed_in.post(f"/app/confirmations/{request_id}", data={"decision": "approve"})
    assert "Solicitud vencida" in done.text


def test_a_customer_only_sees_their_own_requests(signed_in: TestClient) -> None:
    other = push(signed_in, "32.718.281-1")
    assert "No disponible" in signed_in.get(f"/app/confirmations/{other}").text
    answer = signed_in.post(f"/app/confirmations/{other}", data={"decision": "approve"})
    assert "No disponible" in answer.text
    assert signed_in.get(f"{PUSH}/{other}", headers=API_KEY).json() == {"status": "pending"}


def test_confirmations_need_the_pin_first(client: TestClient) -> None:
    request_id = push(client)
    response = client.get(f"/app/confirmations/{request_id}", follow_redirects=False)
    assert response.headers["location"] == f"/app?next=/app/confirmations/{request_id}"
    post = client.post(
        f"/app/confirmations/{request_id}", data={"decision": "approve"}, follow_redirects=False
    )
    assert post.status_code == 303
    assert client.get(f"{PUSH}/{request_id}", headers=API_KEY).json() == {"status": "pending"}


def test_the_contract_is_complete_and_personal(
    signed_in: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    number = proposal(signed_in, marta)["proposal_number"]
    assert f"/app/proposals/{number}" in signed_in.get("/app/home").text
    page = signed_in.get(f"/app/proposals/{number}").text
    for expected in (
        "Marta Rojas Fuentes", "31.415.926-8", "Protección de tarjeta y asistencia", "$10.790",
        "Magallanes Seguros Generales S.A.", "tarjeta Visa de crédito terminada en 4821",
        "Coberturas", "Exclusiones", "Derecho de retracto", "Término anticipado",
        f"Propuesta {number} · Página 4 de 4", 'data-initials="MR"', "Firmar y contratar",
    ):  # fmt: skip
        assert expected in page
    signed_in.get(f"/app/proposals/{number}")
    assert len(repository.select("audit_log", {"outcome": "proposal_viewed"})) == 1


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"initial_3": ""}, "Faltan sus iniciales"),
        ({"signature_name": "Marta"}, "no coincide"),
        ({"accept": ""}, "Falta marcar la confirmación"),
    ],
)
def test_an_incomplete_signature_signs_nothing(
    signed_in: TestClient, repository: InMemoryRepository, marta: dict, change: dict, error: str
) -> None:
    number = proposal(signed_in, marta)["proposal_number"]
    response = signed_in.post(f"/app/proposals/{number}", data={**SIGNATURE, **change})
    assert response.status_code == 422 and error in response.text
    assert repository.select("proposals")[0]["status"] == "sent"
    assert repository.select("policies", {"customer_id": seed_id("customer/marta")}) == []


def test_signing_in_the_app_creates_the_policy(
    signed_in: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    sent = proposal(signed_in, marta)
    number = sent["proposal_number"]
    data = {**SIGNATURE, "signature_name": "  marta ROJAS fuentes "}
    done = signed_in.post(f"/app/proposals/{number}", data=data)
    policy = repository.select("policies", {"customer_id": seed_id("customer/marta")})[0]
    assert done.status_code == 200 and "Firma recibida" in done.text
    assert policy["policy_number"] in done.text and "correo y a su mensajería" in done.text

    status = signed_in.get(f"/v1/insurance/proposals/{number}", headers=marta).json()
    assert status["status"] == "signed" and status["policy_number"] == policy["policy_number"]
    assert repository.select("audit_log")[-2]["outcome"] == "proposal_signed"
    # Signed once: the app shows the result, the home page lists the policy, the link agrees.
    assert "Firma recibida" in signed_in.post(f"/app/proposals/{number}", data=SIGNATURE).text
    assert len(repository.select("policies", {"customer_id": seed_id("customer/marta")})) == 1
    home = signed_in.get("/app/home").text
    assert policy["policy_number"] in home and f"/app/proposals/{number}" not in home
    link = sent["signing_url"].removeprefix("http://localhost:8000")
    assert "Propuesta firmada" in signed_in.get(link).text


def test_an_unknown_proposal_cannot_be_opened(signed_in: TestClient) -> None:
    assert "No disponible" in signed_in.get("/app/proposals/PR-2026-NOPE00").text


def test_asking_for_the_details_also_puts_the_contract_in_the_app(
    signed_in: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    offer = {"product_code": "CARD_FRAUD", "customer_response": "info_requested"}
    offer_id = signed_in.post("/v1/insurance/offers", json=offer, headers=marta).json()["offer_id"]
    body = {"offer_id": offer_id}
    details = signed_in.post("/v1/insurance/proposals", json=body, headers=marta).json()
    path = f"/app/proposals/{details['proposal_number']}"
    # It waits on the home page like any proposal, and signing it is what accepts it.
    assert path in signed_in.get("/app/home").text
    assert "Firma recibida" in signed_in.post(path, data=SIGNATURE).text
    assert len(repository.select("policies", {"customer_id": seed_id("customer/marta")})) == 1
