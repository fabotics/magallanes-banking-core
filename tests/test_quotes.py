"""Quotes: the bank's rules price the product, and the number follows the sale."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app import quotes
from app.clock import parse_time, utc_now
from tests.fake_db import InMemoryRepository

PRODUCT = {"code": "CARD_FRAUD", "monthly_premium": 2990, "currency": "CLP"}
TODAY = date(2026, 11, 16)


def person(segment: str, birth_date: str = "1986-03-14") -> dict:
    return {"segment": segment, "birth_date": birth_date}


def test_the_segment_and_the_age_set_the_premium() -> None:
    assert quotes.premium_for(PRODUCT, person("mass"), TODAY) == 2990
    assert quotes.premium_for(PRODUCT, person("preferred"), TODAY) == 2690
    assert quotes.premium_for(PRODUCT, person("premium"), TODAY) == 2540
    assert quotes.premium_for(PRODUCT, person("mass", "1948-05-09"), TODAY) == 3440


def test_age_counts_whole_years() -> None:
    assert quotes.age_on("1961-11-17", TODAY) == 64 and quotes.age_on("1961-11-16", TODAY) == 65


def test_asking_again_returns_the_same_quote_until_it_expires(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    first = client.get("/v1/insurance/eligibility", headers=marta).json()["products"][0]
    again = client.get("/v1/insurance/eligibility", headers=marta).json()["products"][0]
    assert first["quote_number"].startswith("CT-") and first == again
    row = repository.select("quotes", {"quote_number": first["quote_number"]})[0]
    assert parse_time(row["valid_until"]) - parse_time(row["created_at"]) == timedelta(days=15)
    past = (utc_now() - timedelta(minutes=1)).isoformat()
    repository.update("quotes", {"id": row["id"]}, {"valid_until": past})
    renewed = client.get("/v1/insurance/eligibility", headers=marta).json()["products"][0]
    assert renewed["quote_number"] != first["quote_number"]


def test_the_quote_number_travels_to_the_offer_the_proposal_and_the_contract(
    client: TestClient, repository: InMemoryRepository, marta: dict
) -> None:
    quoted = client.get("/v1/insurance/eligibility", headers=marta).json()["products"][0]
    offer = {"product_code": "CARD_FRAUD", "customer_response": "accepted"}
    offer_id = client.post("/v1/insurance/offers", json=offer, headers=marta).json()["offer_id"]
    sent = client.post("/v1/insurance/proposals", json={"offer_id": offer_id}, headers=marta).json()
    assert sent["quote_number"] == quoted["quote_number"]
    assert repository.select("insurance_offers")[0]["quote_number"] == quoted["quote_number"]
    page = client.get(sent["signing_url"].removeprefix("http://localhost:8000")).text
    assert "$2.690" in page and "$2.990" not in page


def test_a_product_without_a_quote_keeps_the_catalog_price(repository: InMemoryRepository) -> None:
    product = repository.select("insurance_products", {"code": "CARD_FRAUD"})[0]
    priced = quotes.priced(repository, product, None)
    assert priced["monthly_premium"] == 2990 and priced["coverage_limit"] is None
