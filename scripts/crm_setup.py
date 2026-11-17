"""Prepare a Salesforce org for the mirror of the insurance sale. Safe to run again.

Usage:
    python scripts/crm_setup.py

It sets up what the mirror needs and a fresh org does not have. The sales
process becomes five stages and nothing else: Offered, Interested, Proposal
Sent, Signed (won) and Declined (lost); the org's default stages are switched
off. It adds the lead source Voice agent, the custom fields (the external IDs
the mirror finds records by, what a card shows, the loss reason, and the
Seeded mark of demo data), a permission set that lets administrators see
those fields and lets the seed script date its records in the past, and the
list view "Voice agent funnel" for opportunities and leads. It uses the
Metadata API, which takes XML.
"""

import re
import sys
from pathlib import Path

import httpx

# Make `app` importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import crm, crm_sync  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402

# stage, probability, closed, won, forecast category. The order is the order of the funnel.
STAGES = (
    ("Offered", 10, False, False, "Pipeline"),
    ("Interested", 30, False, False, "Pipeline"),
    ("Proposal Sent", 60, False, False, "Pipeline"),
    ("Signed", 100, True, True, "Closed"),
    ("Declined", 0, True, False, "Omitted"),
)
VIEW = "Voice_agent_funnel"
# object, field name, label, what kind of field
FIELDS = [
    ("Contact", "Customer_Reference__c", "Customer Reference", "key"),
    ("Contact", "Seeded__c", "Seeded", "mark"),
    ("Lead", "Offer_Reference__c", "Offer Reference", "key"),
    ("Lead", "Seeded__c", "Seeded", "mark"),
    ("Opportunity", "Offer_Reference__c", "Offer Reference", "key"),
    ("Opportunity", "Seeded__c", "Seeded", "mark"),
    ("Opportunity", "Proposal_Number__c", "Proposal Number", "text"),
    ("Opportunity", "Policy_Number__c", "Policy Number", "text"),
    ("Opportunity", "Loss_Reason__c", "Loss Reason", "reason"),
    ("Opportunity", "Contact_Name__c", "Contact Name", "name"),
    ("Opportunity", "Monthly_Premium__c", "Monthly Premium (CLP)", "pesos"),
    ("Opportunity", "Quote_Number__c", "Quote Number", "text"),
    ("Opportunity", "Channel__c", "Channel", "channel"),
    ("Opportunity", "Last_Activity__c", "Last Activity", "day"),
]
CHANNELS = ("Phone", "App", "Telegram")


def choices(values: tuple[str, ...]) -> str:
    """Write a picklist that takes these values and no others."""
    listed = "".join(
        f"<value><fullName>{v}</fullName><default>false</default><label>{v}</label></value>"
        for v in values
    )
    return (
        "<type>Picklist</type><valueSet><restricted>true</restricted><valueSetDefinition>"
        f"<sorted>false</sorted>{listed}</valueSetDefinition></valueSet>"
    )


REASONS = ("Not interested", "Price", "Already insured", "Other")
KINDS = {
    "key": "<externalId>true</externalId><unique>true</unique><length>40</length><type>Text</type>",
    "text": "<length>20</length><type>Text</type>",
    "name": "<length>80</length><type>Text</type>",
    "mark": "<defaultValue>false</defaultValue><type>Checkbox</type>",
    # A plain number, so the amount is not shown with the org's own currency sign.
    "pesos": "<precision>9</precision><scale>0</scale><type>Number</type>",
    "day": "<type>Date</type>",
    "reason": choices(REASONS),
    "channel": choices(CHANNELS),
}
# object, columns of the list view, the column the lead source is filtered on
VIEWS = [
    # The first four columns are what a card of the board shows under its title.
    ("Opportunity", ("OPPORTUNITY.NAME", "Contact_Name__c", "Monthly_Premium__c", "Channel__c",
                     "Last_Activity__c", "OPPORTUNITY.STAGE_NAME", "OPPORTUNITY.AMOUNT",
                     "Quote_Number__c", "Policy_Number__c", "Loss_Reason__c",
                     "OPPORTUNITY.CLOSE_DATE", "OPPORTUNITY.LAST_UPDATE"),
     "OPPORTUNITY.LEAD_SOURCE", "LastModifiedDate"),
    ("Lead", ("LEAD.CREATED_DATE", "FULL_NAME", "LEAD.COMPANY", "LEAD.STATUS",
              "LEAD.LEAD_SOURCE"), "LEAD.LEAD_SOURCE", "CreatedDate"),
]  # fmt: skip


def metadata(settings: Settings, verb: str, body: str) -> str:
    """Send one Metadata API call and return the answer. Stop on a refusal."""
    version = settings.salesforce_api_version.lstrip("v")
    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Header>'
        '<SessionHeader xmlns="http://soap.sforce.com/2006/04/metadata">'
        f"<sessionId>{crm.access_token(settings)}</sessionId></SessionHeader></Header>"
        f'<Body><{verb} xmlns="http://soap.sforce.com/2006/04/metadata" '
        f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">{body}</{verb}></Body></Envelope>'
    )
    headers = {"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": '""'}
    address = f"{crm.instance(settings)}/services/Soap/m/{version}"
    answer = httpx.post(address, content=envelope.encode(), headers=headers, timeout=120).text
    refused = re.findall(r"<message>(.*?)</message>|<faultstring>(.*?)</faultstring>", answer)
    if refused:
        sys.exit(f"{verb} was refused: {refused}")
    return answer


