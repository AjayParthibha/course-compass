from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.base import Schema

PlacementStatus = Literal["completed", "in_progress", "planned"]
Origin = Literal["import", "user", "advisor", "planner"]


class Placement(Schema):
    """One course (or open requirement slot) placed in a term."""

    id: str
    term: str
    course: str | None = None
    title: str | None = None
    slot: str | None = None
    slot_label: str | None = None
    credits: int
    status: PlacementStatus = "planned"
    locked: bool = False
    origin: Origin = "user"


class Plan(Schema):
    id: int
    name: str
    version: int
    program: str
    terms: list[str]
    current_term: str
    placements: list[Placement]


class AddOp(Schema):
    op: Literal["add"] = "add"
    term: str
    course: str | None = None
    slot: str | None = None


class RemoveOp(Schema):
    op: Literal["remove"] = "remove"
    placement_id: str


class MoveOp(Schema):
    op: Literal["move"] = "move"
    placement_id: str
    term: str


class ReplaceOp(Schema):
    op: Literal["replace"] = "replace"
    placement_id: str
    course: str


PlanOp = Annotated[AddOp | RemoveOp | MoveOp | ReplaceOp, Field(discriminator="op")]

ViolationKind = Literal[
    "prereq", "coreq", "credits_high", "credits_low", "offering", "duplicate", "unknown_course"
]


class Violation(Schema):
    kind: ViolationKind
    message: str
    placement_ids: list[str] = []
    blocking: bool = False


class RequirementStatus(Schema):
    id: str
    label: str
    status: Literal["done", "planned", "missing", "flagged"]
    needed: int
    filled: list[str] = []
    # how many of the `needed` seats (or children) are only held by an open slot,
    # so the UI can tell "chosen" apart from "room left in the plan"
    open_slots: int = 0
    children: list[RequirementStatus] = []


class AuditResult(Schema):
    complete: bool
    requirements: list[RequirementStatus]
    unassigned: list[str] = []


class PlanEdge(Schema):
    """`source` is a prerequisite of `target` (both placement ids)."""

    source: str
    target: str


class PlanState(Schema):
    plan: Plan
    audit: AuditResult
    violations: list[Violation]
    edges: list[PlanEdge] = []


class OpsRequest(Schema):
    ops: list[PlanOp]
    dry_run: bool = False


class ProposedChange(Schema):
    course: str
    from_term: str | None = None
    to_term: str | None = None
    reason: str


class RejectedOption(Schema):
    title: str
    reason: str


# "outdated": still pending, but the plan has changed since it was made (version != base_version),
# so it can't be applied as-is
ProposalStatus = Literal["pending", "applied", "discarded", "outdated"]


class Proposal(Schema):
    id: int
    plan_id: int
    base_version: int
    summary: str
    ops: list[PlanOp]
    changes: list[ProposedChange] = []
    rejected: list[RejectedOption] = []
    checks: list[str] = []
    violations: list[Violation] = []
    status: ProposalStatus = "pending"
    created_at: datetime
