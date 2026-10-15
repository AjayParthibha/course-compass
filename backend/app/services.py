"""Plan, proposal and profile operations shared by the API routes and advisor tools."""

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.catalog.store import get_catalog
from app.config import get_settings
from app.planner.audit import audit
from app.planner.ops import apply_ops, term_index, term_label, terms_between
from app.planner.validate import prereq_edges, validate
from app.requirements.loader import get_program
from app.schemas import plans as s
from app.schemas.profile import ProfileFact, Student

parse_ops = TypeAdapter(list[s.PlanOp])


class NotReady(Exception):
    """Student hasn't finished onboarding, so there's no plan yet."""


class Stale(Exception):
    pass


class SettingsConflict(Exception):
    """A settings change would drop terms that still have courses in them."""


class CannotUndo(Exception):
    pass


def student_schema(st: models.Student) -> Student:
    return Student(
        id=st.id,
        code=st.code,
        program=st.program,
        catalog_year=st.catalog_year,
        entering_term=st.entering_term,
        graduation_term=st.graduation_term,
        max_credits=st.max_credits,
        term_caps=st.term_caps or {},
        memory_enabled=st.memory_enabled,
        onboarded=bool(st.plans),
    )


def program_for(st: models.Student):
    if not (st.program and st.catalog_year):
        raise NotReady
    return get_program(st.program, st.catalog_year)


def slot_labels(st: models.Student) -> dict[str, str]:
    return {r.id: r.label for r in program_for(st).all_requirements()}


def get_plan(db: Session, st: models.Student) -> models.Plan:
    if not st.plans:
        raise NotReady
    return st.plans[0]


def version_row(db: Session, plan: models.Plan, version: int) -> models.PlanVersion | None:
    return db.scalar(
        select(models.PlanVersion).where(
            models.PlanVersion.plan_id == plan.id, models.PlanVersion.version == version
        )
    )


def current_placements(db: Session, plan: models.Plan) -> list[s.Placement]:
    row = version_row(db, plan, plan.version)
    return [s.Placement.model_validate(p) for p in row.placements] if row else []


def plan_schema(db: Session, st: models.Student, plan: models.Plan, placements=None) -> s.Plan:
    placements = placements if placements is not None else current_placements(db, plan)
    catalog = get_catalog()
    for p in placements:
        if p.course and (course := catalog.get(p.course)):
            p.title = course.title
    return s.Plan(
        id=plan.id,
        name=plan.name,
        version=plan.version,
        program=st.program,
        terms=terms_between(st.entering_term, st.graduation_term),
        current_term=get_settings().current_term,
        placements=placements,
    )


def evaluate(st: models.Student, plan: s.Plan) -> s.PlanState:
    catalog = get_catalog()
    return s.PlanState(
        plan=plan,
        audit=audit(plan.placements, program_for(st), catalog),
        violations=validate(
            plan.placements, plan.terms, catalog, st.max_credits, term_caps=st.term_caps
        ),
        edges=[s.PlanEdge(source=a, target=b) for a, b in prereq_edges(plan.placements, catalog)],
    )


def plan_state(db: Session, st: models.Student) -> s.PlanState:
    plan = get_plan(db, st)
    return evaluate(st, plan_schema(db, st, plan))


HEAD = -1


def commit(
    db: Session,
    plan: models.Plan,
    placements: list[s.Placement],
    origin: str,
    note: str | None = None,
    parent: int | None = HEAD,
):
    """Save placements as the plan's new version. `parent` defaults to the current one."""
    if parent == HEAD:
        parent = plan.version or None
    plan.version += 1
    db.add(
        models.PlanVersion(
            plan_id=plan.id,
            version=plan.version,
            parent_version=parent,
            placements=[p.model_dump() for p in placements],
            origin=origin,
            note=note,
        )
    )
    db.commit()


def preview_ops(db: Session, st: models.Student, ops: list[s.PlanOp], origin="user") -> s.PlanState:
    plan = get_plan(db, st)
    current = plan_schema(db, st, plan)
    new = apply_ops(current.placements, ops, get_catalog(), current.terms, origin, slot_labels(st))
    return evaluate(st, current.model_copy(update={"placements": new}))


def apply_plan_ops(
    db: Session, st: models.Student, ops: list[s.PlanOp], origin="user"
) -> s.PlanState:
    state = preview_ops(db, st, ops, origin)
    commit(db, get_plan(db, st), state.plan.placements, origin)
    return plan_state(db, st)


def undo(db: Session, st: models.Student) -> s.PlanState:
    """Step back one edit. The undo is saved as a new version pointing at the parent of
    the version it undid, so undoing again keeps walking back through history."""
    plan = get_plan(db, st)
    head = version_row(db, plan, plan.version)
    # a graduation change keeps the placements as they were; undo the edit before it
    while head and head.origin == "settings" and head.parent_version:
        head = version_row(db, plan, head.parent_version)
    target = version_row(db, plan, head.parent_version) if head and head.parent_version else None
    if target is None:
        return plan_state(db, st)
    placements = [s.Placement.model_validate(p) for p in target.placements]
    terms = terms_between(st.entering_term, st.graduation_term)
    outside = sorted({p.term for p in placements if p.term not in terms}, key=term_index)
    if outside:
        raise CannotUndo(
            f"Can't undo: before that edit your plan had courses or slots in "
            f"{', '.join(map(term_label, outside))}, which is no longer part of your plan. "
            "Change your graduation term back first."
        )
    commit(db, plan, placements, "user", "undo", parent=target.parent_version)
    return plan_state(db, st)


