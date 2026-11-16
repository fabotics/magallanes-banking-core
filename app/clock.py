"""Time helpers, so every module reads and writes timestamps the same way."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current time with the UTC timezone attached."""
    return datetime.now(UTC)


def parse_time(value: str) -> datetime:
    """Turn an ISO timestamp string, as stored in the database, into a datetime."""
    return datetime.fromisoformat(value)
