"""Customer profile: who the verified customer is and what they hold."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app import overview
from app.db import Repository, Row, get_repository
from app.schemas import CustomerProfile
from app.security import session_from_request

router = APIRouter(tags=["customers"])


@router.get("/customers/me", response_model=CustomerProfile)
def get_profile(
    session: Annotated[Row, Depends(session_from_request)],
    repository: Annotated[Repository, Depends(get_repository)],
) -> CustomerProfile:
    """Return the profile of the customer who owns the session."""
    customer = repository.select("customers", {"id": session["customer_id"]})[0]
    return overview.profile(repository, customer)
