from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field

from app.schemas.base import Schema
from app.schemas.plans import Proposal
from app.schemas.profile import ProfileFact


class ChatRequest(Schema):
    message: str
    conversation_id: int | None = None


class TextEvent(Schema):
    type: Literal["text"] = "text"
    delta: str


class ToolStartEvent(Schema):
    type: Literal["tool_start"] = "tool_start"
    id: str
    name: str
    args: dict[str, Any] = {}


class ToolEndEvent(Schema):
    type: Literal["tool_end"] = "tool_end"
    id: str
    name: str
    summary: str
    ok: bool = True


class QuestionEvent(Schema):
    type: Literal["question"] = "question"
    question: str
    options: list[str]
    dimension: str | None = None


class ProposalEvent(Schema):
    type: Literal["proposal"] = "proposal"
    proposal: Proposal


class ProfileUpdateEvent(Schema):
    type: Literal["profile_update"] = "profile_update"
    fact: ProfileFact


class DoneEvent(Schema):
    type: Literal["done"] = "done"
    conversation_id: int


class ErrorEvent(Schema):
    type: Literal["error"] = "error"
    message: str


AdvisorEvent = Annotated[
    TextEvent
    | ToolStartEvent
    | ToolEndEvent
    | QuestionEvent
    | ProposalEvent
    | ProfileUpdateEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]


class ChatMessage(Schema):
    id: int
    role: Literal["user", "assistant"]
    events: list[AdvisorEvent]


class Conversation(Schema):
    id: int
    messages: list[ChatMessage]


class ConversationSummary(Schema):
    """One past chat in the history list."""

    id: int
    title: str  # the first question, shortened
    last_at: datetime
    questions: int
