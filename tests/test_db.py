"""The in-memory repository behaves like a small database, and health reports its state."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from seed.data import build_seed
from seed.helpers import seed_id
from tests.fake_db import InMemoryRepository


@pytest.fixture
def repository() -> InMemoryRepository:
    return InMemoryRepository(build_seed())


def test_select_filters_by_exact_match(repository: InMemoryRepository) -> None:
    rows = repository.select("customers", {"first_name": "Marta", "country": "CL"})
    assert [row["id"] for row in rows] == [seed_id("customer/marta")]
    assert repository.select("customers", {"first_name": "Nobody"}) == []


def test_results_are_copies(repository: InMemoryRepository) -> None:
    repository.select("customers")[0]["first_name"] = "Changed"
    assert "Changed" not in {row["first_name"] for row in repository.select("customers")}


def test_insert_fills_id_and_case_number(repository: InMemoryRepository) -> None:
    first = repository.insert("cases", {"type": "handoff", "summary": "Wants a person"})
    second = repository.insert("cases", {"type": "fraud", "summary": "Unknown charges"})
    assert first["id"] != second["id"]
    assert first["case_number"].startswith("MG-") and first["case_number"].endswith("-000001")
    assert second["case_number"].endswith("-000002")


def test_update_changes_only_matching_rows(repository: InMemoryRepository) -> None:
    updated = repository.update("cards", {"last4": "4821"}, {"status": "blocked_temporary"})
    assert len(updated) == 1 and updated[0]["status"] == "blocked_temporary"
    assert repository.select("cards", {"last4": "7730"})[0]["status"] == "active"


def test_delete_all_empties_one_table(repository: InMemoryRepository) -> None:
    repository.delete_all("transactions")
    assert repository.select("transactions") == []
    assert len(repository.select("customers")) == 10


def test_health_reports_ok_when_the_database_answers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "get_repository", lambda settings: InMemoryRepository())
    assert client.get("/health").json()["database"] == "ok"


def test_health_reports_unreachable_when_the_database_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Broken(InMemoryRepository):
        def ping(self) -> bool:
            return False

    monkeypatch.setattr(db, "get_repository", lambda settings: Broken())
    assert client.get("/health").json()["database"] == "unreachable"


def test_repository_requires_configuration() -> None:
    assert db.database_status(Settings(_env_file=None)) == "not_configured"
