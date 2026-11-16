"""Request and response models for the insurance endpoints."""

from typing import Literal

from pydantic import BaseModel, Field


class OfferedProduct(BaseModel):
    """A product the bank pre-approves for this customer, with their personal quote."""

    code: str
    name: str
    monthly_premium: float = Field(description="The quoted premium for this customer.")
    currency: str
    coverage_summary: str
    quote_number: str
    coverage_limit: float = Field(description="The most the insurance pays per event.")
    valid_until: str = Field(description="ISO date until which the quote can be accepted.")


class EligibilityResponse(BaseModel):
    """The bank's decision on what may be offered. The agent never decides this itself."""

    eligible: bool
    products: list[OfferedProduct]
    reason_if_not: str | None = Field(
        default=None,
        description="already_insured, segment_not_eligible, vulnerable_customer or "
        "not_available_in_country.",
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
    language: Literal["es", "en"] | None = Field(
        default=None,
        description="Language the call is held in. Messages and links to the customer follow it. "
        "Absent: the language the bank has on file for the customer.",
    )
    session_token: str | None = Field(
        default=None, description="Only if the X-Session-Token header is not used."
    )


class ProposalResponse(BaseModel):
    """The proposal, waiting in the customer's app to be read and signed."""

    proposal_number: str
    quote_number: str | None = None
    signing_url: str | None = None
    valid_until: str = Field(description="ISO date. The last day the customer can sign it.")
    sent_to: str = Field(description="Masked address, safe to read aloud.")
    email_sent: bool = Field(description="False when the API is not configured to send email.")
    message_sent: bool = Field(
        default=False, description="True when the signing link also went to the messaging channel."
    )


class ProposalStatusResponse(BaseModel):
    """Where a proposal stands. The policy fields are present only once it is signed."""

    proposal_number: str
    status: Literal["pending", "signed", "expired"]
    policy_number: str | None = None
    start_date: str | None = Field(default=None, description="ISO date the cover starts.")
