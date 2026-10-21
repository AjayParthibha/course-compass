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
    # subjects it's cross-listed with that the rule caps, e.g. ["CS"]
    capped_cross_listings: list[str] = []


class RankingFactor(Schema):
    label: str
    strength: Literal["strong", "medium", "weak", "not used"]
    basis: str


class HiddenCourse(Schema):
    """An eligible course left out because the student marked it "not for me"."""

    course: CourseSummary
    fact_id: int


class BlockedCourse(Schema):
    """A course that fits the rule but can't go in this term, and why."""

    course: CourseSummary
    reason: str


class ApprovalState(Schema):
    """An exception the catalog lets an advisor approve for this rule."""

    label: str
    approved: bool


class SlotCandidates(Schema):
    slot_id: str
    slot_label: str
    term: str
    eligible_count: int
    candidates: list[Candidate]
    factors: list[RankingFactor] = []
    ordering: str = ""
    hidden: list[HiddenCourse] = []
    # the rule wants all its courses from one subject, so pick an area first
    same_subject: bool = False
    # set when the list is narrowed to one subject (same-subject rules)
    subject: str | None = None
    blocked: list[BlockedCourse] = []
    approval: ApprovalState | None = None


class Area(Schema):
    """One subject a same-subject rule could be filled from."""

    subject: str
    name: str
    ready: int  # courses you could take in the slot's term
    blocked: int  # courses that fit but need a prerequisite or another season
    builds_on: list[str] = []  # courses in your plan under this subject
    counted: list[str] = []  # courses already counting toward the rule here
    sample: list[CourseSummary] = []
    # why the area fits what the student told us ("3 courses about machine learning")
    reasons: list[Reason] = []


class SlotAreas(Schema):
    slot_id: str
    slot_label: str
    term: str
    needed: int
    # the subject the plan already uses for this rule, if any
    chosen: str | None = None
    counted: list[CourseSummary] = []
    caps: dict[str, int] = {}
    areas: list[Area]
    approval: ApprovalState | None = None
