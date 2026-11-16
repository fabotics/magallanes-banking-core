"""Shared test fixtures. Tests never read `.env` and never touch the network."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.security import require_api_key

TEST_API_KEY = "test-key"


@pytest.fixture
def app() -> FastAPI:
    """A fresh app with fixed settings and one protected probe route for auth tests."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, bank_api_key=TEST_API_KEY
    )

    @app.get("/v1/probe", dependencies=[Depends(require_api_key)])
    def probe() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """An HTTP client that calls the app in process."""
    return TestClient(app)
