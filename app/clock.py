"""Time helpers, so every module reads and writes timestamps the same way."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

# Dates the customer sees, such as the start of a policy, are dates at the bank.
BANK_TIMEZONE = ZoneInfo("America/Santiago")


def utc_now() -> datetime:
    """Return the current time with the UTC timezone attached."""
    return datetime.now(UTC)


def parse_time(value: str) -> datetime:
    """Turn an ISO timestamp string, as stored in the database, into a datetime."""
    return datetime.fromisoformat(value)


def bank_date(moment: datetime) -> date:
    """Return the calendar date of a moment at the bank, not in UTC."""
    return moment.astimezone(BANK_TIMEZONE).date()
