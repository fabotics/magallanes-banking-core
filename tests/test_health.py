"""The health check and the interactive docs are public."""

from fastapi.testclient import TestClient

from app import __version__


def test_health_reports_status_database_and_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "not_configured",
        "version": __version__,
    }


def test_docs_page_loads_without_a_key(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
