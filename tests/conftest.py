"""Shared test fixtures. Tests never read `.env` and never touch the network."""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import Row
from app.main import create_app
from app.security import session_from_request
from seed.data import build_seed
from tests.fake_db import InMemoryRepository

TEST_API_KEY = "test-key"
API_KEY = {"X-API-Key": TEST_API_KEY}
MARTA = {"document_number": "31.415.926-8", "card_last4": "4821", "birth_year": 1986}


def fixed_settings() -> Settings:
    """Fixed settings that ignore the real environment file."""
    return Settings(_env_file=None, bank_api_key=TEST_API_KEY)


@pytest.fixture
def repository() -> InMemoryRepository:
    """An in-memory database loaded with the seed data."""
    return InMemoryRepository(build_seed())


@pytest.fixture
def app(repository: InMemoryRepository) -> FastAPI:
    """A fresh app on the in-memory repository, plus one probe route for session tests."""
    app = create_app(repository)
    app.dependency_overrides[get_settings] = fixed_settings

    @app.get("/v1/session-probe")
    def session_probe(session: Annotated[Row, Depends(session_from_request)]) -> dict[str, str]:
        return {"customer_id": session["customer_id"]}

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """An HTTP client that calls the app in process."""
    return TestClient(app)


@pytest.fixture
def marta_token(client: TestClient) -> str:
    """A valid session token for the golden-path customer."""
    body = {**MARTA, "conversation_id": "conv-test"}
    return client.post("/v1/identity/verify", json=body, headers=API_KEY).json()["session_token"]
