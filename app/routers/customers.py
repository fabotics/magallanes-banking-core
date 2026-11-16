"""Customer profile: who the verified customer is and what they hold."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.db import Repository, Row, get_repository
from app.schemas import CustomerProfile, HeldProduct
from app.security import session_from_request

router = APIRouter(tags=["customers"])


def held_products(repository: Repository, customer_id: str) -> list[HeldProduct]:
    """List the customer's accounts, cards and active insurance policies."""
    products = []
    for account in repository.select("accounts", {"customer_id": customer_id}):
        name = f"{account['type']} account in {account['currency']}"
        products.append(HeldProduct(kind="account", name=name, status="active"))
    for card in repository.select("cards", {"customer_id": customer_id}):
        name = f"{card['brand']} {card['type']} card ending {card['last4']}"
        products.append(HeldProduct(kind="card", name=name, status=card["status"]))
    catalog = {row["code"]: row["name"] for row in repository.select("insurance_products")}
    for policy in repository.select("policies", {"customer_id": customer_id, "status": "active"}):
        name = catalog[policy["product_code"]]
        products.append(HeldProduct(kind="insurance", name=name, status="active"))
    return products


@router.get("/customers/me", response_model=CustomerProfile)
def get_profile(
    session: Annotated[Row, Depends(session_from_request)],
    repository: Annotated[Repository, Depends(get_repository)],
) -> CustomerProfile:
    """Return the profile of the customer who owns the session."""
    customer = repository.select("customers", {"id": session["customer_id"]})[0]
    return CustomerProfile(
        first_name=customer["first_name"],
        segment=customer["segment"],
        country=customer["country"],
        preferred_language=customer["preferred_language"],
        is_vulnerable=customer["is_vulnerable"],
        products=held_products(repository, customer["id"]),
    )
