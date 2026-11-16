"""Shared test fixtures. Tests never read `.env` and never touch the network."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from seed.data import build_seed
from tests.fake_db import InMemoryRepository

TEST_API_KEY = "test-key"
API_KEY = {"X-API-Key": TEST_API_KEY}
MARTA = {"document_number": "31.415.926-8", "card_last4": "4821", "birth_year": 1986}


def fixed_settings() -> Settings:
    """Fixed settings that ignore the real environment file."""
    return Settings(_env_file=None, bank_api_key=TEST_API_KEY, transactions_delay_seconds=0)


@pytest.fixture
def repository() -> InMemoryRepository:
    """An in-memory database loaded with the seed data."""
    return InMemoryRepository(build_seed())


@pytest.fixture
def app(repository: InMemoryRepository) -> FastAPI:
    """A fresh app on the in-memory repository."""
    app = create_app(repository)
    app.dependency_overrides[get_settings] = fixed_settings
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


@pytest.fixture
def marta(marta_token: str) -> dict[str, str]:
    """Headers for a call on behalf of the verified golden-path customer."""
    return {**API_KEY, "X-Session-Token": marta_token}