def item(kind: str, name: str, body: str) -> str:
    """Wrap one piece of metadata of this kind, under its full name."""
    return f'<metadata xsi:type="{kind}"><fullName>{name}</fullName>{body}</metadata>'


def stage_values() -> str:
    """Write the five stages of the sale, in the order of the funnel."""
    written = ""
    for name, probability, closed, won, forecast in STAGES:
        written += (
            f"<standardValue><fullName>{name}</fullName><default>false</default>"
            f"<label>{name}</label><closed>{str(closed).lower()}</closed>"
            f"<forecastCategory>{forecast}</forecastCategory>"
            f"<probability>{probability}</probability><won>{str(won).lower()}</won>"
            "</standardValue>"
        )
    return written


def add_lead_source(settings: Settings) -> None:
    """Add the lead source of mirrored records to the ones the org already has."""
    ask = "<type>StandardValueSet</type><fullNames>LeadSource</fullNames>"
    current = "".join(
        re.findall(r"<standardValue>.*?</standardValue>", metadata(settings, "readMetadata", ask))
    )
    if f"<fullName>{crm_sync.SOURCE}</fullName>" not in current:
        added = (
            f"<standardValue><fullName>{crm_sync.SOURCE}</fullName><default>false</default>"
            f"<label>{crm_sync.SOURCE}</label></standardValue>"
        )
        body = f"<sorted>false</sorted>{added}{current}"
        metadata(settings, "updateMetadata", item("StandardValueSet", "LeadSource", body))


def main() -> None:
    """Create or update everything, in the order the pieces depend on each other."""
    settings = get_settings()
    if not crm.enabled(settings):
        sys.exit("SALESFORCE_INSTANCE_URL and SALESFORCE_CLIENT_ID are not set.")
    # Only these five stages stay active: a stage that is not written here is switched off.
    stages = f"<sorted>false</sorted>{stage_values()}"
    metadata(settings, "updateMetadata", item("StandardValueSet", "OpportunityStage", stages))
    print(f"stages: {[stage[0] for stage in STAGES]}")
    add_lead_source(settings)
    # Lets a record be created with a date in the past, for the seeded history.
    dated = "<enableAuditFieldsInactiveOwner>true</enableAuditFieldsInactiveOwner>"
    metadata(settings, "updateMetadata", item("SecuritySettings", "Security", dated))
    fields = [
        item("CustomField", f"{o}.{n}", f"<label>{label}</label>{KINDS[k]}")
        for o, n, label, k in FIELDS
    ]
    for start in range(0, len(fields), 5):
        metadata(settings, "upsertMetadata", "".join(fields[start : start + 5]))
    print(f"fields: {len(fields)} in place")
    allowed = "".join(
        f"<fieldPermissions><editable>true</editable><field>{o}.{n}</field>"
        "<readable>true</readable></fieldPermissions>" for o, n, _, _ in FIELDS
    )  # fmt: skip
    past_dates = (
        "<userPermissions><enabled>true</enabled><name>CreateAuditFields</name></userPermissions>"
    )
    body = f"{allowed}<label>Voice agent funnel</label>{past_dates}"
    metadata(settings, "upsertMetadata", item("PermissionSet", VIEW, body))
    allow_administrators(settings)
    for kind, columns, source_column, newest in VIEWS:
        shown = "".join(f"<columns>{column}</columns>" for column in columns)
        only = (
            f"<filters><field>{source_column}</field><operation>equals</operation>"
            f"<value>{crm_sync.SOURCE}</value></filters>"
        )
        body = (
            f"{shown}<filterScope>Everything</filterScope>{only}<label>Voice agent funnel</label>"
        )
        metadata(settings, "upsertMetadata", item("ListView", f"{kind}.{VIEW}", body))
        # Newest first. This is a preference of the user the app signs in as.
        order = {"orderedBy": [{"fieldApiName": newest, "isAscending": False}]}
        crm.call(settings, "PATCH", f"/ui-api/list-preferences/{kind}/{VIEW}", json=order)
    print("list views: Voice agent funnel on Opportunity and Lead, newest first")


def allow_administrators(settings: Settings) -> None:
    """Give the permission set to every active administrator who does not have it yet."""
    found = crm.query(settings, f"SELECT Id FROM PermissionSet WHERE Name = '{VIEW}'")[0]["Id"]
    admins = crm.query(
        settings,
        "SELECT Id FROM User WHERE IsActive = true AND UserType = 'Standard' "
        "AND Profile.PermissionsModifyAllData = true",
    )
    have = crm.query(
        settings,
        f"SELECT AssigneeId FROM PermissionSetAssignment WHERE PermissionSetId = '{found}'",
    )
    holders = {row["AssigneeId"] for row in have}
    for admin in admins:
        if admin["Id"] not in holders:
            grant = {"AssigneeId": admin["Id"], "PermissionSetId": found}
            crm.call(settings, "POST", "/sobjects/PermissionSetAssignment", json=grant)
    print(f"permission set: held by {len(admins)} administrator(s)")


if __name__ == "__main__":
    main()