OUTDATED = "This suggestion was made for an earlier version of your plan. Ask the advisor again."


def proposal_status(row: models.Proposal, plan_version: int) -> str:
    if row.status == "stale" or (row.status == "pending" and row.base_version != plan_version):
        return "outdated"
    return row.status


# how far past the current term a graduation date may be set
MAX_TERMS_AHEAD = 8


def update_plan_settings(
    db: Session,
    st: models.Student,
    graduation_term: str | None = None,
    max_credits: int | None = None,
    term_caps: dict[str, int] | None = None,
) -> None:
    """Change graduation term and credit caps for every plan of the student.

    Raises ValueError for terms out of range and SettingsConflict when an earlier
    graduation would drop terms that still hold placements.
    """
    if not (st.entering_term and st.graduation_term):
        raise NotReady
    current = get_settings().current_term
    grad = graduation_term or st.graduation_term
    if graduation_term and graduation_term != st.graduation_term:
        offset = term_index(grad) - term_index(current)
        if not 0 <= offset <= MAX_TERMS_AHEAD:
            raise ValueError(
                f"graduation has to be between {term_label(current)} and "
                f"{MAX_TERMS_AHEAD // 2} years from now"
            )
    try:
        terms = terms_between(st.entering_term, grad)
    except ValueError:
        raise ValueError(f"{term_label(grad)} isn't reachable from {st.entering_term}") from None

    if grad != st.graduation_term:
        keep = set(terms)
        stranded: dict[str, dict[str, None]] = {}
        for plan in st.plans:
            for p in current_placements(db, plan):
                if p.term not in keep:
                    name = p.course or p.slot_label or "an open slot"
                    stranded.setdefault(p.term, {})[name] = None
        if stranded:
            dropped = "; ".join(
                f"{term_label(t)}: {', '.join(stranded[t])}"
                for t in sorted(stranded, key=term_index)
            )
            raise SettingsConflict(
                f"Graduating in {term_label(grad)} would drop terms that still have courses "
                f"or slots ({dropped}). Move or remove them first."
            )

    if term_caps is not None:
        for term in term_caps:
            if term not in terms or term_index(term) < term_index(current):
                raise ValueError(f"{term_label(term)} isn't a remaining term in your plan")
        st.term_caps = dict(term_caps)
    else:
        st.term_caps = {t: c for t, c in (st.term_caps or {}).items() if t in terms}
    if max_credits is not None:
        st.max_credits = max_credits
    if grad != st.graduation_term:
        st.graduation_term = grad
        # a new version, so proposals made for the old terms show as outdated
        for plan in st.plans:
            placements = current_placements(db, plan)
            commit(db, plan, placements, "settings", f"Changed graduation to {term_label(grad)}")
    db.commit()


def proposal_schema(row: models.Proposal, plan_version: int) -> s.Proposal:
    return s.Proposal(
        id=row.id,
        plan_id=row.plan_id,
        base_version=row.base_version,
        summary=row.summary,
        ops=row.ops,
        violations=row.violations,
        status=proposal_status(row, plan_version),
        created_at=row.created_at,
        **row.details,
    )


def create_proposal(
    db: Session,
    st: models.Student,
    ops: list[s.PlanOp],
    summary: str,
    changes: list[s.ProposedChange] = (),
    rejected: list[s.RejectedOption] = (),
) -> s.Proposal:
    plan = get_plan(db, st)
    state = preview_ops(db, st, ops, origin="advisor")
    blocking = [v for v in state.violations if v.blocking]
    checks = []
    if not any(v.kind == "prereq" for v in blocking):
        checks.append("Every prerequisite still comes before the course that needs it")
    if not any(v.kind == "credits_high" for v in blocking):
        checks.append(
            "No term goes above its credit cap"
            if st.term_caps
            else f"No term goes above {st.max_credits} credits"
        )
    row = models.Proposal(
        plan_id=plan.id,
        base_version=plan.version,
        summary=summary,
        ops=[o.model_dump() for o in ops],
        details={
            "changes": [c.model_dump() for c in changes],
            "rejected": [r.model_dump() for r in rejected],
            "checks": checks,
        },
        violations=[v.model_dump() for v in state.violations],
    )
    db.add(row)
    db.commit()
    return proposal_schema(row, plan.version)


def get_proposal(db: Session, st: models.Student, proposal_id: int) -> models.Proposal | None:
    row = db.get(models.Proposal, proposal_id)
    if row is None or row.plan_id != get_plan(db, st).id:
        return None
    return row


def apply_proposal(db: Session, st: models.Student, row: models.Proposal) -> s.PlanState:
    plan = get_plan(db, st)
    status = proposal_status(row, plan.version)
    if status == "outdated":
        raise Stale(OUTDATED)
    if status != "pending":
        raise Stale(f"This suggestion was already {status}.")
    state = apply_plan_ops(db, st, parse_ops.validate_python(row.ops), origin="advisor")
    row.status = "applied"
    db.commit()
    return state


def fact_schema(row: models.ProfileFact) -> ProfileFact:
    return ProfileFact.model_validate(row, from_attributes=True)


def visible_facts(db: Session, st: models.Student, conversation_id: int | None = None):
    """Facts the advisor may use. With memory off, only this conversation's facts."""
    q = select(models.ProfileFact).where(
        models.ProfileFact.student_id == st.id,
        models.ProfileFact.status.not_in(["superseded"]),
    )
    if not st.memory_enabled:
        q = q.where(models.ProfileFact.conversation_id == conversation_id)
    return list(db.scalars(q.order_by(models.ProfileFact.id)))
