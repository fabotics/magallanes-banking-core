"""The bank's brand on the customer pages: icons, web manifest, tab titles and the lockup."""

import pytest
from fastapi.testclient import TestClient

from app import i18n
from app.routers import brand
from seed.helpers import app_pin, seed_id
from tests.conftest import PIN_SECRET

MARTA_ID = seed_id("customer/marta")
PNG_START = b"\x89PNG\r\n\x1a\n"


def sign_in(client: TestClient, language: str) -> TestClient:
    client.get(f"/app?lang={language}")
    client.post("/app/login", data={"u": MARTA_ID, "pin": app_pin(PIN_SECRET, "marta")})
    return client


def title(html: str) -> str:
    return html.split("<title>")[1].split("</title>")[0]


@pytest.mark.parametrize(("name", "media_type"), brand.FILES.items())
def test_every_icon_is_served_at_the_root_with_its_type(
    client: TestClient, name: str, media_type: str
) -> None:
    response = client.get(f"/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == media_type
    assert response.content == (brand.FOLDER / name).read_bytes()
    assert response.headers["cache-control"] == "public, max-age=86400"
    if name.endswith(".png"):
        assert response.content.startswith(PNG_START)


def test_the_icons_need_no_key_and_stay_out_of_the_api_docs(client: TestClient) -> None:
    assert client.get("/favicon.ico").status_code == 200
    assert not set(client.get("/openapi.json").json()["paths"]) & {f"/{n}" for n in brand.FILES}


def test_the_manifest_names_the_bank_and_only_icons_that_exist(client: TestClient) -> None:
    manifest = client.get("/site.webmanifest").json()
    assert manifest["name"] == "Banco Magallanes"
    assert manifest["theme_color"] == "#0B2530"
    assert [icon.get("purpose") for icon in manifest["icons"]] == [None, None, "maskable"]
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_every_page_links_the_icons_and_carries_the_colour_tokens(client: TestClient) -> None:
    for address in ("/app", "/sign/nope"):
        html = client.get(address).text
        assert '<link rel="icon" href="/favicon.ico" sizes="48x48">' in html
        assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml">' in html
        assert '<link rel="apple-touch-icon" href="/apple-touch-icon.png">' in html
        assert '<link rel="manifest" href="/site.webmanifest">' in html
        assert "--bm-deep: #0B2530" in html and "--bm-copper: #C2622A" in html
        assert "<small>Banco</small>Magallanes" in html


@pytest.mark.parametrize("language", ["es", "en"])
def test_the_tab_title_is_the_bank_and_the_screen_in_the_page_language(
    client: TestClient, language: str
) -> None:
    words = i18n.TEXTS[language]
    pages = {f"/app?lang={language}": "login_title", "/sign/nope": "link_title"}
    for address, key in pages.items():
        assert title(client.get(address).text) == f"Banco Magallanes | {words[key]}"
    sign_in(client, language)
    assert title(client.get("/app/home").text) == f"Banco Magallanes | {words['home_title']}"
    assert words["login_title"] == {"es": "Ingreso", "en": "Sign in"}[language]


def test_the_first_page_of_the_contract_carries_the_lockup(
    client: TestClient, marta: dict[str, str]
) -> None:
    offer = {"product_code": "CARD_FRAUD", "customer_response": "accepted"}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=marta).json()["offer_id"]
    number = client.post(
        "/v1/insurance/proposals", json={"offer_id": offer_id}, headers=marta
    ).json()["proposal_number"]
    html = sign_in(client, "en").get(f"/app/proposals/{number}").text
    assert title(html) == f"Banco Magallanes | Proposal {number}"
    first_sheet = html.split('<section class="sheet">')[1]
    assert 'class="lockup"' in first_sheet and html.count('class="lockup"') == 1
