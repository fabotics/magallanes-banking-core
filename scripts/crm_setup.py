"""Prepare a Salesforce org for the mirror of the insurance sale. Safe to run again.

Usage:
    python scripts/crm_setup.py

It adds what the mirror needs and a fresh org does not have: the stages
Offered and Proposal Sent, the lead source Voice agent, the custom fields
(the external IDs the mirror finds records by, the loss reason, the proposal
and policy numbers, and the Seeded mark of demo data), a permission set that
lets administrators see those fields, and the list view "Voice agent funnel"
for opportunities and leads. It uses the Metadata API, which takes XML.
"""

import re
import sys
from pathlib import Path

import httpx

# Make `app` importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import crm, crm_sync  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402

NEW_STAGES = (("Offered", 20), ("Proposal Sent", 60))
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
]
REASONS = ("Not interested", "Price", "Already insured", "Other")
KINDS = {
    "key": "<externalId>true</externalId><unique>true</unique><length>40</length><type>Text</type>",
    "text": "<length>20</length><type>Text</type>",
    "mark": "<defaultValue>false</defaultValue><type>Checkbox</type>",
    "reason": "<type>Picklist</type><valueSet><restricted>true</restricted><valueSetDefinition>"
    "<sorted>false</sorted>"
    + "".join(
        f"<value><fullName>{r}</fullName><default>false</default><label>{r}</label></value>"
        for r in REASONS
    )
    + "</valueSetDefinition></valueSet>",
}
# object, columns of the list view, the column the lead source is filtered on
VIEWS = [
    ("Opportunity", ("OPPORTUNITY.LAST_UPDATE", "OPPORTUNITY.NAME", "OPPORTUNITY.STAGE_NAME",
                     "OPPORTUNITY.AMOUNT", "OPPORTUNITY.CLOSE_DATE", "Loss_Reason__c",
                     "Policy_Number__c"), "OPPORTUNITY.LEAD_SOURCE", "LastModifiedDate"),
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


def add_values(settings: Settings, value_set: str, values: list[str]) -> None:
    """Add values to a standard picklist, in front of the ones it already has."""
    ask = f"<type>StandardValueSet</type><fullNames>{value_set}</fullNames>"
    current = re.findall(
        r"<standardValue>.*?</standardValue>", metadata(settings, "readMetadata", ask)
    )
    new = [value for value in values if f"<fullName>{value[0]}</fullName>" not in "".join(current)]
    added = "".join(
        f"<standardValue><fullName>{name}</fullName>{rest}</standardValue>" for name, rest in new
    )
    body = "<sorted>false</sorted>" + added + "".join(current)
    metadata(settings, "updateMetadata", item("StandardValueSet", value_set, body))
    print(f"{value_set}: added {[name for name, _ in new] or 'nothing, all there'}")


def main() -> None:
    """Create or update everything, in the order the pieces depend on each other."""
    settings = get_settings()
    if not crm.enabled(settings):
        sys.exit("SALESFORCE_INSTANCE_URL and SALESFORCE_CLIENT_ID are not set.")
    stage = (
        "<default>false</default><label>{0}</label><closed>false</closed>"
        "<forecastCategory>Pipeline</forecastCategory><probability>{1}</probability><won>false</won>"
    )
    add_values(settings, "OpportunityStage", [(n, stage.format(n, p)) for n, p in NEW_STAGES])
    source = "<default>false</default><label>Voice agent</label>"
    add_values(settings, "LeadSource", [(crm_sync.SOURCE, source)])
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
    body = f"<label>Voice agent funnel</label>{allowed}"
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
