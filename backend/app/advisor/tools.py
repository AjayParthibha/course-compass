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
from app.planner.elicit import plan_question as _plan_question
from app.planner.eligible import list_eligible as _list_eligible
from app.planner.ops import term_label
from app.planner.recommend import standard_courses
from app.planner.solver import RepairRequest, RequestError
from app.schemas.advisor import ProfileUpdateEvent, ProposalEvent, QuestionEvent
from app.schemas.plans import AdvisorOp, ProposedChange, RejectedOption


@dataclass
class ToolContext:
    db: Session
    student: models.Student
    conversation_id: int | None = None
    events: list[BaseModel] = field(default_factory=list)  # pushed to the UI after the call
    # proposals made with propose_changes this turn; events is emptied after every call
    drafts: list[int] = field(default_factory=list)
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
    in that season before. Use requirement ids from get_plan_state.

    The list is ranked for this student, best fit first, the same way Explore ranks it.
    Each course's `why` says what put it there and where that came from: "stated" is
    something the student told us, "inference" is an unconfirmed guess (confirm it
    before leaning on it), "plan" is their plan. `official` is roster information,
    kept apart from those reasons. Courses the student marked "not for me" are left out
    and listed under `not_for_me`; don't suggest them."""
    st = ctx.student
    program = services.program_for(st)
    req = next((r for r in program.all_requirements() if r.id == requirement_id), None)
    if req is None:
        return ToolResult(None, f"no requirement {requirement_id}")
    plan = services.plan_schema(ctx.db, st, services.get_plan(ctx.db, st))
    if term not in plan.terms:
        return ToolResult(None, f"{term} isn't one of the plan's terms ({', '.join(plan.terms)})")
    courses = _list_eligible(req, term, plan.placements, get_catalog())
    ranking, hidden = services.rank_for_student(
        ctx.db, st, courses, plan.placements, ctx.conversation_id
    )
    data = {
        "count": len(ranking.courses),
        "ranked_by_profile": ranking.personalized,
        "courses": [
            {
                "code": r.course.code,
                "title": r.course.title,
                "credits": r.course.credits,
                "why": [{"text": x.text, "basis": x.basis} for x in r.reasons],
                "official": {
                    "prerequisites": r.course.prereq_text or "none listed",
                    "offered": f"{len(r.course.terms_offered)} of the recent terms we have",
                },
            }
            for r in ranking.courses[:limit]
        ],
        "not_for_me": [c.code for c, _ in hidden],
    }
    n = len(ranking.courses)
    summary = f"{n} course fits" if n == 1 else f"{n} courses fit"
    if ranking.personalized:
        summary += ", ranked by their profile"
    return ToolResult(data, summary)


@tool
def plan_question(ctx: ToolContext, requirement_id: str, term: str) -> ToolResult:
    """Before recommending courses for a slot, check whether a question is worth
    asking first. It tries each likely answer to each question you could ask, ranks the
    slot's courses as if the student had given it, and sees how much the top picks
    move. If `ask` is true, ask exactly that question with ask_student (its text,
    options and dimension), then save their answer with update_profile using the
    option's `save` facts. If `ask` is false, recommend from list_eligible without
    asking. It never suggests questions the student already answered or asked to
    leave for later."""
    st = ctx.student
    program = services.program_for(st)
    req = next((r for r in program.all_requirements() if r.id == requirement_id), None)
    if req is None:
        return ToolResult(None, f"no requirement {requirement_id}")
    plan = services.plan_schema(ctx.db, st, services.get_plan(ctx.db, st))
    if term not in plan.terms:
        return ToolResult(None, f"{term} isn't one of the plan's terms ({', '.join(plan.terms)})")
    courses = _list_eligible(req, term, plan.placements, get_catalog())
    ranking, _ = services.rank_for_student(
        ctx.db, st, courses, plan.placements, ctx.conversation_id
    )
    facts = [
        services.fact_schema(f) for f in services.visible_facts(ctx.db, st, ctx.conversation_id)
    ]
    result = _plan_question(
        [r.course for r in ranking.courses],
        facts,
        plan.placements,
        get_catalog(),
        standard_courses(program),
        req.label.lower(),
    )
    q = result.ask
    data = {
        "ask": q is not None,
        "reason": result.reason,
        "question": q
        and {
            "text": q.text,
            "dimension": q.dimension,
            "options": [
                {
                    "label": o.label,
                    "save": [{"dimension": d, "value": v} for d, v in o.facts],
                    "top_picks_if_chosen": o.picks,
                }
                for o in q.options
            ],
        },
    }
    if q:
        return ToolResult(data, f"worth asking about {q.dimension} ({q.disagreement:.0%} apart)")
    return ToolResult(data, "no question needed")


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
    ops: list[AdvisorOp],
    changes: list[ProposedChange],
    rejected: list[RejectedOption] = [],  # noqa: B006
) -> ToolResult:
    """Propose plan edits for the student to review. Nothing changes until they
    click Apply. `ops` are the edits; `changes` explain each moved/added course in
    plain words; `rejected` lists options you considered and why you didn't pick
    them. The planner re-checks the result and reports any violations back.
    Placements with `locked: true` are kept in their term by the student: don't
    move, remove or replace them."""
    proposal = services.create_proposal(ctx.db, ctx.student, ops, summary, changes, rejected)
    ctx.events.append(ProposalEvent(proposal=proposal))
    ctx.drafts.append(proposal.id)
    blocking = [v.message for v in proposal.violations if v.blocking]
    summary = "proposal ready" if not blocking else f"proposal has {len(blocking)} problems"
    return ToolResult(proposal.model_dump(mode="json"), summary)


