from typing import Literal

from app.schemas.base import Schema
from app.schemas.courses import CourseSummary


class Reason(Schema):
    text: str
    basis: Literal["stated", "plan", "inference"]
    fact_id: int | None = None
    date: str | None = None


class ReviewSummary(Schema):
    overall: float
    difficulty: float
    workload: float
    count: int
    url: str


class OfficialInfo(Schema):
    prereqs_met: bool
    prereq_note: str
    offering_note: str
    assumed: bool


class Candidate(Schema):
    course: CourseSummary
    rank: int
    reasons: list[Reason]
    official: OfficialInfo
    reviews: ReviewSummary | None = None


class RankingFactor(Schema):
    label: str
    strength: Literal["strong", "medium", "weak", "not used"]
    basis: str


class HiddenCourse(Schema):
    """An eligible course left out because the student marked it "not for me"."""

    course: CourseSummary
    fact_id: int


class SlotCandidates(Schema):
    slot_id: str
    slot_label: str
    term: str
    eligible_count: int
    candidates: list[Candidate]
    factors: list[RankingFactor] = []
    ordering: str = ""
    hidden: list[HiddenCourse] = []
