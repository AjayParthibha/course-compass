from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.config import get_settings

engine = create_engine(
    get_settings().database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def now() -> datetime:
    return datetime.now(UTC)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    program: Mapped[str | None]
    catalog_year: Mapped[str | None]
    entering_term: Mapped[str | None]
    graduation_term: Mapped[str | None]
    max_credits: Mapped[int] = mapped_column(default=18)
    # per-term overrides of max_credits, e.g. {"SP27": 15}
    term_caps: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    # requirement ids whose advisor approval the student has (a mixed-subject
    # external specialization); see Requirement.approval
    approvals: Mapped[list[str]] = mapped_column(JSON, default=list)
    memory_enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=now)

    plans: Mapped[list["Plan"]] = relationship(back_populates="student")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    name: Mapped[str] = mapped_column(default="Plan A")
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(default=now)

    student: Mapped[Student] = relationship(back_populates="plans")
    versions: Mapped[list["PlanVersion"]] = relationship(order_by="PlanVersion.version")


class PlanVersion(Base):
    """Append-only history of a plan. The newest row is the current plan."""

    __tablename__ = "plan_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    version: Mapped[int]
    placements: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # the version this one was derived from; undo steps back along these links, so an
    # undo commit points at the parent of the version it undid
    parent_version: Mapped[int | None]
    # "settings" for versions that only record a graduation change
    origin: Mapped[str] = mapped_column(default="user")
    note: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(default=now)


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    base_version: Mapped[int]
    summary: Mapped[str]
    ops: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    violations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(default="pending")
    created_at: Mapped[datetime] = mapped_column(default=now)


class ProfileFact(Base):
    __tablename__ = "profile_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    dimension: Mapped[str]
    value: Mapped[str]
    text: Mapped[str]
    status: Mapped[str] = mapped_column(default="stated")
    confidence: Mapped[float] = mapped_column(default=1.0)
    evidence: Mapped[str | None]
    # set when memory is off, so the fact only lives for that conversation
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)
    last_confirmed_at: Mapped[datetime | None]


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=now)

    messages: Mapped[list["Message"]] = relationship(order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str]
    # raw content blocks sent to / received from the model
    content: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # what the UI renders (text, tool rows, proposals...)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=now)


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))
    kind: Mapped[str]  # "llm" or "tool"
    name: Mapped[str]
    input: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    summary: Mapped[str | None]
    model: Mapped[str | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cache_read_tokens: Mapped[int | None]
    latency_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(default=now)


class StudyEvent(Base):
    __tablename__ = "study_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    kind: Mapped[str]
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)
