"""Take the demo customer's sale out of the CRM, so the next run starts clean.

Usage:
    python scripts/crm_cleanup.py                    Daniel Keller, the main demo customer
    python scripts/crm_cleanup.py "Emma Whitfield"   another customer, by full name

It deletes the Opportunities and Leads that the mirror created for that
customer. The Contact stays, and so does every seeded record: only records
without the Seeded mark are touched.
"""

import sys
from pathlib import Path

# Make `app` importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import crm, crm_sync  # noqa: E402
from app.config import get_settings  # noqa: E402

DEMO_CUSTOMER = "Daniel Keller"


def main() -> None:
    """Find the customer's mirrored sales and leads and delete them."""
    settings = get_settings()
    if not crm.enabled(settings):
        sys.exit("SALESFORCE_INSTANCE_URL and SALESFORCE_CLIENT_ID are not set.")
    name = (sys.argv[1] if len(sys.argv) > 1 else DEMO_CUSTOMER).replace("'", "")
    mirrored = f"WHERE Seeded__c = false AND LeadSource = '{crm_sync.SOURCE}'"
    found = {
        "Opportunity": f"SELECT Id FROM Opportunity {mirrored} AND Contact_Name__c = '{name}'",
        "Lead": f"SELECT Id FROM Lead {mirrored} AND Name = '{name}'",
    }
    for kind, soql in found.items():
        rows = crm.query(settings, soql)
        for row in rows:
            crm.call(settings, "DELETE", f"/sobjects/{kind}/{row['Id']}")
        print(f"{kind:12} {len(rows)} deleted for {name}")
    print("the Contact stays")


if __name__ == "__main__":
    main()
