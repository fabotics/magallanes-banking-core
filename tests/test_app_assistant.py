"""Talking to the bank from inside the app: behind the PIN, configured from outside."""

import html
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from seed.helpers import app_pin, seed_id
from tests.conftest import API_KEY, PIN_SECRET, TEST_API_KEY

SNIPPET = (
    "<chat-widget variables='{variables}' language=\"{lang}\"></chat-widget>"
    '<script src="https://widget.example/w.js"></script>'
)
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
    assert client.get("/app/assistant/widget").status_code == 404
    assert client.get("/app/assistant/waiting").status_code == 401


def test_the_widget_lives_in_a_frame_on_the_assistant_tab_only(
    client: TestClient, with_widget: None
) -> None:
    home = sign_in(client).get("/app/home")
    assert 'href="/app/assistant"' in home.text and "Hablar con el banco" in home.text
    assert "chat-widget" not in home.text and "<iframe" not in home.text
    view = client.get("/app/assistant")
    # The view holds the frame, not the widget, and cannot itself be framed.
    assert '<iframe id="widget" src="/app/assistant/widget?lang=es"' in view.text
    assert "chat-widget" not in view.text and view.headers["x-frame-options"] == "DENY"
    inside = client.get("/app/assistant/widget")
    assert "chat-widget" in inside.text and "https://widget.example/w.js" in inside.text
    assert inside.headers["x-frame-options"] == "SAMEORIGIN"
    assert inside.headers["cache-control"] == "no-store"


def test_the_conversation_starts_with_the_customer_reference_and_the_app_language(
    client: TestClient, with_widget: None
) -> None:
    sign_in(client)
    variables = html.escape(
        json.dumps({"channel": "app", "channel_identity": MARTA_ID}), quote=True
    )
    spanish = client.get("/app/assistant/widget").text
    assert f"<chat-widget variables='{variables}' language=\"es\"></chat-widget>" in spanish
    assert "Hable con el banco" in spanish
    # The switch reloads the view, and the frame inside it, in the other language.
    view = client.get("/app/assistant?lang=en").text
    assert 'src="/app/assistant/widget?lang=en"' in view and "Read and sign" in view
    english = client.get("/app/assistant/widget?lang=en").text
    assert f"<chat-widget variables='{variables}' language=\"en\"></chat-widget>" in english
    assert "Talk to the bank" in english


def test_a_snippet_without_a_language_placeholder_still_works(
    app: FastAPI, client: TestClient
) -> None:
    old = "<chat-widget variables='{variables}'></chat-widget>"
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, bank_api_key=TEST_API_KEY, assistant_embed_html=old
    )
    page = sign_in(client).get("/app/assistant/widget?lang=en").text
    assert "<chat-widget variables='{" in page and "{lang}" not in page


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
