"""Request and response models for notifications to the customer."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CallSummaryRequest(BaseModel):
    """A short written summary of the call, for the customer to keep."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "summary": "We reviewed four charges and blocked the card ending in 4821.",
                "language": "es",
            }
        }
    )

    summary: str = Field(min_length=1, max_length=1000, description="Plain text, a few lines.")
    language: Literal["es", "en"] | None = Field(
        default=None,
        description="Language the call is held in. Messages and links to the customer follow it. "
        "Absent: the language the bank has on file for the customer.",
    )
    session_token: str | None = Field(
        default=None, description="Only if the X-Session-Token header is not used."
    )


class ConversationEnded(BaseModel):
    """The notice that a conversation is over, as the caller's platform sends it.

    Platforms shape this notice differently. The ID is read from the top
    level, or from an object called `data`, which is where some put it.
    """

    model_config = ConfigDict(json_schema_extra={"example": {"conversation_id": "conv_123"}})

    conversation_id: str | None = None
    data: dict | None = None

    def named_conversation(self) -> str | None:
        """Return the conversation ID wherever the notice carries it."""
        return self.conversation_id or (self.data or {}).get("conversation_id")


class ClosingSummaryResponse(BaseModel):
    """Whether the bank wrote to the customer, and if not, why."""

    sent: bool
    reason: str | None = Field(
        default=None,
        description="not_verified, already_sent, nothing_recorded or no_channel when not sent.",
    )


class CallSummaryResponse(BaseModel):
    """Whether the summary went out, and through which channel."""

    sent: bool
    channel: str = Field(description="telegram, or none when the customer has no channel.")
