"""The bank's phone line on the sign-in screen, and the demo customer's phone on file."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.routers.app_auth import dialable
from seed.data import build_seed
from tests.conftest import PIN_SECRET, TEST_API_KEY

LINE = "+1 555 010 0100"


def with_line(app: FastAPI, line: str) -> None:
    """Run the app with this phone line in its settings."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, bank_api_key=TEST_API_KEY, app_pin_secret=PIN_SECRET, bank_phone_line=line
    )


def test_the_sign_in_screen_offers_the_phone_line_in_both_languages(
    app: FastAPI, client: TestClient
) -> None:
    with_line(app, LINE)
    spanish = client.get("/app").text
    english = client.get("/app?lang=en").text
    link = f'<a href="tel:+15550100100">{LINE}</a>'
    assert "¿Prefiere llamar?" in spanish and link in spanish
    assert "Prefer to call?" in english and link in english


def test_the_line_stays_after_a_wrong_pin(app: FastAPI, client: TestClient) -> None:
    with_line(app, LINE)
    page = client.post("/app/login", data={"document": "1-9", "pin": "0000"})
    assert page.status_code == 401 and "tel:+15550100100" in page.text


def test_without_a_phone_line_nothing_is_shown(client: TestClient) -> None:
    page = client.get("/app?lang=en").text
    assert "Prefer to call?" not in page and "tel:" not in page


def test_a_number_is_dialled_without_spaces() -> None:
    assert dialable("+1 (555) 010-0100") == "+15550100100"


def test_the_demo_phone_goes_to_the_first_demo_customer_only() -> None:
    customers = build_seed(demo_phone="+56900000001")["customers"]
    assert [row["first_name"] for row in customers if row["phone"] == "+56900000001"] == ["Emma"]
    assert len({row["phone"] for row in customers}) == len(customers)
