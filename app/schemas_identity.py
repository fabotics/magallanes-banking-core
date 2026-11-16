"""Request and response models for identity confirmation in the bank's app."""

from typing import Literal

from pydantic import BaseModel, Field


class PushRequest(BaseModel):
    """Ask the customer to confirm who they are in the bank's app."""

    customer_id: str = Field(
        description="The customer's national ID number, as they say it. "
        "Dots and hyphens are ignored."
    )
    conversation_id: str | None = Field(default=None, description="Caller's conversation ID.")


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
