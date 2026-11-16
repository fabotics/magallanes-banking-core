"""Fill the CRM with a believable funnel of fictional customers, or take it out again.

Usage:
    python scripts/crm_seed.py            create or refresh about 400 customers
    python scripts/crm_seed.py --wipe     delete every seeded record

Each customer is a Contact with a Lead and an Opportunity for the card cover.
The opportunities are spread over the stages of the sale and over the last 90
days. Everyone is invented: names are drawn from two lists, document numbers
use a range that has not been issued, and nobody has an email or a phone.
Every record carries Seeded = true and the lead source Voice agent. Running
it again updates the same records: each one is found by its external ID.
"""

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Make `app` importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import crm, crm_sync  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from seed.helpers import rut  # noqa: E402

PRODUCT = "Protección de tarjeta y asistencia"
# The monthly premium of each segment: mass, preferred, premium.
PREMIUMS = (11990, 10790, 10190)
# stage, share of the customers, lead status
STAGES = (
    ("Closed Lost", 0.35, "Closed - Not Converted"),
    ("Offered", 0.30, "Open - Not Contacted"),
    ("Proposal Sent", 0.15, "Working - Contacted"),
    ("Closed Won", 0.20, "Working - Contacted"),
)
REASONS = ("Not interested",) * 9 + ("Price",) * 6 + ("Already insured",) * 3 + ("Other",) * 2
FIRST_NAMES = (
    "Camila Valentina Javiera Francisca Antonia Constanza Catalina Fernanda Daniela Macarena "
    "Paula Carolina Bárbara Isidora Josefa Matías Benjamín Vicente Martín Sebastián Felipe "
    "Cristóbal Joaquín Ignacio Tomás Nicolás Diego Rodrigo Gonzalo Álvaro Claudio Patricio"
).split()
LAST_NAMES = (
    "González Muñoz Rojas Díaz Pérez Soto Contreras Silva Martínez Sepúlveda Morales Rodríguez "
    "López Fuentes Hernández Torres Araya Flores Espinoza Valenzuela Castillo Tapia Reyes "
    "Gutiérrez Castro Pizarro Álvarez Vásquez Sánchez Fernández Ramírez Carrasco Gómez Cortés"
).split()
CITIES = ("Santiago", "Providencia", "Ñuñoa", "Maipú", "Valparaíso", "Concepción", "Temuco")
BATCH = 200


def people(count: int, today: date) -> list[dict]:
    """Invent the customers, always the same ones, with where each sale stands."""
    dice = random.Random(2026)
    stages = [stage for stage in STAGES for _ in range(round(count * stage[1]))]
    rows = []
    for number, (stage, _, lead_status) in enumerate(stages[:count], start=1):
        closed = stage.startswith("Closed")
        # Sales that are still open were offered in the last two weeks: a quote lasts 15 days.
        offered = today - timedelta(days=dice.randint(0, 89 if closed else 13))
        rows.append({
            "key": f"seed-{number:04d}",
            "document": rut(30_000_000 + dice.randint(0, 4_999_999), hyphen=True),
            "first": dice.choice(FIRST_NAMES),
            "last": f"{dice.choice(LAST_NAMES)} {dice.choice(LAST_NAMES)}",
            "city": dice.choice(CITIES),
            "stage": stage,
            "lead_status": lead_status,
            "amount": dice.choice(PREMIUMS) * 12,
            "close": offered if closed else offered + timedelta(days=15),
            "reason": dice.choice(REASONS) if stage == "Closed Lost" else None,
            "proposal": f"PR-{offered.year}-{dice.randrange(16**6):06X}",
            "policy": f"PZ-{offered.year}-{dice.randrange(16**6):06X}",
        })  # fmt: skip
    return rows


def records(person: dict, account: str) -> tuple[dict, dict, dict]:
    """Shape one invented customer as a Contact, a Lead and an Opportunity."""
    mark = {"LeadSource": crm_sync.SOURCE, "Seeded__c": True}
    name = {"FirstName": person["first"], "LastName": person["last"]}
    contact = {**name, **mark, "Customer_Reference__c": person["document"], "AccountId": account,
               "MailingCity": person["city"], "MailingCountry": "Chile"}  # fmt: skip
    lead = {**name, **mark, "Offer_Reference__c": person["key"], "Company": PRODUCT,
            "Status": person["lead_status"], "City": person["city"]}  # fmt: skip
    sent = person["stage"] in ("Proposal Sent", "Closed Won")
    deal = {
        **mark,
        "Offer_Reference__c": person["key"],
        "Name": f"{PRODUCT} - {person['first']} {person['last']}",
        "AccountId": account,
        "StageName": person["stage"],
        "Amount": person["amount"],
        "CloseDate": person["close"].isoformat(),
        "Loss_Reason__c": person["reason"],
        "Proposal_Number__c": person["proposal"] if sent else None,
        "Policy_Number__c": person["policy"] if person["stage"] == "Closed Won" else None,
    }
    return contact, lead, deal


def save(settings: Settings, kind: str, key_field: str, rows: list[dict]) -> int:
    """Create or update records of one kind, 200 per request. Stop on the first refusal."""
    for start in range(0, len(rows), BATCH):
        batch = [{"attributes": {"type": kind}, **row} for row in rows[start : start + BATCH]]
        body = {"allOrNone": True, "records": batch}
        results = crm.call(settings, "PATCH", f"/composite/sobjects/{kind}/{key_field}", json=body)
        refused = [result["errors"] for result in results if not result["success"]]
        if refused:
            sys.exit(f"{kind}: refused, {refused[0]}")
    return len(rows)


def wipe(settings: Settings) -> None:
    """Delete every record that carries the Seeded mark, sales first."""
    for kind in ("Opportunity", "Lead", "Contact"):
        deleted = 0
        while found := crm.query(
            settings, f"SELECT Id FROM {kind} WHERE Seeded__c = true LIMIT 200"
        ):
            ids = ",".join(row["Id"] for row in found)
            crm.call(settings, "DELETE", "/composite/sobjects", params={"ids": ids})
            deleted += len(found)
        print(f"{kind:12} {deleted} deleted")


def main() -> None:
    """Parse the arguments and run."""
    parser = argparse.ArgumentParser(description="Seed the CRM with a fictional sales funnel.")
    parser.add_argument("--wipe", action="store_true", help="delete every seeded record")
    parser.add_argument("--count", type=int, default=400, help="how many customers")
    args = parser.parse_args()
    settings = get_settings()
    if not crm.enabled(settings):
        sys.exit("SALESFORCE_INSTANCE_URL and SALESFORCE_CLIENT_ID are not set.")
    crm.TIMEOUT_SECONDS = 60
    if args.wipe:
        return wipe(settings)
    account = crm_sync.account_id(settings)
    shaped = [records(person, account) for person in people(args.count, date.today())]
    kinds = (
        ("Contact", "Customer_Reference__c"),
        ("Lead", "Offer_Reference__c"),
        ("Opportunity", "Offer_Reference__c"),
    )
    for (kind, key_field), rows in zip(kinds, zip(*shaped, strict=True), strict=True):
        print(f"{kind:12} {save(settings, kind, key_field, list(rows))} saved")


if __name__ == "__main__":
    main()
