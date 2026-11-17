"""Request and response models for the insurance endpoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "product_code": "PURCHASE",
                "outcome": "sent",
                "conversation_id": "conv_123",
            }
        }
    )

    product_code: str
    outcome: Literal["sent", "interested", "declined"] | None = Field(
        default=None,
        description="How the offer ended. sent: the customer wants the proposal. interested: "
        "they want to read it before deciding. declined: they said no.",
    )
    loss_reason: Literal["not_interested", "price", "already_insured", "other"] | None = Field(
        default=None, description="Only with declined: why, as the customer put it."
    )
    customer_response: Literal["accepted", "declined", "info_requested"] | None = Field(
        default=None, description="The older way to say the same. Use `outcome` instead."
    )
    conversation_id: str | None = None
    language: Literal["es", "en"] | None = Field(
        default=None,
        description="Language the call is held in. The proposal's message and link follow it.",
    )
    session_token: str | None = Field(
        default=None, description="Only if the X-Session-Token header is not used."
    )

    @model_validator(mode="after")
    def has_an_answer(self) -> "OfferRequest":
        """Fill the stored answer from `outcome`. A request with neither is refused."""
        stored = {"sent": "accepted", "interested": "info_requested", "declined": "declined"}
        if self.outcome:
            self.customer_response = stored[self.outcome]
        if not self.customer_response:
            raise ValueError("Send outcome: sent, interested or declined.")
        return self


class OfferResponse(BaseModel):
    """Proof that the offer and the answer were stored, and what happens next.

    When the customer wants the product, the bank sends the proposal in this
    same step, so the answer also carries the proposal.
    """

    offer_id: str
    logged_at: str
    offer_route: Literal["sign", "send_proposal", "wrap_up"] = Field(
        description="Where the conversation goes next: sign when the proposal is on its way "
        "to the customer, send_proposal when it still has to be asked for, wrap_up when "
        "they said no."
    )
    proposal_number: str | None = None
    valid_until: str | None = Field(default=None, description="Last day to sign, ISO date.")
    message_sent: bool | None = Field(
        default=None, description="True when the link went to the customer's chat."
    )


class ProposalRequest(BaseModel):
    """Send the proposal for an offer the customer accepted or asked details about."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "offer_id": "the offer_id returned by /v1/insurance/offers",
                "language": "es",
            }
        }
    )

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
