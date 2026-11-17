"""Identity verification: sessions, generic failures and the lockout rule."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.clock import parse_time, utc_now
from seed.helpers import seed_id
from tests.conftest import API_KEY, MARTA
from tests.fake_db import InMemoryRepository

URL = "/v1/identity/verify"


def verify(client: TestClient, **changes: object) -> dict:
    response = client.post(URL, json={**MARTA, **changes}, headers=API_KEY)
    assert response.status_code == 200
    return response.json()


def test_correct_details_open_a_15_minute_session(
    client: TestClient, repository: InMemoryRepository
) -> None:
    result = verify(client, conversation_id="conv-1")
    overview = result.pop("overview")
    assert result.pop("review_route") == "review"
    assert result == {
        "verified": True,
        "locked": False,
        "session_token": result["session_token"],
        "first_name": "Marta",
    }
    # The profile and the movements come with the verification: no second and third call.
    assert overview["customer"]["first_name"] == "Marta" and overview["turn_1"][0]["count"] == 4
    session = repository.select("verification_sessions", {"token": result["session_token"]})[0]
    assert session["customer_id"] == seed_id("customer/marta")
    assert session["conversation_id"] == "conv-1"
    lifetime = parse_time(session["expires_at"]) - parse_time(session["created_at"])
    assert lifetime == timedelta(minutes=15)


def test_document_format_does_not_matter(client: TestClient) -> None:
    assert verify(client, document_number="314159268")["verified"] is True
    assert verify(client, document_number=" 31415926-8 ")["verified"] is True


@pytest.mark.parametrize(
    "changes",
    [{"card_last4": "0000"}, {"birth_year": 1990}, {"document_number": "11.111.111-1"}],
)
def test_any_mismatch_gives_the_same_answer(client: TestClient, changes: dict) -> None:
    assert verify(client, **changes) == {
        "verified": False,
        "locked": False,
        "attempts_remaining": 2,
    }


def test_three_failures_lock_even_correct_details(client: TestClient) -> None:
    assert verify(client, birth_year=1900)["attempts_remaining"] == 2
    assert verify(client, birth_year=1900)["attempts_remaining"] == 1
    assert verify(client, birth_year=1900) == {
        "verified": False,
        "locked": True,
        "attempts_remaining": 0,
    }
    assert verify(client)["locked"] is True
    assert "session_token" not in verify(client)


def test_lock_is_per_document(client: TestClient) -> None:
    for _ in range(3):
        verify(client, birth_year=1900)
    other = {"document_number": "32718281-1", "card_last4": "7730", "birth_year": 1979}
    assert verify(client, **other)["verified"] is True


def test_failures_older_than_the_window_do_not_count(
    client: TestClient, repository: InMemoryRepository
) -> None:
    long_ago = (utc_now() - timedelta(minutes=16)).isoformat()
    for _ in range(3):
        repository.insert(
            "verification_attempts",
            {"document_number": "314159268", "success": False, "created_at": long_ago},
        )
    assert verify(client)["verified"] is True


def test_a_success_resets_the_failure_count(client: TestClient) -> None:
    verify(client, birth_year=1900)
    verify(client, birth_year=1900)
    assert verify(client)["verified"] is True
    assert verify(client, birth_year=1900)["attempts_remaining"] == 2
