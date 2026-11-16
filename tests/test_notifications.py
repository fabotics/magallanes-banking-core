"""Call summary: sent to the channel on file for the verified customer, or honestly not sent."""

import httpx
import pytest
from fastapi.testclient import TestClient

from seed.data import build_seed
from seed.helpers import seed_id
from tests.conftest import API_KEY, BOT_TOKEN
from tests.fake_db import InMemoryRepository

URL = "/v1/notifications/call-summary"
SUMMARY = {"summary": "Reconociste el cargo del restaurante. No se hizo ningun cambio."}


def test_summary_goes_to_the_chat_on_file(
    client: TestClient, marta: dict, with_bot: None, telegram: list[dict]
) -> None:
    response = client.post(URL, json=SUMMARY, headers=marta)
    assert response.status_code == 200
    assert response.json() == {"sent": True, "channel": "telegram"}
    assert len(telegram) == 1
    assert telegram[0]["json"]["chat_id"] == "42"
    assert SUMMARY["summary"] in telegram[0]["json"]["text"]


def test_customer_without_a_channel_gets_an_honest_answer(
    client: TestClient, marta: dict, telegram: list[dict]
) -> None:
    response = client.post(URL, json=SUMMARY, headers=marta)
    assert response.json() == {"sent": False, "channel": "none"}
    assert telegram == []


def test_missing_bot_token_means_not_sent(
    client: TestClient, repository: InMemoryRepository, marta: dict, telegram: list[dict]
) -> None:
    repository.update("customers", {"id": seed_id("customer/marta")}, {"telegram_chat_id": "42"})
    assert client.post(URL, json=SUMMARY, headers=marta).json() == {
        "sent": False,
        "channel": "telegram",
    }
    assert telegram == []


def test_a_telegram_failure_is_reported_as_not_sent(
    client: TestClient, marta: dict, with_bot: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_post(url: str, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx, "post", failing_post)
    assert client.post(URL, json=SUMMARY, headers=marta).json()["sent"] is False


def test_summary_needs_a_session_and_some_text(client: TestClient, marta: dict) -> None:
    assert client.post(URL, json=SUMMARY, headers=API_KEY).status_code == 401
    assert client.post(URL, json={"summary": ""}, headers=marta).status_code == 422
    assert client.post(URL, json={"summary": "x" * 1001}, headers=marta).status_code == 422


def test_audit_records_the_result_but_not_the_text_or_the_token(
    client: TestClient,
    repository: InMemoryRepository,
    marta: dict,
    with_bot: None,
    telegram: list[dict],
) -> None:
    client.post(URL, json=SUMMARY, headers=marta)
    row = repository.select("audit_log")[-1]
    assert row["outcome"] == "summary_sent"
    assert "restaurante" not in str(row) and BOT_TOKEN not in str(row)


def test_seed_gives_the_demo_chat_to_the_golden_path_customer_only() -> None:
    customers = build_seed(demo_chat_id="987654")["customers"]
    with_chat = [row["first_name"] for row in customers if row["telegram_chat_id"]]
    assert with_chat == ["Marta"]
