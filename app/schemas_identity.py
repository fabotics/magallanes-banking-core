"""Request and response models for identity confirmation in the bank's app."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import Overview


class PushRequest(BaseModel):
    """Ask the customer to confirm who they are in the bank's app.

    Name the customer in one of three ways, whichever the channel gives: the
    reference a conversation started inside the app carries, the number a phone
    call comes from, or the national ID number the customer says. A caller may
    send both the reference and the phone, whatever its channel carries: the
    bank uses the one that names a customer. A request that names nobody is
    answered `not_identified`, and the caller then asks for the ID number.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customer_id": "31.415.926-8",
                "conversation_id": "conv_123",
                "language": "es",
            }
        }
    )

    customer_id: str | None = Field(
        default=None,
        description="The customer's national ID number, as they say it. "
        "Dots and hyphens are ignored.",
    )
    customer_ref: str | None = Field(
        default=None, description="The customer reference a conversation from the app carries."
    )
    phone: str | None = Field(
        default=None, description="The caller's phone number. Matched to the phone on file."
    )
    conversation_id: str | None = Field(default=None, description="Caller's conversation ID.")
    language: Literal["es", "en"] | None = Field(
        default=None,
        description="Language the call is held in. Messages and links to the customer follow it. "
        "Absent: the language the bank has on file for the customer.",
    )


class PushResponse(BaseModel):
    """The pending request, or `not_identified` when the channel names no customer.

    For an ID number the customer said, the answer is `pending` whether or not
    that number is known, so it says nothing about who is a customer.
    """

    status: Literal["pending", "locked", "not_identified"]
    request_id: str | None = Field(
        default=None, description="Ask for the result with this ID. Absent when locked."
    )
    expires_in_seconds: int | None = None


class PushStatusResponse(BaseModel):
    """Where the request stands. The session token is present only once it is approved."""

    status: Literal["pending", "approved", "denied", "expired"]
    session_token: str | None = Field(
        default=None, description="Send it back in the X-Session-Token header. Valid 15 minutes."
    )
    first_name: str | None = None
    next_step: Literal["ask_customer", "send_new_confirmation", "offer_other_way"] | None = Field(
        default=None,
        description="What to do after a status that is not approved. The bank counts the "
        "checks, so the caller never decides how long to wait.",
    )
    instruction: str | None = Field(default=None, description="The same, in a sentence.")
    overview: Overview | None = Field(
        default=None,
        description="Once approved: the profile and what the statement shows, so the caller "
        "does not have to ask for them.",
    )
    review_route: Literal["review", "handoff"] | None = Field(
        default=None,
        description="Once approved: where the conversation goes next. handoff for a customer "
        "the bank serves in person.",
    )
