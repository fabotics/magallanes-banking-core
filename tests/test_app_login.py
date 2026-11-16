"""The bank's app: PIN screen, lock after three wrong PINs, session cookie, redirects."""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.clock import utc_now
from app.pins import hash_pin
from seed.data import build_seed
from seed.helpers import app_pin, seed_id
from tests.conftest import PIN_SECRET
from tests.fake_db import InMemoryRepository

MARTA_ID = seed_id("customer/marta")
MARTA_PIN = app_pin(PIN_SECRET, "marta")
WRONG_PIN = "0000" if MARTA_PIN != "0000" else "1111"


def sign_in(client: TestClient, pin: str = MARTA_PIN, **fields: str):
    return client.post("/app/login", data={"pin": pin, **fields}, follow_redirects=False)


def test_the_pin_screen_shows_only_a_first_name(client: TestClient) -> None:
    page = client.get("/app")
    assert page.status_code == 200 and "Hola, Marta" in page.text
    assert "Rojas" not in page.text and "4821" not in page.text
    assert page.headers["cache-control"] == "no-store"


def test_the_right_pin_opens_a_session_and_the_home_page(
    client: TestClient, repository: InMemoryRepository
) -> None:
    response = sign_in(client)
    assert response.status_code == 303 and response.headers["location"] == "/app/home"
    assert "httponly" in response.headers["set-cookie"].lower()
    home = client.get("/app/home")
    assert "Marta Rojas Fuentes" in home.text and "•••• 4821" in home.text
    assert "No tiene solicitudes pendientes" in home.text
    assert repository.select("audit_log")[-1]["outcome"] == "app_pin_ok"


def test_pins_are_stored_hashed_and_differ_per_customer(repository: InMemoryRepository) -> None:
    customers = repository.select("customers")
    assert all(MARTA_PIN != customer["app_pin_hash"] for customer in customers)
    assert len({customer["app_pin_hash"] for customer in customers}) == len(customers)
    marta = repository.select("customers", {"id": MARTA_ID})[0]
    assert marta["app_pin_hash"] == hash_pin(MARTA_PIN, MARTA_ID)


def test_three_wrong_pins_lock_the_app_for_a_minute(
    client: TestClient, repository: InMemoryRepository
) -> None:
    first = sign_in(client, WRONG_PIN)
    assert first.status_code == 401 and "PIN incorrecto" in first.text
    sign_in(client, WRONG_PIN)
    third = sign_in(client, WRONG_PIN)
    assert third.status_code == 429 and "Demasiados intentos" in third.text
    assert sign_in(client).status_code == 429
    # Once the minute has passed the right PIN works again.
    past = (utc_now() - timedelta(seconds=1)).isoformat()
    repository.update("customers", {"id": MARTA_ID}, {"app_locked_until": past})
    assert sign_in(client).status_code == 303


def test_a_right_pin_clears_the_count_of_wrong_ones(
    client: TestClient, repository: InMemoryRepository
) -> None:
    sign_in(client, WRONG_PIN)
    sign_in(client, WRONG_PIN)
    sign_in(client)
    assert repository.select("customers", {"id": MARTA_ID})[0]["app_failed_pins"] == 0


def test_pages_need_a_session_and_come_back_after_the_pin(client: TestClient) -> None:
    response = client.get("/app/home", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/app?next=/app/home"
    target = "/app/proposals/PR-2026-ABCDEF"
    assert sign_in(client, next=target).headers["location"] == target


def test_a_link_can_never_redirect_outside_the_app(client: TestClient) -> None:
    for target in ("https://example.com", "//example.com", "/v1/customers/me", "/app/\\x"):
        assert sign_in(client, next=target).headers["location"] == "/app/home"


def test_the_link_names_the_customer_whose_app_it_is(client: TestClient) -> None:
    pedro = seed_id("customer/pedro")
    assert client.get("/app?u=not-a-customer").status_code == 404
    assert client.get("/app?u=00000000-0000-4000-8000-000000000000").status_code == 404
    assert "Hola, Pedro Pablo" in client.get(f"/app?u={pedro}").text
    # Marta's PIN does not open Pedro's app.
    assert sign_in(client, u=pedro).status_code == 401
    assert sign_in(client, app_pin(PIN_SECRET, "pedro"), u=pedro).status_code == 303


def test_without_a_pin_secret_nobody_can_sign_in(client: TestClient) -> None:
    client.app.state.repository = InMemoryRepository(build_seed())
    assert sign_in(client).status_code == 401


def test_signing_out_and_expiry_end_the_session(
    client: TestClient, repository: InMemoryRepository
) -> None:
    sign_in(client)
    past = (utc_now() - timedelta(seconds=1)).isoformat()
    repository.update("app_sessions", {"customer_id": MARTA_ID}, {"expires_at": past})
    assert client.get("/app/home", follow_redirects=False).status_code == 303
    sign_in(client)
    assert client.post("/app/logout", follow_redirects=False).headers["location"] == "/app"
    assert client.get("/app/home", follow_redirects=False).status_code == 303
