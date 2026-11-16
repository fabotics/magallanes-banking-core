"""The bank's app: signing in with ID number and PIN, the remembered customer, the lock."""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.clock import utc_now
from app.pins import hash_pin
from seed.data import build_seed
from seed.helpers import app_pin, seed_id
from seed.people import PEOPLE
from tests.conftest import PIN_SECRET
from tests.fake_db import InMemoryRepository

MARTA_ID = seed_id("customer/marta")
MARTA_PIN = app_pin(PIN_SECRET, "marta")
WRONG_PIN = "0000" if MARTA_PIN != "0000" else "1111"


def sign_in(client: TestClient, pin: str = MARTA_PIN, **fields: str):
    """Post the PIN screen of a customer the app already knows (Marta unless told otherwise)."""
    data = {"u": MARTA_ID, "pin": pin, **fields}
    return client.post("/app/login", data=data, follow_redirects=False)


def full_form(client: TestClient, document: str, pin: str):
    """Post the first-visit form: ID number and PIN."""
    return client.post(
        "/app/login", data={"document": document, "pin": pin}, follow_redirects=False
    )


def test_the_first_visit_asks_for_the_id_number_and_the_pin(client: TestClient) -> None:
    page = client.get("/app")
    assert page.status_code == 200 and 'name="document"' in page.text
    assert "Ingrese a su banco" in page.text and 'name="pin"' in page.text
    # Nobody is named before someone signs in.
    assert "Hola," not in page.text and "Marta" not in page.text and "Emma" not in page.text
    assert page.headers["cache-control"] == "no-store"


def test_every_seed_customer_can_sign_in_with_id_number_and_pin(client: TestClient) -> None:
    for key, _, document, first_name, *_ in PEOPLE:
        response = full_form(client, document, app_pin(PIN_SECRET, key))
        assert response.status_code == 303 and response.headers["location"] == "/app/home"
        assert f"{first_name} " in client.get("/app/home").text
        client.post("/app/logout")
    # The ID number can be typed the way it is printed.
    assert full_form(client, "31.415.926-8", MARTA_PIN).status_code == 303


def test_the_browser_remembers_the_last_customer_and_asks_for_the_pin_only(
    client: TestClient, repository: InMemoryRepository
) -> None:
    full_form(client, "358979327", app_pin(PIN_SECRET, "emma"))
    # The session ends without a log out: the app still knows whose it is.
    past = (utc_now() - timedelta(seconds=1)).isoformat()
    repository.update("app_sessions", {}, {"expires_at": past})
    page = client.get("/app?lang=en").text
    assert "Hello, Emma" in page and 'name="document"' not in page
    assert "Not Emma? Log in as someone else" in page
    assert 'href="/app?other=1&amp;next=%2Fapp%2Fhome"' in page
    other = client.get("/app?other=1").text
    assert 'name="document"' in other and "Emma" not in other
    emma_pin = {"u": seed_id("customer/emma"), "pin": app_pin(PIN_SECRET, "emma")}
    assert client.post("/app/login", data=emma_pin, follow_redirects=False).status_code == 303


def test_logging_out_returns_to_the_full_form(client: TestClient) -> None:
    sign_in(client)
    assert "Cerrar sesión" in client.get("/app/home").text
    response = client.post("/app/logout", follow_redirects=False)
    assert response.headers["location"] == "/app"
    page = client.get("/app").text
    assert 'name="document"' in page and "Marta" not in page


def test_the_full_form_never_says_which_part_was_wrong(
    client: TestClient, repository: InMemoryRepository
) -> None:
    unknown = full_form(client, "11.111.111-1", MARTA_PIN)
    wrong_pin = full_form(client, "314159268", WRONG_PIN)
    for response in (unknown, wrong_pin):
        assert response.status_code == 401 and "El documento o el PIN no coinciden" in response.text
        assert "Marta" not in response.text and 'name="document"' in response.text
    outcomes = [row["outcome"] for row in repository.select("audit_log")]
    assert outcomes[-2:] == ["app_login_unknown", "app_pin_wrong"]
    # Wrong PINs through the full form count towards the same lock.
    full_form(client, "314159268", WRONG_PIN)
    locked = full_form(client, "314159268", WRONG_PIN)
    assert locked.status_code == 429 and "Demasiados intentos" in locked.text
    assert full_form(client, "314159268", MARTA_PIN).status_code == 429


def test_a_link_from_the_bank_shows_only_a_first_name(client: TestClient) -> None:
    page = client.get(f"/app?u={MARTA_ID}")
    assert page.status_code == 200 and "Hola, Marta" in page.text
    assert "Rojas" not in page.text and "4821" not in page.text
    assert "¿No es Marta? Ingresar con otra persona" in page.text


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
    # A link for someone else does not open the app of whoever is signed in.
    assert "Hola, Marta" in client.get(f"/app?u={MARTA_ID}").text


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


def test_reloading_the_sign_in_or_sign_out_address_goes_back_to_the_sign_in_screen(
    client: TestClient,
) -> None:
    for address in ("/app/login", "/app/logout"):
        answer = client.get(address, follow_redirects=False)
        assert answer.status_code == 303 and answer.headers["location"] == "/app"
