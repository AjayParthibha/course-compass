"""Tools the advisor can call. Each returns ToolResult(data, summary); the summary
is the one-liner the chat shows ("list_eligible(ls, SP27) → 41 courses fit").

Add a tool by decorating a function whose first argument is the ToolContext.
Everything else in the signature becomes the tool's input schema.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, create_model
from sqlalchemy.orm import Session

from app import models, services
from app.catalog.store import get_catalog
from app.models import now
from app.planner.eligible import list_eligible as _list_eligible
from app.schemas.advisor import ProfileUpdateEvent, ProposalEvent, QuestionEvent
from app.schemas.plans import PlanOp, ProposedChange, RejectedOption


@dataclass
class ToolContext:
    db: Session
    student: models.Student
    conversation_id: int | None = None
    events: list[BaseModel] = field(default_factory=list)  # pushed to the UI after the call
    end_turn: bool = False


@dataclass
class ToolResult:
    data: Any
    summary: str


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., ToolResult]
    args_model: type[BaseModel]

    def schema(self) -> dict:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": schema,
        }

    def call(self, ctx: ToolContext, args: dict) -> ToolResult:
        parsed = self.args_model.model_validate(args)
        return self.fn(ctx, **{k: getattr(parsed, k) for k in type(parsed).model_fields})


REGISTRY: dict[str, Tool] = {}


def tool(fn):
    params = list(inspect.signature(fn).parameters.values())[1:]
    fields = {
        p.name: (p.annotation, ... if p.default is inspect.Parameter.empty else p.default)
        for p in params
    }
    args_model = create_model(
        f"{fn.__name__}_args", __config__=ConfigDict(extra="forbid"), **fields
    )
    REGISTRY[fn.__name__] = Tool(fn.__name__, inspect.getdoc(fn) or "", fn, args_model)
    return fn


@tool
def get_plan_state(ctx: ToolContext) -> ToolResult:
    """Get the student's current plan: every placement by term, requirement progress,
    and any rule violations. Call this before suggesting changes."""
    state = services.plan_state(ctx.db, ctx.student)
    missing = [r.label for r in state.audit.requirements if r.status == "missing"]
    open_slots = [p for p in state.plan.placements if p.slot and not p.course]
    summary = f"{len(state.plan.placements)} placements, {len(open_slots)} open slots"
    if missing:
        summary += f", missing: {', '.join(missing)}"
    if state.violations:
        summary += f", {len(state.violations)} issues"
    return ToolResult(state.model_dump(mode="json"), summary)


@tool
def get_course(ctx: ToolContext, code: str) -> ToolResult:
    """Look up one course by code (e.g. "CS 4780"): title, description, credits,
    prerequisites, and which terms it has been offered."""
    course = get_catalog().get(code)
    if course is None:
        return ToolResult(None, f"{code} not found")
    return ToolResult(course.model_dump(mode="json"), f"{course.code} · {course.title}")


@tool
def search_courses(ctx: ToolContext, query: str, limit: int = 10) -> ToolResult:
    """Search courses by code, title or description keywords."""
    found = get_catalog().search(query, limit)
    data = [{"code": c.code, "title": c.title, "credits": c.credits} for c in found]
    return ToolResult(data, f"{len(found)} matches for “{query}”")


@tool
def list_eligible(ctx: ToolContext, requirement_id: str, term: str, limit: int = 25) -> ToolResult:
    """Courses that would satisfy a requirement in a given term (e.g. "ls", "SP27"):
    they match the rule, prerequisites are done by then, and they've been offered
    in that season before. Use requirement ids from get_plan_state."""
    st = ctx.student
    program = services.program_for(st)
    req = next((r for r in program.all_requirements() if r.id == requirement_id), None)
    if req is None:
        return ToolResult(None, f"no requirement {requirement_id}")
    plan = services.plan_schema(ctx.db, st, services.get_plan(ctx.db, st))
    courses = _list_eligible(req, term, plan.terms, plan.placements, get_catalog())
    data = {
        "count": len(courses),
        "courses": [
            {"code": c.code, "title": c.title, "credits": c.credits} for c in courses[:limit]
        ],
    }
    return ToolResult(data, f"{len(courses)} courses fit")


@tool
def read_profile(ctx: ToolContext) -> ToolResult:
    """What we know about the student: goals and preferences, each marked as
    stated by them, inferred by you, or still open."""
    facts = services.visible_facts(ctx.db, ctx.student, ctx.conversation_id)
    data = [
        {"id": f.id, "dimension": f.dimension, "value": f.value, "text": f.text, "status": f.status}
        for f in facts
    ]
    return ToolResult(data, f"{len(facts)} facts on file" if facts else "nothing on file")


@tool
def update_profile(
    ctx: ToolContext,
    dimension: str,
    value: str,
    text: str,
    status: Literal["stated", "inferred", "open"] = "stated",
    evidence: str | None = None,
) -> ToolResult:
    """Record something about the student. Use status "stated" only for things they
    said directly; "inferred" for your own guesses; "open" for questions they asked
    to leave for later. `text` is a short sentence the student will see on their
    profile. Dimensions: career_track, grad_school, work_style, max_heavy_per_term,
    ls_goal, interest, term_load, note."""
    st = ctx.student
    row = models.ProfileFact(
        student_id=st.id,
        dimension=dimension,
        value=value,
        text=text,
        status=status,
        confidence=1.0 if status == "stated" else 0.5,
        evidence=evidence,
        conversation_id=None if st.memory_enabled else ctx.conversation_id,
        last_confirmed_at=now() if status == "stated" else None,
    )
    ctx.db.add(row)
    ctx.db.commit()
    fact = services.fact_schema(row)
    ctx.events.append(ProfileUpdateEvent(fact=fact))
    return ToolResult(fact.model_dump(mode="json"), f"saved ({status})")


@tool
def propose_changes(
    ctx: ToolContext,
    summary: str,
    ops: list[PlanOp],
    changes: list[ProposedChange],
    rejected: list[RejectedOption] = [],  # noqa: B006
) -> ToolResult:
    """Propose plan edits for the student to review. Nothing changes until they
    click Apply. `ops` are the edits; `changes` explain each moved/added course in
    plain words; `rejected` lists options you considered and why you didn't pick
    them. The planner re-checks the result and reports any violations back."""
    proposal = services.create_proposal(ctx.db, ctx.student, ops, summary, changes, rejected)
    ctx.events.append(ProposalEvent(proposal=proposal))
    blocking = [v.message for v in proposal.violations if v.blocking]
    summary = "proposal ready" if not blocking else f"proposal has {len(blocking)} problems"
    return ToolResult(proposal.model_dump(mode="json"), summary)


@tool
def ask_student(
    ctx: ToolContext, question: str, options: list[str], dimension: str | None = None
) -> ToolResult:
    """Ask the student one multiple-choice question and end your turn. Only ask
    when the answer would change your recommendation. Their reply arrives as the
    next message."""
    ctx.events.append(QuestionEvent(question=question, options=options, dimension=dimension))
    ctx.end_turn = True
    return ToolResult({"shown": True}, "asked")


def call_tool(ctx: ToolContext, name: str, args: dict) -> ToolResult:
    if name not in REGISTRY:
        return ToolResult(None, f"unknown tool {name}")
    return REGISTRY[name].call(ctx, args)


def tool_schemas() -> list[dict]:
    return [REGISTRY[name].schema() for name in sorted(REGISTRY)]
