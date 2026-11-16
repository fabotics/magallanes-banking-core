"""The in-memory repository behaves like a small database."""

import pytest

from app import db
from app.config import Settings
from app.errors import ApiError
from seed.helpers import seed_id
from tests.fake_db import InMemoryRepository


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
    assert len(repository.select("customers")) == 11


def test_repository_requires_configuration() -> None:
    with pytest.raises(ApiError) as raised:
        db.build_repository(Settings(_env_file=None))
    assert raised.value.status_code == 503
