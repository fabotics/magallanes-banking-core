"""Reaching a person: which routes are open, meetings, and sales leads."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.routers import cases
from tests.conftest import API_KEY, TEST_API_KEY
from tests.fake_db import InMemoryRepository

# Santiago is three hours behind UTC in November.
TUESDAY_NOON = datetime(2026, 11, 17, 15, 0, tzinfo=UTC)
TUESDAY_NIGHT = datetime(2026, 11, 18, 1, 0, tzinfo=UTC)
SATURDAY_NOON = datetime(2026, 11, 21, 15, 0, tzinfo=UTC)


def routes_at(client: TestClient, monkeypatch: pytest.MonkeyPatch, moment: datetime) -> dict:
    monkeypatch.setattr(cases, "utc_now", lambda: moment)
    return client.get("/v1/cases/routes", headers=API_KEY).json()


def test_without_a_phone_line_nobody_can_be_reached_at_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert routes_at(client, monkeypatch, TUESDAY_NOON) == {
        "talk_now": {"available": False, "reason_if_not": "no_phone_line"},
        "callback": {"available": True},
        "meeting": {"available": True},
        "service_hours": "Monday to Friday, 09:00 to 18:00",
    }


def test_with_a_phone_line_a_person_answers_only_in_service_hours(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, bank_api_key=TEST_API_KEY, human_line_attached=True
    )
    assert routes_at(client, monkeypatch, TUESDAY_NOON)["talk_now"] == {"available": True}
    for closed in (TUESDAY_NIGHT, SATURDAY_NOON):
        assert routes_at(client, monkeypatch, closed)["talk_now"] == {
            "available": False,
            "reason_if_not": "outside_service_hours",
        }


def test_a_meeting_for_a_loan_quote_is_a_sales_lead(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    body = {
        "type": "meeting",
        "category": "sales_lead",
        "summary": "Marta quiere cotizar un crédito de consumo.",
        "meeting_at": "jueves a las 10:00",
    }
    result = client.post("/v1/cases", json=body, headers=marta).json()
    assert result == {
        "case_number": result["case_number"],
        "queue": "sales",
        "sla_hours": 24,
        "category": "sales_lead",
        "meeting_at": "jueves a las 10:00",
    }
    row = repository.select("cases", {"case_number": result["case_number"]})[0]
    assert row["category"] == "sales_lead" and row["meeting_at"] == "jueves a las 10:00"


def test_a_problem_is_a_service_case_and_keeps_its_callback_window(
    client: TestClient, marta: dict
) -> None:
    body = {"type": "callback", "summary": "Duda", "callback_window": "hoy de 15 a 17"}
    result = client.post("/v1/cases", json=body, headers=marta).json()
    assert result["category"] == "service" and result["queue"] == "advisors"
    assert result["callback_window"] == "hoy de 15 a 17"


def test_a_caller_who_is_not_verified_can_still_ask_for_a_callback(
    client: TestClient, repository: InMemoryRepository
) -> None:
    body = {"type": "handoff", "summary": "Pide un crédito.", "callback_window": "mañana AM"}
    result = client.post("/v1/cases", json=body, headers=API_KEY).json()
    row = repository.select("cases", {"case_number": result["case_number"]})[0]
    assert row["customer_id"] is None and row["callback_window"] == "mañana AM"
    assert (
        client.post("/v1/cases", json={**body, "type": "meeting"}, headers=API_KEY).status_code
        == 401
    )
