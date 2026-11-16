"""Request and response models for cases and for the ways to reach a person."""

from typing import Literal

from pydantic import BaseModel, Field


class CaseRequest(BaseModel):
    """Open a case for the bank's staff.

    `type` says what kind of help: a fraud report, a handoff, a complaint, a
    callback or a meeting. `category` says what it is for the bank: a problem
    to solve (`service`) or a wish to buy something (`sales_lead`).
    """

    type: Literal["fraud", "handoff", "complaint", "callback", "meeting"]
    summary: str = Field(description="What happened, so the customer never repeats the story.")
    category: Literal["service", "sales_lead"] = Field(
        default="service", description="sales_lead when the customer wants to buy or quote."
    )
    priority: Literal["low", "normal", "high"] | None = Field(
        default=None, description="Defaults to high for fraud and normal otherwise."
    )
    transaction_ids: list[str] = Field(default=[], description="Transactions the case is about.")
    conversation_id: str | None = None
    callback_window: str | None = Field(
        default=None, description="When the customer prefers to be called."
    )
    meeting_at: str | None = Field(
        default=None, description="The day and time the customer asked to meet an advisor."
    )
    session_token: str | None = Field(
        default=None, description="Omit when identity could not be verified (handoff only)."
    )


class CaseResponse(BaseModel):
    """Where the case went and when the customer can expect an answer."""

    case_number: str
    queue: str
    sla_hours: int
    category: str
    callback_window: str | None = None
    meeting_at: str | None = None


class Route(BaseModel):
    """One way to reach a person, and why it is closed when it is."""

    available: bool
    reason_if_not: str | None = Field(
        default=None, description="no_phone_line or outside_service_hours."
    )


class RoutesResponse(BaseModel):
    """The ways to reach a person right now. The bank decides, not the agent."""

    talk_now: Route
    callback: Route
    meeting: Route
    service_hours: str
