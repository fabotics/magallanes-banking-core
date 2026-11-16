"""The health check and the interactive docs are public."""

from fastapi.testclient import TestClient

from app import __version__
from app.config import get_settings
from app.main import create_app
from tests.conftest import fixed_settings
from tests.fake_db import InMemoryRepository


def test_health_reports_status_database_and_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "version": __version__}


def test_health_reports_not_configured_without_database_settings() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = fixed_settings
    assert TestClient(app).get("/health").json()["database"] == "not_configured"


def test_health_reports_unreachable_when_the_database_fails() -> None:
    class Broken(InMemoryRepository):
        def ping(self) -> bool:
            return False

    assert TestClient(create_app(Broken())).get("/health").json()["database"] == "unreachable"


def test_docs_page_loads_without_a_key(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
