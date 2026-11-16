"""Merchant registry: the tax ID on a statement becomes a business name."""

import pytest
from fastapi.testclient import TestClient

from seed.movements import RESTAURANT_TAX_ID
from tests.conftest import API_KEY
from tests.fake_db import InMemoryRepository


@pytest.mark.parametrize("written", [RESTAURANT_TAX_ID, "66.871.234-7", "668712347"])
def test_lookup_accepts_any_common_format(client: TestClient, written: str) -> None:
    response = client.get(f"/v1/registry/merchants/{written}", headers=API_KEY)
    assert response.status_code == 200
    assert response.json() == {
        "tax_id": "66871234-7",
        "legal_name": "Inversiones Gastronomicas Providencia SpA",
        "trade_name": "Restaurante El Mirador",
        "activity": "Restaurant",
        "address": "Avenida Los Aromos 245",
        "commune": "Providencia",
    }


def test_the_golden_path_charge_resolves_to_a_business(client: TestClient, marta: dict) -> None:
    transactions = client.get("/v1/cards/transactions", headers=marta).json()["transactions"]
    tax_id = next(t["merchant_tax_id"] for t in transactions if t["merchant_tax_id"])
    merchant = client.get(f"/v1/registry/merchants/{tax_id}", headers=API_KEY).json()
    assert merchant["trade_name"] == "Restaurante El Mirador"


def test_unknown_tax_id_is_a_404_in_the_error_shape(client: TestClient) -> None:
    response = client.get("/v1/registry/merchants/11111111-1", headers=API_KEY)
    assert response.status_code == 404 and response.json()["error"] == "merchant_not_found"


def test_lookup_needs_the_api_key_but_no_session(client: TestClient) -> None:
    assert client.get(f"/v1/registry/merchants/{RESTAURANT_TAX_ID}").status_code == 401


def test_lookups_are_audited(client: TestClient, repository: InMemoryRepository) -> None:
    client.get(f"/v1/registry/merchants/{RESTAURANT_TAX_ID}", headers=API_KEY)
    client.get("/v1/registry/merchants/11111111-1", headers=API_KEY)
    outcomes = [row["outcome"] for row in repository.select("audit_log")]
    assert outcomes == ["merchant_found", "merchant_not_found"]
