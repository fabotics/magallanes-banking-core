"""Talking to the bank from inside the app: behind the PIN, configured from outside."""

import html
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from seed.helpers import app_pin, seed_id
from tests.conftest import API_KEY, PIN_SECRET, TEST_API_KEY

SNIPPET = "<chat-widget variables='{variables}'></chat-widget><script src=\"https://widget.example/w.js\"></script>"
MARTA_ID = seed_id("customer/marta")


@pytest.fixture
def with_widget(app: FastAPI) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, bank_api_key=TEST_API_KEY, assistant_embed_html=SNIPPET
    )


def sign_in(client: TestClient) -> TestClient:
    client.post("/app/login", data={"u": MARTA_ID, "pin": app_pin(PIN_SECRET, "marta")})
    return client


def test_without_a_snippet_there_is_no_button_and_no_widget(client: TestClient) -> None:
    home = sign_in(client).get("/app/home").text
    assert "/app/assistant" not in home
    page = client.get("/app/assistant")
    assert "Asistente no disponible" in page.text and "<script src" not in page.text


def test_the_widget_exists_only_behind_the_pin(client: TestClient, with_widget: None) -> None:
    locked = client.get("/app/assistant", follow_redirects=False)
    assert locked.status_code == 303 and locked.headers["location"].startswith("/app?next=")
    assert "chat-widget" not in client.get("/app").text
    assert client.get("/app/assistant/waiting").status_code == 401


def test_the_conversation_starts_with_the_customer_reference(
    client: TestClient, with_widget: None
) -> None:
    home = sign_in(client).get("/app/home").text
    assert 'href="/app/assistant"' in home and "Hablar con el banco" in home
    page = client.get("/app/assistant").text
    variables = json.dumps({"channel": "app", "channel_identity": MARTA_ID})
    expected = html.escape(variables, quote=True)
    assert f"<chat-widget variables='{expected}'></chat-widget>" in page
    assert "https://widget.example/w.js" in page and "Hable con el banco" in page
    english = client.get("/app/assistant?lang=en").text
    assert "Talk to the bank" in english and "Read and sign" in english


def test_what_the_assistant_sends_can_be_answered_without_leaving_the_page(
    client: TestClient, with_widget: None
) -> None:
    sign_in(client)
    assert client.get("/app/assistant/waiting").json() == {"confirmations": [], "proposals": []}
    pushed = client.post("/v1/identity/push", json={"customer_ref": MARTA_ID}, headers=API_KEY)
    request_id = pushed.json()["request_id"]
    waiting = client.get("/app/assistant/waiting").json()["confirmations"]
    assert [item["id"] for item in waiting] == [request_id] and len(waiting[0]["code"]) == 6
    client.post(f"/app/confirmations/{request_id}", data={"decision": "approve"})
    assert client.get("/app/assistant/waiting").json()["confirmations"] == []
    status = client.get(f"/v1/identity/push/{request_id}", headers=API_KEY).json()
    assert status["status"] == "approved" and status["first_name"] == "Marta"
