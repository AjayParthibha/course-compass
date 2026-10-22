from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from app.catalog.store import Catalog
from app.planner.ops import terms_between
from app.schemas.plans import Placement


class Slot(BaseModel):
    requirement: str  # e.g. "ls"
    term: str  # e.g. "SP27"


class Request(BaseModel):
    text: str | None = None  # what the student says, for advisor / LLM modes
    # structured edits; `course` is resolved to a placement id when the scenario loads
    ops: list[dict[str, Any]] = []
    # the same request for the solver (a RepairRequest), for repair and advisor modes
    constraints: dict[str, Any] | None = None
    # the open slot a "what should I take?" request is about, for the elicit modes
    slot: Slot | None = None


class Expected(BaseModel):
    outcome: Literal["feasible", "infeasible", "needs_info"]
    notes: str | None = None


class Scenario(BaseModel):
    id: str
    split: Literal["dev", "heldout"] = "dev"
    program: str
    catalog_year: str
    entering: str
    graduating: str
    current: str
    max_credits: int = 18
    history: dict[str, list[str]] = {}  # term -> courses already taken (or taking now)
    plan: dict[str, list[str]] = {}  # term -> courses planned later
    hidden_preferences: dict[str, str] = {}  # for elicitation runs
    # what the student already told us, as stated profile facts ({dimension: value})
    profile: dict[str, str] = {}
    request: Request
    expected: Expected

    @property
    def terms(self) -> list[str]:
        return terms_between(self.entering, self.graduating)

    def placements(self, catalog: Catalog) -> list[Placement]:
        out = []
        now = self.terms.index(self.current)
        for term, codes in {**self.history, **self.plan}.items():
            idx = self.terms.index(term)
            status = "completed" if idx < now else "in_progress" if idx == now else "planned"
            for code in codes:
                course = catalog.get(code)
                if course is None:
                    raise ValueError(f"{self.id}: {code} isn't in the snapshot")
                out.append(
                    Placement(
                        id=course.code.replace(" ", "").lower(),
                        term=term,
                        course=course.code,
                        title=course.title,
                        credits=course.credits,
                        status=status,
                    )
                )
        return out

    def resolved_ops(self) -> list[dict[str, Any]]:
        ops = []
        for op in self.request.ops:
            op = dict(op)
            if op["op"] != "add" and "course" in op and "placement_id" not in op:
                op["placement_id"] = op.pop("course").replace(" ", "").lower()
            ops.append(op)
        return ops


def load_scenarios(path: Path, split: str | None = None) -> list[Scenario]:
    scenarios = [Scenario.model_validate(d) for d in yaml.safe_load(path.read_text())]
    return [s for s in scenarios if split is None or s.split == split]
