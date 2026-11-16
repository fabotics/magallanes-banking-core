"""The seed script and the small helpers that other tests only touch in passing."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.audit import default_outcome, mask
from app.config import Settings
from app.email import mask_email, send_email
from app.messaging import send_telegram
from app.routers.registry import normalize_tax_id
from scripts.seed import print_counts, reset
from seed.data import TABLES
from seed.helpers import seed_id
from tests.conftest import API_KEY, MARTA
from tests.fake_db import InMemoryRepository


def test_reset_reloads_the_seed_and_unlocks_a_locked_customer(
    client: TestClient, repository: InMemoryRepository
) -> None:
    for _ in range(3):
        client.post("/v1/identity/verify", json={**MARTA, "birth_year": 1900}, headers=API_KEY)
    locked = client.post("/v1/identity/verify", json=MARTA, headers=API_KEY).json()
    repository.update("cards", {"last4": "4821"}, {"status": "blocked_temporary"})
    assert locked["locked"] is True

    reset(repository, demo_email="", demo_chat_id="")

    assert repository.select("verification_attempts") == []
    assert repository.select("audit_log") == []
    assert repository.select("cards", {"last4": "4821"})[0]["status"] == "active"
    assert len(repository.select("customers")) == 10
    assert client.post("/v1/identity/verify", json=MARTA, headers=API_KEY).json()["verified"]


def test_reset_gives_the_demo_contact_details_to_the_golden_path_customer(
    repository: InMemoryRepository,
) -> None:
    reset(repository, demo_email="demo@example.org", demo_chat_id="987654")
    marta = repository.select("customers", {"id": seed_id("customer/marta")})[0]
    assert marta["email"] == "demo@example.org" and marta["telegram_chat_id"] == "987654"
    others = [row for row in repository.select("customers") if row["id"] != marta["id"]]
    assert all(row["telegram_chat_id"] is None for row in others)


def test_print_counts_lists_every_table(
    repository: InMemoryRepository, capsys: pytest.CaptureFixture[str]
) -> None:
    print_counts(repository)
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines] == TABLES
    assert "customers                  10" in lines


def test_masks_keep_only_what_is_safe_to_show() -> None:
    assert mask("314159268") == "*****9268"
    assert mask("12") == "12"
    assert mask_email("marta.rojas@example.com") == "m***@example.com"
    assert mask_email("x@example.com") == "x***@example.com"


def test_tax_id_normalization_handles_edge_cases() -> None:
    assert normalize_tax_id("66.871.234-7") == "66871234-7"
    assert normalize_tax_id(" 66871234 k ") == "66871234-K"
    assert normalize_tax_id("7") == "7"
    assert normalize_tax_id("") == ""


def test_default_audit_outcome_follows_the_status_code() -> None:
    assert default_outcome(200) == "ok"
    assert default_outcome(401) == "denied" and default_outcome(403) == "denied"
    assert default_outcome(404) == "error" and default_outcome(500) == "error"


def test_nothing_is_sent_without_credentials() -> None:
    settings = Settings(_env_file=None)
    assert send_email(settings, "a@example.com", "Subject", "<p>Body</p>") is False
    assert send_telegram(settings, "42", "Hello") is False


def test_a_provider_error_is_reported_as_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    def rejected(url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", rejected)
    settings = Settings(_env_file=None, resend_api_key="key", telegram_bot_token="1:token")
    assert send_email(settings, "a@example.com", "Subject", "<p>Body</p>") is False
    assert send_telegram(settings, "42", "Hello") is False


def test_wrong_method_uses_the_error_shape(client: TestClient) -> None:
    response = client.get("/v1/identity/verify", headers=API_KEY)
    assert response.status_code == 405
    assert response.json()["error"] == "http_error" and "message" in response.json()
