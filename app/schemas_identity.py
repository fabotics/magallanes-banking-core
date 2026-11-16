"""Request and response models for identity confirmation in the bank's app."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PushRequest(BaseModel):
    """Ask the customer to confirm who they are in the bank's app.

    Name the customer in one of three ways, whichever the channel gives: the
    reference a conversation started inside the app carries, the number a phone
    call comes from, or the national ID number the customer says.
    """

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

    @model_validator(mode="after")
    def names_a_customer(self) -> "PushRequest":
        """Refuse a request that names nobody."""
        if not (self.customer_id or self.customer_ref or self.phone):
            raise ValueError("Send customer_id, customer_ref or phone.")
        return self


class PushResponse(BaseModel):
    """The pending request. The answer is the same whether or not the customer exists."""

    status: Literal["pending", "locked"]
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
