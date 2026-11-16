"""The customer pages in English: the switch, every screen, and what a signature records."""

from datetime import date

from fastapi.testclient import TestClient

from app import contract_en, contract_es, contracts, quotes, texts_en, texts_es
from app.clock import bank_date, parse_time
from app.formatting import card_label, long_date, money
from seed.helpers import app_pin, seed_id
from tests.conftest import API_KEY, MARTA, PIN_SECRET
from tests.fake_db import InMemoryRepository

PIN = app_pin(PIN_SECRET, "marta")
MARTA_ID = seed_id("customer/marta")
APP = f"/app?u={MARTA_ID}"
SIGNATURE = {
    "initial_1": "yes", "initial_2": "yes", "initial_3": "yes", "initial_4": "yes",
    "signature_name": "Marta Rojas Fuentes", "accept": "yes",
}  # fmt: skip


def sign_in(client: TestClient, language: str = "en") -> TestClient:
    client.get(f"/app?lang={language}")
    client.post("/app/login", data={"u": MARTA_ID, "pin": PIN})
    return client


def proposal(client: TestClient, marta: dict) -> dict:
    offer = {"product_code": "CARD_FRAUD", "customer_response": "accepted"}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=marta).json()["offer_id"]
    body = {"offer_id": offer_id}
    return client.post("/v1/insurance/proposals", json=body, headers=marta).json()


def signed_detail(repository: InMemoryRepository) -> dict:
    return repository.select("audit_log", {"outcome": "proposal_signed"})[0]["detail"]


def test_both_languages_have_the_same_sentences_and_clauses() -> None:
    assert texts_es.TEXTS.keys() == texts_en.TEXTS.keys()
    spanish, english = contract_es.TEXT, contract_en.TEXT
    assert len(spanish["labels"]) == len(english["labels"])
    assert len(spanish["general"]) == len(english["general"])
    assert spanish["titles"].keys() == english["titles"].keys()
    for part in ("cover", "exclusions"):
        assert spanish[part].keys() == english[part].keys()
        for code in spanish[part]:
            assert len(spanish[part][code]) == len(english[part][code])
    assert english["products"].keys() == spanish["cover"].keys()


def test_spanish_is_the_default_and_the_link_can_ask_for_english(client: TestClient) -> None:
    spanish = client.get(APP)
    assert '<html lang="es">' in spanish.text and "Hola, Marta" in spanish.text
    # The switch is on the PIN screen, with a link for each language.
    home = "&amp;next=%2Fapp%2Fhome"
    assert f"{APP}{home}&amp;lang=es" in spanish.text
    assert f"{APP}{home}&amp;lang=en" in spanish.text
    english = client.get(f"{APP}&lang=en")
    assert '<html lang="en">' in english.text and "Hello, Marta" in english.text
    assert "Enter your four digit PIN" in english.text and "fictional bank" in english.text


def test_the_choice_lasts_for_the_visit_and_can_be_changed_back(client: TestClient) -> None:
    client.get("/app?lang=en")
    assert "Hello, Marta" in client.get(APP).text
    assert "Sign in to your bank" in client.get("/app").text
    assert "Hola, Marta" in client.get(f"{APP}&lang=es").text
    assert "Hola, Marta" in client.get(APP).text
    # A language the pages do not exist in changes nothing.
    assert "Hola, Marta" in client.get(f"{APP}&lang=fr").text


def test_the_switch_keeps_the_rest_of_the_link(client: TestClient) -> None:
    pedro = seed_id("customer/pedro")
    page = client.get(f"/app?u={pedro}&next=/app/proposals/PR-1").text
    assert f"/app?u={pedro}&amp;next=%2Fapp%2Fproposals%2FPR-1&amp;lang=en" in page


def test_pin_errors_and_the_lock_message_in_english(client: TestClient) -> None:
    client.get("/app?lang=en")
    wrong = "0000" if PIN != "0000" else "1111"
    first = client.post("/app/login", data={"u": MARTA_ID, "pin": wrong})
    assert first.status_code == 401 and "Wrong PIN" in first.text
    # The page answers a form, so its language links go back to the PIN screen.
    assert f"/app?u={seed_id('customer/marta')}&amp;next=%2Fapp%2Fhome&amp;lang=es" in first.text
    client.post("/app/login", data={"u": MARTA_ID, "pin": wrong})
    locked = client.post("/app/login", data={"u": MARTA_ID, "pin": wrong})
    form = client.post("/app/login", data={"document": "1-9", "pin": wrong})
    assert "The ID number or the PIN is not right" in form.text
    assert "/app?other=1&amp;next=%2Fapp%2Fhome&amp;lang=es" in form.text
    assert locked.status_code == 429 and "Too many attempts. Wait one minute" in locked.text
    assert client.get("/app?u=nobody").status_code == 404
    assert "App not available" in client.get("/app?u=nobody").text


def test_a_language_in_a_deep_link_survives_the_pin_screen(client: TestClient) -> None:
    response = client.get("/app/home?lang=en", follow_redirects=False)
    assert response.status_code == 303 and "mg_lang=en" in response.headers["set-cookie"]
    client.post("/app/login", data={"u": MARTA_ID, "pin": PIN})
    home = client.get("/app/home").text
    assert "You have no pending requests" in home and "Visa credit card ending in 4821" in home
    assert "Sign out" in home


