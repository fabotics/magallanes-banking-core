"""Fill the CRM with a believable funnel of fictional customers, or take it out again.

Usage:
    python scripts/crm_seed.py            replace the seeded funnel with a fresh one
    python scripts/crm_seed.py --wipe     delete every seeded record

Each customer is a Contact with a Lead and an Opportunity for the card cover.
About 400 offers are spread over the last 90 days, so every week has some:
most were declined, some were signed, and the ones still open are mostly from
the last two weeks. Records are created with the date of the offer, which
needs the permission that `crm_setup.py` grants. Everyone is invented: names
are drawn from two lists and never repeat, document numbers use a range that
has not been issued, and nobody has an email or a phone. Every record carries
Seeded = true and the lead source Voice agent. Running it again first removes
the seeded records, so the result is always one fresh funnel.
"""

import argparse
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

# Make `app` importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import crm, crm_sync  # noqa: E402
from app.clock import BANK_TIMEZONE  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from seed.helpers import rut  # noqa: E402

PRODUCT = "Protección de tarjeta y asistencia"
# The monthly premium of each segment: mass, preferred, premium.
PREMIUMS = (11990, 10790, 10190)
# stage, share of the offers, lead status
STAGES = (
    ("Declined", 0.55, "Closed - Not Converted"),
    ("Offered", 0.15, "Open - Not Contacted"),
    ("Interested", 0.10, "Working - Contacted"),
    ("Proposal Sent", 0.08, "Working - Contacted"),
    ("Signed", 0.12, "Working - Contacted"),
)
CLOSED = ("Declined", "Signed")
REASONS = ("Not interested",) * 9 + ("Price",) * 6 + ("Already insured",) * 3 + ("Other",) * 2
CHANNELS = ("Phone",) * 6 + ("App",) * 3 + ("Telegram",)
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


def moment(day: date, dice: random.Random) -> str:
    """Return a time during the bank's working day on that date, as the CRM wants it."""
    at = time(dice.randint(9, 19), dice.randint(0, 59))
    # Never later than now, so nothing seeded sits above a sale made today.
    stamp = min(datetime.combine(day, at, tzinfo=BANK_TIMEZONE), datetime.now(BANK_TIMEZONE))
    return stamp.isoformat(timespec="seconds")


def offered_on(stage: str, today: date, dice: random.Random) -> date:
    """Pick the day of the offer: any of the last 90 for a closed sale, recent for an open one.

    Three in four of the open sales are from the last two weeks, the rest
    from the two weeks before, because a quote lasts 15 days.
    """
    if stage in CLOSED:
        return today - timedelta(days=dice.randint(1, 89))
    recent = dice.random() < 0.75
    return today - timedelta(days=dice.randint(0, 13) if recent else dice.randint(14, 28))


def people(count: int, today: date) -> list[dict]:
    """Invent the customers, always the same ones, with where each sale stands."""
    dice = random.Random(2026)
    stages = [stage for stage in STAGES for _ in range(round(count * stage[1]))]
    rows, taken = [], set()
    for number, (stage, _, lead_status) in enumerate(stages[:count], start=1):
        # Nobody shares a full name with anybody else.
        while (name := (dice.choice(FIRST_NAMES), dice.choice(LAST_NAMES))) in taken:
            pass
        taken.add(name)
        offered = offered_on(stage, today, dice)
        # A closed sale was decided within a week. An open one was last touched since the offer.
        decided = min(offered + timedelta(days=dice.randint(0, 7)), today)
        touched = (
            decided if stage in CLOSED else min(offered + timedelta(days=dice.randint(0, 3)), today)
        )
        rows.append({
            "key": f"seed-{number:04d}",
            "document": rut(30_000_000 + number * 12_347 % 5_000_000, hyphen=True),
            "first": name[0],
            "last": f"{name[1]} {dice.choice(LAST_NAMES)}",
            "city": dice.choice(CITIES),
            "stage": stage,
            "lead_status": lead_status,
            "premium": dice.choice(PREMIUMS),
            "channel": dice.choice(CHANNELS),
            "offered": moment(offered, dice),
            "touched": moment(touched, dice) if touched > offered else None,
            "last_activity": touched,
            "close": decided if stage in CLOSED else offered + timedelta(days=15),
            "reason": dice.choice(REASONS) if stage == "Declined" else None,
            "quote": f"CT-{offered.year}-{dice.randrange(16**6):06X}",
            "proposal": f"PR-{offered.year}-{dice.randrange(16**6):06X}",
            "policy": f"PZ-{offered.year}-{dice.randrange(16**6):06X}",
        })  # fmt: skip
    return rows


def records(person: dict, account: str) -> tuple[dict, dict, dict]:
    """Shape one invented customer as a Contact, a Lead and an Opportunity."""
    # Created on the day of the offer, last changed on the day of the last activity.
    dated = {
        "CreatedDate": person["offered"],
        "LastModifiedDate": person["touched"] or person["offered"],
    }
    mark = {"LeadSource": crm_sync.SOURCE, "Seeded__c": True, **dated}
    name = {"FirstName": person["first"], "LastName": person["last"]}
    full_name = f"{person['first']} {person['last']}"
    contact = {**name, **mark, "Customer_Reference__c": person["document"], "AccountId": account,
               "MailingCity": person["city"], "MailingCountry": "Chile"}  # fmt: skip
    lead = {**name, **mark, "Offer_Reference__c": person["key"], "Company": PRODUCT,
            "Status": person["lead_status"], "City": person["city"]}  # fmt: skip
    sent = person["stage"] in ("Proposal Sent", "Signed")
    deal = {
        **mark,
        "Offer_Reference__c": person["key"],
        "Name": f"{full_name} - {PRODUCT}",
        "AccountId": account,
        "StageName": person["stage"],
        "Amount": person["premium"] * 12,
        "CloseDate": person["close"].isoformat(),
        "Contact_Name__c": full_name,
        "Monthly_Premium__c": person["premium"],
        "Channel__c": person["channel"],
        "Last_Activity__c": person["last_activity"].isoformat(),
        "Last_Activity_At__c": person["touched"] or person["offered"],
        "Quote_Number__c": person["quote"],
        "Loss_Reason__c": person["reason"],
        "Proposal_Number__c": person["proposal"] if sent else None,
        "Policy_Number__c": person["policy"] if person["stage"] == "Signed" else None,
    }
    return contact, lead, deal


def save(settings: Settings, kind: str, rows: list[dict]) -> int:
    """Create records of one kind, 200 per request. Stop on the first refusal."""
    for start in range(0, len(rows), BATCH):
        batch = [{"attributes": {"type": kind}, **row} for row in rows[start : start + BATCH]]
        body = {"allOrNone": True, "records": batch}
        results = crm.call(settings, "POST", "/composite/sobjects", json=body)
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
    # The old funnel goes first: a record cannot be given a new creation date.
    wipe(settings)
    account = crm_sync.account_id(settings)
    shaped = [records(person, account) for person in people(args.count, date.today())]
    for kind, rows in zip(
        ("Contact", "Lead", "Opportunity"), zip(*shaped, strict=True), strict=True
    ):
        print(f"{kind:12} {save(settings, kind, list(rows))} created")


if __name__ == "__main__":
    main()
