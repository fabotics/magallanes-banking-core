"""What the bank mirrors to the CRM, and when: the customer, the offer and how it ends.

Each step of the insurance sale already happens in the bank core. Right after
the bank has stored it, the matching function here copies it to the CRM:

- a verified customer becomes a Contact,
- an offer becomes a Lead and an Opportunity in stage Offered, or Closed Lost
  with the reason when the customer said no,
- a proposal moves the Opportunity to Proposal Sent,
- a signature moves it to Closed Won.

A failure is logged and reported as `failed`, never raised: the customer and
the agent on the call must not notice that a copy could not be written.
"""

import logging
from collections.abc import Callable
from datetime import date

from fastapi import Request

from app import audit, crm
from app.config import Settings
from app.db import Row

logger = logging.getLogger(__name__)
SOURCE = "Voice agent"
ACCOUNT_NAME = "Banco Magallanes - Clientes persona"
COUNTRIES = {"CL": "Chile", "PE": "Peru", "CO": "Colombia", "MX": "Mexico"}
LOSS_REASONS = {
    "not_interested": "Not interested",
    "price": "Price",
    "already_insured": "Already insured",
    "other": "Other",
}
# The account every personal customer hangs from, found once per process.
found: dict[str, str] = {}


def mirrored(settings: Settings, step: Callable[[], None]) -> str:
    """Run one mirroring step. Return `off`, `ok` or `failed`, and never raise."""
    if not crm.enabled(settings):
        return "off"
    try:
        step()
    except Exception as error:
        logger.warning("crm mirror failed: %s", error)
        return "failed"
    return "ok"


def noted(request: Request, result: str) -> None:
    """Write the result of a mirroring step on the audit row, unless there is no CRM."""
    if result != "off":
        audit.note(request, crm=result)


def account_id(settings: Settings) -> str:
    """Return the ID of the account for personal customers, creating it the first time."""
    if "account" not in found:
        rows = crm.query(settings, f"SELECT Id FROM Account WHERE Name = '{ACCOUNT_NAME}'")
        if rows:
            found["account"] = rows[0]["Id"]
        else:
            created = crm.call(settings, "POST", "/sobjects/Account", json={"Name": ACCOUNT_NAME})
            found["account"] = created["id"]
    return found["account"]


def contact(settings: Settings, customer: Row) -> dict:
    """Create or update the Contact of a customer. Only fictional seed data is sent."""
    fields = {
        "FirstName": customer["first_name"],
        "LastName": customer["last_name"],
        "AccountId": account_id(settings),
        "LeadSource": SOURCE,
        "MailingCountry": COUNTRIES.get(customer["country"], customer["country"]),
    }
    return crm.upsert(settings, "Contact", "Customer_Reference__c", customer["id"], fields)


def customer_verified(settings: Settings, customer: Row) -> str:
    """Mirror a customer who has just been verified."""
    return mirrored(settings, lambda: contact(settings, customer))


def offer_logged(
    settings: Settings, customer: Row, offer: Row, product: Row, valid_until: date, reason: str
) -> str:
    """Mirror an offer: a Lead and an Opportunity. A declined one is born Closed Lost."""

    def step() -> None:
        declined = offer["customer_response"] == "declined"
        person = contact(settings, customer)
        name = {"FirstName": customer["first_name"], "LastName": customer["last_name"]}
        lead = {
            **name,
            "Company": product["name"],
            "LeadSource": SOURCE,
            "Status": "Closed - Not Converted" if declined else "Open - Not Contacted",
            "Description": f"Quote {offer.get('quote_number') or '-'}",
        }
        crm.upsert(settings, "Lead", "Offer_Reference__c", offer["id"], lead)
        deal = {
            "Name": f"{product['name']} - {customer['first_name']} {customer['last_name']}",
            "AccountId": account_id(settings),
            "StageName": "Closed Lost" if declined else "Offered",
            "Amount": float(product["monthly_premium"]) * 12,
            "CloseDate": valid_until.isoformat(),
            "LeadSource": SOURCE,
            "Description": f"Quote {offer.get('quote_number') or '-'}",
        }
        if declined:
            deal["Loss_Reason__c"] = LOSS_REASONS.get(reason, "Other")
        saved = crm.upsert(settings, "Opportunity", "Offer_Reference__c", offer["id"], deal)
        if saved and saved.get("created"):
            role = {"OpportunityId": saved["id"], "ContactId": person["id"], "IsPrimary": True}
            crm.call(settings, "POST", "/sobjects/OpportunityContactRole", json=role)

    return mirrored(settings, step)


def stage_changed(settings: Settings, offer_id: str, stage: str, **fields: str) -> str:
    """Move the Opportunity of an offer to another stage, with any fields that go with it."""

    def step() -> None:
        change = {"StageName": stage, **fields}
        crm.upsert(settings, "Opportunity", "Offer_Reference__c", offer_id, change)
        if stage == "Proposal Sent":
            working = {"Status": "Working - Contacted"}
            crm.upsert(settings, "Lead", "Offer_Reference__c", offer_id, working)

    return mirrored(settings, step)