def test_identity_confirmation_in_english(client: TestClient) -> None:
    sign_in(client)
    answers = {"approve": "Identity confirmed", "deny": "Request rejected"}
    for decision, result in answers.items():
        body = {"customer_id": MARTA["document_number"]}
        request_id = client.post("/v1/identity/push", json=body, headers=API_KEY).json()[
            "request_id"
        ]
        assert "Confirm identity" in client.get("/app/home").text
        page = client.get(f"/app/confirmations/{request_id}").text
        assert "Is this you?" in page and "Yes, it is me. Approve" in page
        done = client.post(f"/app/confirmations/{request_id}", data={"decision": decision})
        assert result in done.text and "Back to home" in done.text
    missing = client.get("/app/confirmations/00000000-0000-4000-8000-000000000000")
    assert "Not available" in missing.text


def test_the_contract_is_fully_in_english(client: TestClient, marta: dict) -> None:
    number = proposal(sign_in(client), marta)["proposal_number"]
    assert "Card protection and assistance" in client.get("/app/home").text
    page = client.get(f"/app/proposals/{number}").text
    for expected in (
        "Review and sign your proposal", "Insurance proposal", "Card protection and assistance",
        "CLP 2,690", "Visa credit card ending in 4821", "Policyholder and intermediary",
        "Cash stolen after a withdrawal", "Quote No.", "CLP 500,000", "Exclusions",
        "Right of withdrawal", "Early termination",
        "Electronic signature", f"Proposal {number} · Page 4 of 4", 'data-label="Initials"',
        "Click to sign", "Sign and take out the policy", 'name="lang" value="en"',
    ):  # fmt: skip
        assert expected in page
    for spanish in ("Coberturas", "Derecho de retracto", "Protección de tarjeta", "Firmar"):
        assert spanish not in page
    incomplete = client.post(f"/app/proposals/{number}", data={**SIGNATURE, "accept": ""})
    assert incomplete.status_code == 422 and "final confirmation is not ticked" in incomplete.text


def test_a_signature_records_the_language_and_the_fingerprint_of_what_was_shown(
    client: TestClient,
    repository: InMemoryRepository,
    marta: dict,
    with_bot: None,
    telegram: list[dict],
) -> None:
    number = proposal(sign_in(client), marta)["proposal_number"]
    done = client.post(f"/app/proposals/{number}", data={**SIGNATURE, "lang": "en"})
    detail = signed_detail(repository)
    assert "Signature received" in done.text and "Document fingerprint" in done.text
    assert detail["language"] == "en" and len(detail["document_hash"]) == 64
    assert detail["document_hash"][:16] in done.text
    # The confirmation is written in the language she read and signed in.
    text = telegram[-1]["json"]["text"]
    assert "Your Card protection and assistance insurance is now active" in text
    assert "In force from" in text and "Monthly premium: CLP 2,690" in text


def test_the_fingerprint_is_of_the_wording_in_that_language(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    number = proposal(sign_in(client), marta)["proposal_number"]
    # The visit is in English, but this form was shown in Spanish: Spanish is what was read.
    client.post(f"/app/proposals/{number}", data={**SIGNATURE, "lang": "es"})
    detail = signed_detail(repository)
    stored = repository.select("proposals")[0]
    customer = repository.select("customers", {"id": stored["customer_id"]})[0]
    product = quotes.for_proposal(repository, stored)
    card = repository.select("cards", {"customer_id": customer["id"]})[0]
    issued = bank_date(parse_time(stored["created_at"]))
    prints = {
        language: contracts.fingerprint(
            contracts.build(language, stored, product, customer, card, issued)
        )
        for language in ("es", "en")
    }
    assert detail["language"] == "es" and detail["document_hash"] == prints["es"]
    assert prints["es"] != prints["en"]


def test_the_signing_link_in_english(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    link = proposal(client, marta)["signing_url"].removeprefix("http://localhost:8000")
    spanish = client.get(link).text
    assert "Firmar propuesta" in spanish and f"{link}?lang=en" in spanish
    english = client.get(f"{link}?lang=en").text
    assert "Sign proposal" in english and "Card protection and assistance" in english
    assert "CLP 2,690" in english and "Monthly premium" in english
    signed = client.post(link)
    assert "Proposal signed. Your insurance is now active." in signed.text
    assert signed_detail(repository)["language"] == "en"
    assert "Link not valid" in client.get("/sign/nope").text


def test_amounts_dates_and_cards_for_an_english_reader() -> None:
    assert money(2990, "CLP", "en") == "CLP 2,990"
    assert money(12.5, "PEN", "en") == "PEN 12.50"
    assert long_date(date(2026, 11, 16), "en") == "16 November 2026"
    card = {"brand": "mastercard", "type": "debit", "last4": "3378"}
    assert card_label(card, "en") == "Mastercard debit card ending in 3378"
    assert card_label(card) == "tarjeta Mastercard de débito terminada en 3378"
