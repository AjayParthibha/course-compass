from datetime import datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from app.schemas.base import Schema

FactStatus = Literal["stated", "inferred", "open", "rejected", "superseded", "conflict"]

# Dimensions the ranker understands. Free-text facts can use "note".
DIMENSIONS = [
    "career_track",
    "grad_school",
    "work_style",
    "max_heavy_per_term",
    "ls_goal",
    "interest",
    "term_load",
    "note",
]


class ProfileFact(Schema):
    id: int
    dimension: str
    value: str
    text: str
    status: FactStatus
    confidence: float = 1.0
    evidence: str | None = None
    created_at: datetime
    updated_at: datetime
    last_confirmed_at: datetime | None = None


class FactCreate(Schema):
    dimension: str
    value: str
    text: str
    status: FactStatus = "stated"
    confidence: float = 1.0
    evidence: str | None = None


class FactUpdate(Schema):
    value: str | None = None
    text: str | None = None
    status: FactStatus | None = None


class Student(Schema):
    id: int
    code: str
    program: str | None
    catalog_year: str | None
    entering_term: str | None
    graduation_term: str | None
    max_credits: int
    # per-term overrides of max_credits for remaining terms, e.g. {"SP27": 15}
    term_caps: dict[str, int] = {}
    memory_enabled: bool
    onboarded: bool


class StudentUpdate(Schema):
    """Program and entering term are set by onboarding; graduation term and credit
    limits change through PlanSettingsUpdate. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    memory_enabled: bool


MIN_CREDIT_CAP = 12
MAX_CREDIT_CAP = 23

Term = Annotated[str, Field(pattern=r"^(FA|SP)\d{2}$")]
CreditCap = Annotated[int, Field(ge=MIN_CREDIT_CAP, le=MAX_CREDIT_CAP)]


class PlanSettingsUpdate(Schema):
    """Fields left out stay as they are. `term_caps` replaces the whole map."""

    graduation_term: Term | None = None
    max_credits: CreditCap | None = None
    term_caps: dict[Term, CreditCap] | None = None


class Profile(Schema):
    student: Student
    facts: list[ProfileFact]
