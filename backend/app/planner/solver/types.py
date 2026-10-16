from typing import Literal

from app.schemas.base import Schema
from app.schemas.plans import PlanOp


class AddWish(Schema):
    course: str
    term: str | None = None  # None: wherever it fits


class RepairRequest(Schema):
    """What the student wants changed. Saved settings stay the hard defaults; this adds to
    them. Everything here can be named back when the request can't be met."""

    term_caps: dict[str, int] = {}  # "Spring ’27 ≤ 15", on top of saved caps
    keep: list[str] = []  # placement ids to hold in place (locked ones already are)
    move: dict[str, str] = {}  # placement id -> the term it has to go in ("CS 4701 to SP28")
    remove: list[str] = []  # placement ids to drop ("drop CS 3410")
    add: list[AddWish] = []
    avoid_courses: list[str] = []  # never schedule these
    # soft: among equally small changes, prefer fewer credits here. It never causes a change
    # on its own; to actually lighten a term, cap it in term_caps
    lighter_terms: list[str] = []
    graduate_by: str | None = None  # finish by this term instead of the plan's last
    allow_removing_courses: bool = False  # otherwise only open slots can be dropped


class RepairResult(Schema):
    status: Literal["solved", "infeasible", "timeout"]
    strategy: Literal["global", "rebuild"]
    ops: list[PlanOp] = []  # the change against the current plan, ready for a proposal
    moved: int = 0
    added: int = 0
    removed: int = 0
    replaced: int = 0  # open slots filled with a course in place
    optimal: bool = False  # proven minimal, not just the best found in time
    runtime_ms: int = 0
    # readable reasons when infeasible: the requests and settings that can't all hold
    conflicts: list[str] = []
    # when infeasible: nearby versions of the request that do work, each checked
    alternatives: list[str] = []
    # an independent validate() of the repaired plan; should always be 0
    blocking: int = 0
