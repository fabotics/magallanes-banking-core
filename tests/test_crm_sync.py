"""The CRM mirror: what is copied at each step of the sale, and that a failure stays hidden."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import crm, crm_sync
from app.config import Settings, get_settings
from seed.helpers import app_pin, seed_id
from tests.conftest import API_KEY, MARTA, PIN_SECRET, TEST_API_KEY
from tests.fake_db import InMemoryRepository

MARTA_ID = seed_id("customer/marta")
SIGNATURE = {
    **{f"initial_{page}": "yes" for page in range(1, 5)},
    "signature_name": "Marta Rojas Fuentes",
    "accept": "yes",
}


@pytest.fixture
def sent(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict]]:
    """Switch the CRM on and record every request instead of sending it."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        bank_api_key=TEST_API_KEY,
        app_pin_secret=PIN_SECRET,
        transactions_delay_seconds=0,
        salesforce_instance_url="crm.example",
        salesforce_client_id="client",
    )
    requests: list[tuple[str, str, dict]] = []

    def fake_call(settings: Settings, method: str, path: str, **request: dict) -> dict:
        requests.append((method, path, request.get("json") or request.get("params") or {}))
        if path == "/query":
            return {"records": [{"Id": "ACCOUNT"}]}
        return {"id": f"ID{len(requests)}", "created": True}

    monkeypatch.setattr(crm, "call", fake_call)
    monkeypatch.setattr(crm_sync, "found", {})
    return requests


def verified(client: TestClient) -> dict:
    token = client.post("/v1/identity/verify", json=MARTA, headers=API_KEY).json()["session_token"]
    return {**API_KEY, "X-Session-Token": token}


def log_offer(client: TestClient, session: dict, **answer: str) -> str:
    body = {"product_code": "CARD_FRAUD", **answer}
    return client.post("/v1/insurance/offers", json=body, headers=session).json()["offer_id"]


def opportunity_changes(sent: list, offer_id: str) -> list[dict]:
    path = f"/sobjects/Opportunity/Offer_Reference__c/{offer_id}"
    return [body for _, where, body in sent if where == path]


def test_the_whole_sale_is_mirrored_stage_by_stage(
    client: TestClient, repository: InMemoryRepository, sent: list
) -> None:
    session = verified(client)
    assert sent[1][1] == f"/sobjects/Contact/Customer_Reference__c/{MARTA_ID}"
    assert sent[1][2]["LastName"] == "Rojas Fuentes" and sent[1][2]["LeadSource"] == "Voice agent"
    assert "Email" not in sent[1][2] and "Phone" not in sent[1][2]

    offer_id = log_offer(client, session, outcome="sent")
    lead = next(body for _, path, body in sent if path.startswith("/sobjects/Lead/"))
    assert lead["Company"] == "Protección de tarjeta y asistencia"
    (offered,) = opportunity_changes(sent, offer_id)
    quote = repository.select("quotes")[0]
    assert offered["StageName"] == "Offered" and offered["Amount"] == 10790 * 12
    assert (
        offered["CloseDate"] <= quote["valid_until"][:10] and offered["LeadSource"] == "Voice agent"
    )
    assert ("POST", "/sobjects/OpportunityContactRole") == sent[-1][:2]

    body = {"offer_id": offer_id}
    number = client.post("/v1/insurance/proposals", json=body, headers=session).json()
    client.post("/v1/insurance/proposals", json=body, headers=session)
    client.post("/app/login", data={"u": MARTA_ID, "pin": app_pin(PIN_SECRET, "marta")})
    client.post(f"/app/proposals/{number['proposal_number']}", data=SIGNATURE)
    stages = [change["StageName"] for change in opportunity_changes(sent, offer_id)]
    assert stages == ["Offered", "Proposal Sent", "Closed Won"]
    won = opportunity_changes(sent, offer_id)[-1]
    assert won["Policy_Number__c"] == repository.select("policies")[-1]["policy_number"]


@pytest.mark.parametrize(
    ("reason", "label"),
    [("price", "Price"), ("already_insured", "Already insured"), (None, "Other")],
)
def test_a_no_is_born_closed_lost_with_its_reason(
    client: TestClient, sent: list, reason: str | None, label: str
) -> None:
    answer = {"outcome": "declined", **({"loss_reason": reason} if reason else {})}
    offer_id = log_offer(client, verified(client), **answer)
    (lost,) = opportunity_changes(sent, offer_id)
    assert lost["StageName"] == "Closed Lost" and lost["Loss_Reason__c"] == label


def test_the_outcome_is_stored_as_the_answer_and_the_old_field_still_works(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    for answer, stored in (
        ({"outcome": "sent"}, "accepted"),
        ({"outcome": "interested"}, "info_requested"),
        ({"customer_response": "declined"}, "declined"),
    ):
        offer_id = log_offer(client, marta, **answer)
        row = repository.select("insurance_offers", {"id": offer_id})[0]
        assert row["customer_response"] == stored
    nothing = client.post(
        "/v1/insurance/offers", json={"product_code": "CARD_FRAUD"}, headers=marta
    )
    assert nothing.status_code == 422


def test_a_crm_that_fails_changes_no_answer(
    client: TestClient, repository: InMemoryRepository, sent: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> dict:
        raise crm.CrmError("the CRM is down")

    monkeypatch.setattr(crm, "call", broken)
    session = verified(client)
    offer_id = log_offer(client, session, outcome="sent")
    body = {"offer_id": offer_id}
    proposal = client.post("/v1/insurance/proposals", json=body, headers=session)
    assert proposal.status_code == 200 and proposal.json()["proposal_number"].startswith("PR-")
    rows = [row["detail"].get("crm") for row in repository.select("audit_log")]
    assert rows.count("failed") == 3 and "ok" not in rows


def test_without_a_crm_nothing_is_sent_or_noted(
    client: TestClient, repository: InMemoryRepository, marta: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(*args: object, **kwargs: object) -> dict:
        raise AssertionError("no request may leave without a configured CRM")

    monkeypatch.setattr(crm, "call", never)
    log_offer(client, marta, outcome="sent")
    assert all("crm" not in row["detail"] for row in repository.select("audit_log"))


def test_the_seeded_funnel_is_invented_marked_and_always_the_same() -> None:
    from collections import Counter
    from datetime import date

    from scripts.crm_seed import people, records
    from seed.helpers import rut_check_digit

    today = date(2026, 11, 16)
    crowd = people(400, today)
    assert crowd == people(400, today) and len({person["key"] for person in crowd}) == 400
    stages = Counter(person["stage"] for person in crowd)
    assert stages == {"Closed Lost": 140, "Offered": 120, "Proposal Sent": 60, "Closed Won": 80}
    for person in crowd:
        number, digit = person["document"].split("-")
        assert 30_000_000 <= int(number) < 35_000_000 and rut_check_digit(int(number)) == digit
        assert (today - person["close"]).days <= 89 and person["amount"] % 12 == 0
        assert (person["reason"] is not None) == (person["stage"] == "Closed Lost")
    contact, lead, deal = records(crowd[0], "ACCOUNT")
    for record in (contact, lead, deal):
        assert record["Seeded__c"] is True and record["LeadSource"] == "Voice agent"
        assert "Email" not in record and "Phone" not in record
