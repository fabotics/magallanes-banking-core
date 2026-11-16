"""Request and response models.

Responses are small and speakable, because the caller is a voice agent.
"""

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
