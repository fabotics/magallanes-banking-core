"""What the bank writes to the customer when a conversation ends without a summary.

An agent sends the summary before it says goodbye. A customer who hangs up
first would get nothing, so the caller's platform tells the bank when a
conversation is over, and the bank writes the summary itself, from its own
records of that conversation: cases opened, cards blocked, proposals sent and
policies taken out. It never repeats what was said, only what was recorded.
"""

from app import notices, signature
from app.clock import bank_date, parse_time, utc_now
from app.db import Repository, Row
from app.formatting import long_date

LINES = {
    "es": {
        "case": "Caso {number}: el equipo del banco lo contactará.",
        "block": "Su tarjeta terminada en {last4} quedó con un bloqueo temporal. "
        "Puede levantarlo en la app.",
        "proposal": "Su propuesta {number} está en la app para leer y firmar hasta el {until}. "
        "Nada queda contratado hasta que usted firme.",
        "policy": "Su póliza {number} quedó contratada.",
    },
    "en": {
        "case": "Case {number}: the bank's team will contact you.",
        "block": "Your card ending in {last4} has a temporary block. You can lift it in the app.",
        "proposal": "Your proposal {number} is in the app to read and sign until {until}. "
        "Nothing is taken out until you sign.",
        "policy": "Your policy {number} is now active.",
    },
}


def verified_customer(repository: Repository, conversation_id: str) -> Row | None:
    """Return the customer verified last in this conversation, if anyone was."""
    sessions = repository.select("verification_sessions", {"conversation_id": conversation_id})
    if not sessions:
        return None
    latest = max(sessions, key=lambda session: session["created_at"])
    return repository.select("customers", {"id": latest["customer_id"]})[0]


def already_sent(repository: Repository, conversation_id: str) -> bool:
    """Say whether a summary of this conversation already went to the customer."""
    rows = repository.select("audit_log", {"conversation_id": conversation_id})
    return any(row["outcome"] in ("summary_sent", "closing_summary_sent") for row in rows)


def recorded(repository: Repository, conversation_id: str, customer: Row, language: str) -> str:
    """Write one line for each thing the bank recorded for this customer in the conversation."""
    words = LINES[language]
    talk = {"conversation_id": conversation_id}
    lines = []
    for case in repository.select("cases", {**talk, "customer_id": customer["id"]}):
        lines.append(words["case"].format(number=case["case_number"]))
    for row in repository.select("audit_log", {**talk, "outcome": "card_blocked"}):
        lines.append(words["block"].format(last4=row["detail"].get("card_last4", "")))
    for offer in repository.select("insurance_offers", {**talk, "customer_id": customer["id"]}):
        for proposal in repository.select("proposals", {"offer_id": offer["id"]}):
            policy = signature.policy_for(repository, proposal)
            if policy:
                lines.append(words["policy"].format(number=policy["policy_number"]))
            elif signature.proposal_status(proposal, utc_now()) == "pending":
                last = bank_date(parse_time(proposal["created_at"]) + signature.PROPOSAL_LIFETIME)
                until = long_date(last, language)
                number = proposal["proposal_number"]
                lines.append(words["proposal"].format(number=number, until=until))
    return "\n".join(lines)


def summary(repository: Repository, conversation_id: str, customer: Row) -> str | None:
    """Return the message to send, or None when nothing was recorded for the customer."""
    language = notices.language_for(customer)
    lines = recorded(repository, conversation_id, customer, language)
    return f"{notices.chat(language, 'summary')}\n\n{lines}" if lines else None
