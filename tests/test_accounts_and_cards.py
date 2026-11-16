"""Read endpoints behind a verified session: profile, balances and card transactions."""

import pytest
from fastapi.testclient import TestClient

from app.clock import parse_time
from seed.movements import RESTAURANT_TAX_ID
from tests.conftest import API_KEY

READ_ENDPOINTS = ["/v1/customers/me", "/v1/accounts/balance", "/v1/cards/transactions"]


@pytest.mark.parametrize("path", READ_ENDPOINTS)
def test_no_session_means_no_data(client: TestClient, path: str) -> None:
    response = client.get(path, headers=API_KEY)
    assert response.status_code == 401
    assert response.json()["error"] == "identity_not_verified"


def test_profile_lists_what_the_customer_holds(client: TestClient, marta: dict) -> None:
    profile = client.get("/v1/customers/me", headers=marta).json()
    assert profile["first_name"] == "Marta" and profile["segment"] == "preferred"
    assert profile["country"] == "CL" and profile["is_vulnerable"] is False
    assert [product["kind"] for product in profile["products"]] == ["account", "account", "card"]
    assert profile["products"][2] == {
        "kind": "card",
        "name": "visa credit card ending 4821",
        "status": "active",
    }


def test_profile_never_exposes_contact_or_document_data(client: TestClient, marta: dict) -> None:
    text = client.get("/v1/customers/me", headers=marta).text
    assert "314159268" not in text and "@" not in text and "birth" not in text


def test_balances(client: TestClient, marta: dict) -> None:
    accounts = client.get("/v1/accounts/balance", headers=marta).json()["accounts"]
    assert [(a["type"], a["currency"], a["available_balance"]) for a in accounts] == [
        ("checking", "CLP", 1284500),
        ("savings", "CLP", 3150000),
    ]
    assert all(parse_time(a["as_of"]) for a in accounts)


def test_transactions_are_newest_first_and_only_the_customers(
    client: TestClient, marta: dict
) -> None:
    body = client.get("/v1/cards/transactions", headers=marta).json()
    times = [parse_time(t["transaction_at"]) for t in body["transactions"]]
    assert body["count"] == 7 and times == sorted(times, reverse=True)
    assert {t["card_last4"] for t in body["transactions"]} == {"4821"}


def test_restaurant_charge_shows_descriptor_and_tax_id_not_a_name(
    client: TestClient, marta: dict
) -> None:
    transactions = client.get("/v1/cards/transactions", headers=marta).json()["transactions"]
    charge = next(t for t in transactions if t["merchant_tax_id"])
    assert charge["descriptor"] == "MERPAGO*INVGASTRO PROV"
    assert charge["merchant_tax_id"] == RESTAURANT_TAX_ID
    assert charge["status"] == "posted" and charge["posted_at"] > charge["transaction_at"]
    assert "original_amount" not in charge and "merchant_name" not in charge


def test_status_filter_and_pending_shape(client: TestClient, marta: dict) -> None:
    pending = client.get("/v1/cards/transactions?status=pending", headers=marta).json()
    posted = client.get("/v1/cards/transactions?status=posted", headers=marta).json()
    assert pending["count"] == 1 and posted["count"] == 6
    assert pending["transactions"][0]["posted_at"] is None


def test_days_filter_and_foreign_currency_fields(client: TestClient, marta: dict) -> None:
    week = client.get("/v1/cards/transactions?days=7", headers=marta).json()
    assert 3 <= week["count"] < 7
    everything = client.get("/v1/cards/transactions", headers=marta).json()["transactions"]
    foreign = [t for t in everything if t["country"] != "CL"]
    assert len(foreign) == 1
    assert foreign[0]["original_amount"] == 9.99 and foreign[0]["original_currency"] == "USD"


def test_invalid_filters_are_rejected(client: TestClient, marta: dict) -> None:
    assert client.get("/v1/cards/transactions?days=0", headers=marta).status_code == 422
    assert client.get("/v1/cards/transactions?status=old", headers=marta).status_code == 422
