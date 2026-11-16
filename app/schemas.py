"""Request and response models.

Responses are small and speakable, because the caller is a voice agent.
"""

from typing import Literal

from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    """What the customer says to prove who they are."""

    document_number: str = Field(description="National ID number. Dots and hyphens are ignored.")
    card_last4: str = Field(description="Last four digits of any of the customer's cards.")
    birth_year: int = Field(description="Four digit year of birth.")
    conversation_id: str | None = Field(default=None, description="Caller's conversation ID.")


class VerifyResponse(BaseModel):
    """The result of an identity check. On failure it never says which field was wrong."""

    verified: bool
    locked: bool = False
    session_token: str | None = Field(
        default=None, description="Send it back in the X-Session-Token header. Valid 15 minutes."
    )
    first_name: str | None = None
    attempts_remaining: int | None = None


class HeldProduct(BaseModel):
    """Something the customer holds at the bank: an account, a card or an insurance policy."""

    kind: str = Field(description="account, card or insurance")
    name: str
    status: str


class CustomerProfile(BaseModel):
    """Who the verified customer is, in the few fields an agent needs."""

    first_name: str
    segment: str
    country: str
    preferred_language: str
    is_vulnerable: bool
    products: list[HeldProduct]


class AccountBalance(BaseModel):
    """The available balance of one account."""

    type: str
    currency: str
    available_balance: float
    as_of: str


class BalancesResponse(BaseModel):
    """All of the customer's balances."""

    accounts: list[AccountBalance]


class CardTransaction(BaseModel):
    """One card movement as it appears on a statement: a descriptor, not a merchant name."""

    id: str
    card_last4: str
    amount: float
    currency: str
    descriptor: str
    merchant_tax_id: str | None
    channel: str
    country: str
    transaction_at: str
    posted_at: str | None = Field(description="Null while the charge is pending.")
    status: str
    original_amount: float | None = Field(default=None, description="Only on foreign charges.")
    original_currency: str | None = Field(default=None, description="Only on foreign charges.")


class TransactionsResponse(BaseModel):
    """Recent card movements, newest first."""

    count: int
    transactions: list[CardTransaction]


class BlockCardRequest(BaseModel):
    """Ask for a temporary block on one of the customer's cards."""

    card_last4: str = Field(description="Last four digits of the card to block.")
    reason: str = Field(description="Why, in a few words. For example: suspected fraud.")
    session_token: str | None = Field(
        default=None, description="Only if the X-Session-Token header is not used."
    )


class BlockCardResponse(BaseModel):
    """The card's state after the request, with a reference the agent can read back."""

    card_status: str
    reference: str
    how_to_unblock: str


class CaseRequest(BaseModel):
    """Open a case for the bank's staff: fraud, handoff to a person, complaint or callback."""

    type: Literal["fraud", "handoff", "complaint", "callback"]
    summary: str = Field(description="What happened, so the customer never repeats the story.")
    priority: Literal["low", "normal", "high"] | None = Field(
        default=None, description="Defaults to high for fraud and normal otherwise."
    )
    transaction_ids: list[str] = Field(default=[], description="Transactions the case is about.")
    conversation_id: str | None = None
    callback_window: str | None = Field(
        default=None, description="When the customer prefers to be called."
    )
    session_token: str | None = Field(
        default=None, description="Omit when identity could not be verified (handoff only)."
    )


class CaseResponse(BaseModel):
    """Where the case went and when the customer can expect an answer."""

    case_number: str
    queue: str
    sla_hours: int
    callback_window: str | None = None


class Merchant(BaseModel):
    """The business behind a merchant tax ID, as the public registry knows it."""

    tax_id: str
    legal_name: str
    trade_name: str
    activity: str
    address: str
    commune: str
