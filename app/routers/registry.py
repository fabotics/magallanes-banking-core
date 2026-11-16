"""Merchant registry: look up the business behind a tax ID.

This is public reference data, not customer data, so it needs the API key but
no customer session. It is the step that turns a cryptic statement descriptor
into a name the customer recognizes.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app import audit
from app.db import Repository, Row, get_repository
from app.errors import ApiError
from app.schemas import Merchant

router = APIRouter(tags=["registry"])


def normalize_tax_id(value: str) -> str:
    """Bring a tax ID to the stored form: `66.871.234-7` or `668712347` become `66871234-7`."""
    compact = "".join(character for character in value if character.isalnum()).upper()
    return f"{compact[:-1]}-{compact[-1:]}" if len(compact) > 1 else compact


def find_merchant(repository: Repository, tax_id: str) -> Row | None:
    """Return the registry row for a tax ID, or None when it is not registered."""
    merchants = repository.select("registry_merchants", {"tax_id": normalize_tax_id(tax_id)})
    return merchants[0] if merchants else None


@router.get("/registry/merchants/{tax_id}", response_model=Merchant)
def get_merchant(
    tax_id: str,
    request: Request,
    repository: Annotated[Repository, Depends(get_repository)],
) -> Merchant:
    """Return the business registered under a tax ID."""
    merchant = find_merchant(repository, tax_id)
    if merchant is None:
        audit.note(request, outcome="merchant_not_found")
        raise ApiError(404, "merchant_not_found", "No business is registered under this tax ID.")
    audit.note(request, outcome="merchant_found", tax_id=merchant["tax_id"])
    return Merchant(**merchant)