@tool
def repair_plan(ctx: ToolContext, summary: str, request: RepairRequest) -> ToolResult:
    """Find the smallest valid change that does what the student asked, and show it to
    them as a proposal (nothing changes until they apply it). Use this for structural
    changes: lighter or capped terms, dropping or adding a course, moving a course to a
    term, graduating earlier, fixing prerequisite or season problems. It moves courses
    and open slots, can add open slots or a course from a short list of alternatives (CS
    4410 or CS 4414), fills an open slot with a course the student asked for, never picks
    electives, and keeps every requirement the plan already meets.

    Fill `request` from what the student said; use placement ids from get_plan_state
    for keep/move/remove, and terms like "SP27". Leave out what they didn't ask for. For
    "make a term lighter", put it in lighter_terms and let the solver choose how much (at
    least one course out, never under 12 credits); set term_caps only for a number the
    student gave. Only set allow_removing_courses when they agreed to drop courses.

    The result lists `changes` in plain words; tell the student what moves where, and use
    `credit_changes` to say which terms get lighter and which get heavier. If the
    request can't be met, `conflicts` says why and `alternatives` lists nearby versions
    that were checked and do work. Offer only those alternatives, never ones you came up
    with, and don't work around the conflict with propose_changes. A broken draft you
    made earlier in this turn is withdrawn automatically."""
    withdrawn = _withdraw_broken_drafts(ctx)
    try:
        result, proposal = services.repair_plan(ctx.db, ctx.student, request, summary)
    except RequestError as e:
        return ToolResult({"error": str(e)}, f"request rejected: {e}")
    if proposal:
        ctx.events.append(ProposalEvent(proposal=proposal))
    data = {
        "status": result.status,
        "changes": [_change_text(c) for c in proposal.changes] if proposal else [],
        "conflicts": result.conflicts,
        "alternatives": result.alternatives,
        "smallest_possible": result.optimal,
        # every term whose credits change, including ones that get heavier
        "credit_changes": result.term_loads,
        # terms this takes under 12 credits (only when the student set that cap): say so
        "under_full_time_minimum": result.under_minimum,
        "withdrew_earlier_drafts": withdrawn,
    }
    if result.status == "infeasible":
        summary = f"can't be done ({len(result.alternatives)} alternatives that work)"
    elif result.status == "timeout":
        summary = "no answer in time"
    elif not proposal:
        summary = "nothing needs to change"
    else:
        n = result.moved + result.added + result.removed + result.replaced
        summary = f"proposal ready · {n} change{'s' if n != 1 else ''}"
    return ToolResult(data, summary)


def _change_text(c: ProposedChange) -> str:
    """CS 4701: Fall ’27 → Spring ’28 (you asked for it here)"""
    if c.from_term and c.to_term:
        where = f"{term_label(c.from_term)} → {term_label(c.to_term)}"
    elif c.to_term:
        where = f"added in {term_label(c.to_term)}"
    else:
        where = f"removed from {term_label(c.from_term)}" if c.from_term else "removed"
    return f"{c.course}: {where} ({c.reason[0].lower() + c.reason[1:]})"


def _withdraw_broken_drafts(ctx: ToolContext) -> list[int]:
    """Discard proposals made earlier in this turn that the planner flagged, so the
    student isn't left with a broken draft next to the working one."""
    ids = []
    for pid in ctx.drafts:
        row = services.get_proposal(ctx.db, ctx.student, pid)
        if row is None or row.status != "pending":
            continue
        if any(v.get("blocking") for v in row.violations):
            row.status = "discarded"
            ids.append(row.id)
    if ids:
        ctx.db.commit()
    return ids


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
