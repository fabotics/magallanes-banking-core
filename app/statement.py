"""Card movements as the customer would say them: local days and times, and repeats grouped.

The database keeps moments in UTC. A caller that talks to the customer should
never work out a weekday or a local hour by itself, so each movement carries
them ready-made, in the bank's time zone. Charges that share a descriptor are
also counted and added up here, so the caller reads the total instead of
computing it.
"""

from datetime import datetime

from app.clock import BANK_TIMEZONE, parse_time
from app.formatting import long_date

TIMEZONE_NAME = str(BANK_TIMEZONE)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def at_the_bank(moment: str) -> datetime:
    """Return a stored moment as a time on the bank's clock."""
    return parse_time(moment).astimezone(BANK_TIMEZONE)


def day_in_words(moment: str | None) -> str | None:
    """Write the bank-time day of a moment: `Saturday 14 November 2026`."""
    if moment is None:
        return None
    local = at_the_bank(moment)
    return f"{WEEKDAYS[local.weekday()]} {long_date(local.date(), 'en')}"


def clock_12(hour_minute: str) -> str:
    """Write a 24 hour time the way it is said: `20:55` becomes `8:55 pm`."""
    hour, minute = (int(part) for part in hour_minute.split(":"))
    return f"{hour % 12 or 12}:{minute:02d} {'am' if hour < 12 else 'pm'}"


def local_fields(row: dict) -> dict:
    """Return the moments of one movement in bank time, with the day and hour in words."""
    posted = row["posted_at"]
    return {
        "transaction_at": at_the_bank(row["transaction_at"]).isoformat(),
        "posted_at": at_the_bank(posted).isoformat() if posted else None,
        "purchased_on": day_in_words(row["transaction_at"]),
        "purchased_time": at_the_bank(row["transaction_at"]).strftime("%H:%M"),
        "posted_on": day_in_words(posted),
    }


def repeated_charges(movements: list[dict]) -> list[dict]:
    """Group the movements that share a descriptor, when there are two or more of them.

    Each group says how many charges, their total, the day and the first and
    last hour they were made, and the day the bank posted them.
    """
    by_descriptor: dict[str, list[dict]] = {}
    for movement in movements:
        by_descriptor.setdefault(movement["descriptor"], []).append(movement)
    groups = []
    for descriptor, charges in by_descriptor.items():
        if len(charges) < 2:
            continue
        charges = sorted(charges, key=lambda charge: charge["transaction_at"])
        days = list(dict.fromkeys(charge["purchased_on"] for charge in charges))
        posted = list(dict.fromkeys(c["posted_on"] for c in charges if c["posted_on"]))
        groups.append(
            {
                "descriptor": descriptor,
                "merchant_tax_id": charges[0]["merchant_tax_id"],
                "count": len(charges),
                "total": sum(charge["amount"] for charge in charges),
                "currency": charges[0]["currency"],
                "purchased_on": days,
                "first_time": charges[0]["purchased_time"],
                "last_time": charges[-1]["purchased_time"],
                "posted_on": posted,
            }
        )
    return groups
