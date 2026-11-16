"""Every `/v1` call leaves one audit row, and no row holds a secret."""

import json

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import Row
from app.main import create_app
from seed.helpers import seed_id
from tests.conftest import API_KEY, MARTA, fixed_settings
from tests.fake_db import InMemoryRepository


def test_a_verified_call_is_recorded_with_customer_and_conversation(
    client: TestClient, repository: InMemoryRepository, marta_token: str
) -> None:
    rows = repository.select("audit_log")
    assert len(rows) == 1
    row = rows[0]
    assert row["endpoint"] == "/v1/identity/verify" and row["method"] == "POST"
    assert row["customer_id"] == seed_id("customer/marta")
    assert row["conversation_id"] == "conv-test"
    assert row["outcome"] == "verified"
    assert row["detail"] == {"status_code": 200, "document": "*****9268"}


def test_no_secret_reaches_the_audit_log(
    client: TestClient, repository: InMemoryRepository, marta_token: str
) -> None:
    client.get(f"/v1/session-probe?session_token={marta_token}", headers=API_KEY)
    stored = json.dumps(repository.select("audit_log"))
    assert marta_token not in stored
    assert "314159268" not in stored
    assert API_KEY["X-API-Key"] not in stored


def test_failed_and_denied_calls_are_recorded(
    client: TestClient, repository: InMemoryRepository
) -> None:
    client.post("/v1/identity/verify", json={**MARTA, "birth_year": 1900}, headers=API_KEY)
    client.post("/v1/identity/verify", json=MARTA)
    outcomes = [row["outcome"] for row in repository.select("audit_log")]
    assert outcomes == ["failed", "denied"]


def test_session_calls_carry_the_customer(
    client: TestClient, repository: InMemoryRepository, marta_token: str
) -> None:
    client.get("/v1/session-probe", headers={**API_KEY, "X-Session-Token": marta_token})
    row = repository.select("audit_log")[-1]
    assert row["customer_id"] == seed_id("customer/marta")
    assert row["conversation_id"] == "conv-test" and row["outcome"] == "ok"


def test_health_is_not_audited(client: TestClient, repository: InMemoryRepository) -> None:
    client.get("/health")
    assert repository.select("audit_log") == []


def test_a_failed_audit_write_does_not_break_the_response() -> None:
    class NoAudit(InMemoryRepository):
        def insert(self, table: str, row: Row) -> Row:
            if table == "audit_log":
                raise RuntimeError("audit table unavailable")
            return super().insert(table, row)

    app = create_app(NoAudit())
    app.dependency_overrides[get_settings] = fixed_settings
    response = TestClient(app).post("/v1/identity/verify", json=MARTA, headers=API_KEY)
    assert response.status_code == 200
