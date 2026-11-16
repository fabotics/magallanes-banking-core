"""Request and response models for notifications to the customer."""

from typing import Literal

from pydantic import BaseModel, Field


class CallSummaryRequest(BaseModel):
    """A short written summary of the call, for the customer to keep."""

    summary: str = Field(min_length=1, max_length=1000, description="Plain text, a few lines.")
    language: Literal["es", "en"] | None = Field(
        default=None,
        description="Language the call is held in. Messages and links to the customer follow it. "
        "Absent: the language the bank has on file for the customer.",
    )
    session_token: str | None = Field(
        default=None, description="Only if the X-Session-Token header is not used."
    )


class CallSummaryResponse(BaseModel):
    """Whether the summary went out, and through which channel."""

    sent: bool
    channel: str = Field(description="telegram, or none when the customer has no channel.")
