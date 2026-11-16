"""Proposals after they are sent: seen, signed, turned into a policy.

Both places where a customer can sign, the signing link and the bank's app,
call the same functions here, so a signature always has the same effects: the
proposal is marked signed, the policy is created with its number, the customer
gets the details in writing, and each step leaves an audit row.
"""

import secrets
from datetime import datetime, timedelta

from app import audit
from app.clock import bank_date, parse_time
from app.config import Settings
from app.db import Repository, Row
from app.email import policy_email, send_email
from app.formatting import long_date, money
from app.messaging import send_telegram

PROPOSAL_LIFETIME = timedelta(days=14)


def proposal_status(proposal: Row, now: datetime) -> str:
    """Return pending, signed or expired. A proposal can be signed for 14 days."""
    if proposal["status"] == "signed":
        return "signed"
    expired = parse_time(proposal["created_at"]) + PROPOSAL_LIFETIME <= now
    return "expired" if expired or proposal["status"] == "expired" else "pending"


def policy_for(repository: Repository, proposal: Row) -> Row | None:
    """Return the policy created when this proposal was signed, if it was."""
    policies = repository.select("policies", {"proposal_id": proposal["id"]})
    return policies[0] if policies else None


def mark_viewed(repository: Repository, proposal: Row, now: datetime, endpoint: str) -> Row:
    """Record the first time the customer opens the proposal."""
    if proposal["viewed_at"] is not None:
        return proposal
    values = {"viewed_at": now.isoformat()}
    proposal = repository.update("proposals", {"id": proposal["id"]}, values)[0]
    audit.record(
        repository, endpoint, "GET", proposal["customer_id"], "proposal_viewed",
        proposal_number=proposal["proposal_number"],
    )  # fmt: skip
    return proposal


def sign(
    repository: Repository,
    settings: Settings,
    proposal: Row,
    now: datetime,
    endpoint: str,
    **evidence: str,
) -> Row | None:
    """Sign a pending proposal and return the new policy. Anything else returns None.

    `evidence` goes into the audit row: the language the customer read, and
    the fingerprint of the document when a full contract was shown.
    """
    if proposal_status(proposal, now) != "pending" or proposal["signing_token"] is None:
        return None
    values = {"status": "signed", "signed_at": now.isoformat()}
    proposal = repository.update("proposals", {"id": proposal["id"]}, values)[0]
    policy = repository.insert(
        "policies",
        {
            "customer_id": proposal["customer_id"],
            "product_code": proposal["product_code"],
            "policy_number": f"PZ-{now.year}-{secrets.token_hex(3).upper()}",
            "proposal_id": proposal["id"],
            "status": "active",
            "started_at": now.isoformat(),
        },
    )
    audit.record(
        repository, endpoint, "POST", proposal["customer_id"], "proposal_signed",
        proposal_number=proposal["proposal_number"], policy_number=policy["policy_number"],
        **evidence,
    )  # fmt: skip
    confirm_in_writing(repository, settings, policy)
    return policy


def signing_record(repository: Repository, proposal: Row) -> Row:
    """Return what the audit trail recorded when this proposal was signed, or nothing."""
    filters = {"customer_id": proposal["customer_id"], "outcome": "proposal_signed"}
    for row in repository.select("audit_log", filters):
        if row["detail"].get("proposal_number") == proposal["proposal_number"]:
            return row["detail"]
    return {}


def confirm_in_writing(repository: Repository, settings: Settings, policy: Row) -> None:
    """Send the policy details by email and to the customer's messaging channel."""
    customer = repository.select("customers", {"id": policy["customer_id"]})[0]
    product = repository.select("insurance_products", {"code": policy["product_code"]})[0]
    start = long_date(bank_date(parse_time(policy["started_at"])))
    subject = f"Banco Magallanes: su póliza {policy['policy_number']}"
    send_email(settings, customer["email"], subject, policy_email(product, policy, start))
    if customer["telegram_chat_id"]:
        text = (
            "Banco Magallanes\n"
            f"Su seguro {product['name']} quedó contratado.\n\n"
            f"Póliza: {policy['policy_number']}\n"
            f"Vigente desde: {start}\n"
            f"Prima mensual: {money(product['monthly_premium'], product['currency'])}\n\n"
            "Puede darlo de baja en cualquier momento desde la app."
        )
        send_telegram(settings, customer["telegram_chat_id"], text)
