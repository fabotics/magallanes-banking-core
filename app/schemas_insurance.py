"""Request and response models for the insurance endpoints."""

from typing import Literal

from pydantic import BaseModel, Field


class OfferedProduct(BaseModel):
    """An insurance product the bank pre-approves for this customer."""

    code: str
    name: str
    monthly_premium: float
    currency: str
    coverage_summary: str


class EligibilityResponse(BaseModel):
    """The bank's decision on what may be offered. The agent never decides this itself."""

    eligible: bool
    products: list[OfferedProduct]
    reason_if_not: str | None = Field(
        default=None,
        description="already_insured, segment_not_eligible or vulnerable_customer.",
    )


class OfferRequest(BaseModel):
    """Record that a product was offered and what the customer answered."""

    product_code: str
    customer_response: Literal["accepted", "declined", "info_requested"]
    conversation_id: str | None = None
    session_token: str | None = Field(
        default=None, description="Only if the X-Session-Token header is not used."
    )


class OfferResponse(BaseModel):
    """Proof that the offer and the answer were stored."""

    offer_id: str
    logged_at: str


class ProposalRequest(BaseModel):
    """Send the proposal for an offer the customer accepted or asked details about."""

    offer_id: str
    channel: Literal["email"] = "email"
    session_token: str | None = Field(
        default=None, description="Only if the X-Session-Token header is not used."
    )


class ProposalResponse(BaseModel):
    """The proposal. `signing_url` is absent when the customer only asked for information."""

    proposal_number: str
    signing_url: str | None = None
    sent_to: str = Field(description="Masked address, safe to read aloud.")
    email_sent: bool = Field(description="False when the API is not configured to send email.")
