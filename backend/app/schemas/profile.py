from datetime import datetime
from typing import Literal

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
    memory_enabled: bool
    onboarded: bool


class StudentUpdate(Schema):
    program: str | None = None
    catalog_year: str | None = None
    entering_term: str | None = None
    graduation_term: str | None = None
    max_credits: int | None = None
    memory_enabled: bool | None = None


class Profile(Schema):
    student: Student
    facts: list[ProfileFact]
