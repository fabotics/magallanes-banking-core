"""The contract a customer signs: built per product and language, with a fingerprint.

`build` returns everything the contract page shows, as plain data. The page
renders it, and `fingerprint` hashes it, so the hash stored with the signature
is the hash of exactly the wording, in exactly the language, that was shown.
The wording itself is in `contract_es.py` and `contract_en.py`.
"""

import hashlib
import json
import unicodedata
from datetime import date

from app import contract_en, contract_es
from app.db import Row
from app.formatting import card_label, document, long_date, money

CONTRACT = {"es": contract_es.TEXT, "en": contract_en.TEXT}
INSURER = "Magallanes Seguros Generales S.A."
PAGES = 4


def product_wording(product: Row, language: str) -> tuple[str, str]:
    """Return the product's name and one line of cover in this language.

    The catalog is in Spanish. Other languages come from the contract texts,
    and fall back to the catalog for a product that has no translation.
    """
    translated = CONTRACT[language]["products"].get(product["code"])
    if language == "es" or translated is None:
        return product["name"], product["coverage_summary"]
    return translated


def build(
    language: str, proposal: Row, product: Row, customer: Row, card: Row | None, issued: date
) -> dict:
    """Assemble the four pages for one proposal, in one language."""
    words = CONTRACT[language]
    name, summary = product_wording(product, language)
    premium = money(product["monthly_premium"], product["currency"], language)
    paid_with = card_label(card, language) if card else words["any_card"]
    values = [
        proposal["proposal_number"], long_date(issued, language), INSURER, "Banco Magallanes",
        f"{customer['first_name']} {customer['last_name']}",
        document(customer["document_type"], customer["document_number"]), name, premium,
        paid_with, words["term"],
    ]  # fmt: skip
    labels = list(words["labels"])
    labels[5] = customer["document_type"]
    cover = words["cover"].get(product["code"], [summary])
    exclusions = [*words["exclusions"].get(product["code"], []), words["general_exclusion"]]
    general = [
        (heading, text.format(premium=premium, card=paid_with))
        for heading, text in words["general"]
    ]
    return {
        "language": language,
        "titles": words["titles"],
        "product_name": name,
        "premium": premium,
        "particulars": list(zip(labels, values, strict=True)),
        "cover": cover,
        "exclusions": exclusions,
        "general": general,
    }


def fingerprint(contract: dict) -> str:
    """Return the SHA-256 of the contract's content: same wording, same hash."""
    canonical = json.dumps(contract, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def initials(customer: Row) -> str:
    """Return the first letter of the first name and of the first surname: `MR`."""
    return (customer["first_name"][:1] + customer["last_name"][:1]).upper()


def plain(text: str) -> str:
    """Lower case, no accents, single spaces: how two spellings of a name are compared."""
    without_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(without_accents.lower().split())


def name_matches(typed: str, customer: Row) -> bool:
    """Accept the customer's full name as the signature, whatever the case or accents."""
    return plain(typed) == plain(f"{customer['first_name']} {customer['last_name']}")
