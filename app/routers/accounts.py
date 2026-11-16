"""Account balances for the verified customer."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.db import Repository, Row, get_repository
from app.schemas import AccountBalance, BalancesResponse
from app.security import session_from_request

router = APIRouter(tags=["accounts"])


@router.get("/accounts/balance", response_model=BalancesResponse)
def get_balances(
    session: Annotated[Row, Depends(session_from_request)],
    repository: Annotated[Repository, Depends(get_repository)],
) -> BalancesResponse:
    """Return the available balance of each of the customer's accounts."""
    accounts = repository.select("accounts", {"customer_id": session["customer_id"]})
    return BalancesResponse(
        accounts=[
            AccountBalance(
                type=account["type"],
                currency=account["currency"],
                available_balance=account["available_balance"],
                as_of=account["updated_at"],
            )
            for account in accounts
        ]
    )
