"""Metrics for the operations dashboard, computed from the bank core's own tables.

Everything here is plain Python over rows read through the repository, so it
can be tested without a database and without the dashboard framework.

A "conversation" is every API call that shares one `conversation_id` in the
audit log. A conversation counts as escalated when a case was opened in it,
and as resolved by the agent when the customer was verified and no case was
needed.
"""

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from app.clock import parse_time, utc_now
from app.db import Repository, Row

TABLES = ["audit_log", "cases", "insurance_offers", "proposals"]
TIME_COLUMN = {"audit_log": "at"}


def load_rows(repository: Repository, days: int | None = None) -> dict[str, list[Row]]:
    """Read the tables the dashboard needs, keeping only the last `days` days when given."""
    since = utc_now() - timedelta(days=days) if days else None
    rows = {}
    for table in TABLES:
        column = TIME_COLUMN.get(table, "created_at")
        rows[table] = [row for row in repository.select(table) if is_recent(row[column], since)]
    return rows


def is_recent(timestamp: str, since: datetime | None) -> bool:
    """Return True when there is no cut-off or the timestamp is after it."""
    return since is None or parse_time(timestamp) >= since


def share(part: int, whole: int) -> float:
    """Return part divided by whole as a percentage with one decimal, or 0 when whole is 0."""
    return round(100 * part / whole, 1) if whole else 0.0


def conversation_ids(rows: list[Row], outcome: str | None = None) -> set[str]:
    """Return the conversation ids present in the rows, optionally only for one audit outcome."""
    return {
        row["conversation_id"]
        for row in rows
        if row["conversation_id"] and (outcome is None or row.get("outcome") == outcome)
    }


def compute_metrics(rows: dict[str, list[Row]]) -> dict[str, Any]:
    """Turn raw rows into the numbers the dashboard shows."""
    audit, cases, offers = rows["audit_log"], rows["cases"], rows["insurance_offers"]
    proposals = rows["proposals"]

    conversations = conversation_ids(audit)
    verified = conversation_ids(audit, "verified")
    escalated = conversation_ids(cases)
    resolved = verified - escalated

    answers = Counter(offer["customer_response"] for offer in offers)
    signed = sum(1 for proposal in proposals if proposal["status"] == "signed")
    return {
        "conversations": len(conversations),
        "verified": len(verified),
        "verification_rate": share(len(verified), len(conversations)),
        "locked": len(conversation_ids(audit, "locked")),
        "resolved": len(resolved),
        "resolution_rate": share(len(resolved), len(conversations)),
        "escalated": len(escalated & conversations),
        "escalation_rate": share(len(escalated & conversations), len(conversations)),
        "cases_total": len(cases),
        "cases_by_type": dict(Counter(case["type"] for case in cases)),
        "cards_blocked": sum(1 for row in audit if row["outcome"] == "card_blocked"),
        "offers_made": len(offers),
        "offer_rate": share(len(conversation_ids(offers)), len(verified)),
        "offers_by_answer": dict(answers),
        "acceptance_rate": share(answers["accepted"], len(offers)),
        "proposals_sent": len(proposals),
        "proposals_signed": signed,
        "signing_rate": share(signed, answers["accepted"]),
    }


def recent_cases(rows: dict[str, list[Row]], limit: int = 10) -> list[Row]:
    """Return the newest cases with only the columns that are safe to show on a wall screen."""
    newest = sorted(rows["cases"], key=lambda case: parse_time(case["created_at"]), reverse=True)
    columns = ["case_number", "type", "priority", "status", "created_at"]
    return [{column: case[column] for column in columns} for case in newest[:limit]]
