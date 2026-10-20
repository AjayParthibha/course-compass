"""Plan, proposal and profile operations shared by the API routes and advisor tools."""

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.catalog.store import get_catalog
from app.config import get_settings
from app.planner.audit import audit
from app.planner.ops import apply_ops, term_index, term_label, terms_between
from app.planner.solver import RepairRequest, RepairResult, repair
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
        approvals=st.approvals or [],
        memory_enabled=st.memory_enabled,
        onboarded=bool(st.plans),
    )


def program_for(st: models.Student):
    if not (st.program and st.catalog_year):
        raise NotReady
    return get_program(st.program, st.catalog_year).with_approvals(st.approvals or [])


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


def annotate(placements: list[s.Placement]) -> list[s.Placement]:
    """Fill in what responses show but the plan history doesn't store."""
    catalog = get_catalog()
    for p in placements:
        course = catalog.get(p.course) if p.course else None
        if course:
            p.title = course.title
        p.counts_as = sorted(catalog.prereq_credit(course.code) - {course.code}) if course else []
    return placements


def plan_schema(db: Session, st: models.Student, plan: models.Plan, placements=None) -> s.Plan:
    placements = placements if placements is not None else current_placements(db, plan)
    return s.Plan(
        id=plan.id,
        name=plan.name,
        version=plan.version,
        program=st.program,
        terms=terms_between(st.entering_term, st.graduation_term),
        current_term=get_settings().current_term,
        placements=annotate(placements),
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
            placements=[p.model_dump(exclude={"counts_as"}) for p in placements],
            origin=origin,
            note=note,
        )
    )
    db.commit()


def preview_ops(db: Session, st: models.Student, ops: list[s.PlanOp], origin="user") -> s.PlanState:
    plan = get_plan(db, st)
    current = plan_schema(db, st, plan)
    new = apply_ops(current.placements, ops, get_catalog(), current.terms, origin, slot_labels(st))
    return evaluate(st, current.model_copy(update={"placements": annotate(new)}))


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
    # a settings version holds the same placements as its parent; step past it too, or the
    # next undo would "restore" the plan the student is already looking at
    while target and target.origin == "settings" and target.parent_version:
        target = version_row(db, plan, target.parent_version)
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
            if term not in terms or term_index(term) <= term_index(current):
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
    extra_checks: list[str] = (),
    solver: dict | None = None,
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
    checks += extra_checks
    row = models.Proposal(
        plan_id=plan.id,
        base_version=plan.version,
        summary=summary,
        ops=[o.model_dump() for o in ops],
        details={
            "changes": [c.model_dump() for c in changes],
            "rejected": [r.model_dump() for r in rejected],
            "checks": checks,
            **({"solver": solver} if solver else {}),
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


def repair_plan(
    db: Session, st: models.Student, request: RepairRequest, summary: str
) -> tuple[RepairResult, s.Proposal | None]:
    """Ask the solver for the smallest change that meets `request` and, when there is
    one, save it as a proposal the student can preview and apply. Raises RequestError
    when the request names a placement, course or term that doesn't exist."""
    plan = plan_schema(db, st, get_plan(db, st))
    program = program_for(st)
    catalog = get_catalog()
    result = repair(
        plan.placements,
        plan.terms,
        plan.current_term,
        catalog,
        program,
        request,
        max_credits=st.max_credits,
        term_caps=st.term_caps or {},
        slot_labels=slot_labels(st),
    )
    if result.status != "solved" or not result.ops:
        return result, None
    changes = explain_changes(
        plan.placements, plan.terms, result.ops, request, program, catalog, st
    )
    checks = ["Every degree requirement the plan met before is still met"]
    if not result.under_minimum:
        checks.append("No term is pushed under the 12-credit full-time minimum")
    if result.optimal:
        n = result.moved + result.added + result.removed + result.replaced
        checks.append(f"No smaller change does this ({n} change{'s' if n != 1 else ''})")
    proposal = create_proposal(
        db,
        st,
        result.ops,
        summary,
        changes,
        extra_checks=checks,
        solver=s.SolverSummary(**result.model_dump()).model_dump(),
    )
    return result, proposal


def explain_changes(placements, terms, ops, request: RepairRequest, program, catalog, st):
    """A plain reason for each change the solver made, from what it was fixing."""
    by_id = {p.id: p for p in placements}
    before = validate(placements, terms, catalog, st.max_credits, st.term_caps)
    broken = {
        pid: v.message
        for v in before
        if v.kind in ("prereq", "offering")
        for pid in v.placement_ids
    }
    caps = {**(st.term_caps or {}), **request.term_caps}
    labels = {r.id: r.label for r in program.all_requirements()}
    out: list[s.ProposedChange] = []
    seen_removes: set[str] = set()
    for op in ops:
        if isinstance(op, s.MoveOp):
            p = by_id[op.placement_id]
            if p.id in request.keep:
                continue
            if request.move.get(p.id) == op.term:
                reason = "You asked for it here"
            elif p.id in broken:
                reason = f"Fixes this: {broken[p.id]}"
            elif p.term in request.lighter_terms:
                reason = f"Lightens {term_label(p.term)}"
            elif p.term in caps:
                reason = f"Brings {term_label(p.term)} within {caps[p.term]} credits"
            elif request.graduate_by and term_index(p.term) > term_index(request.graduate_by):
                reason = f"Finishes by {term_label(request.graduate_by)}"
            else:
                reason = "Makes room for the rest of the change"
            out.append(
                s.ProposedChange(course=_label(p), from_term=p.term, to_term=op.term, reason=reason)
            )
        elif isinstance(op, s.RemoveOp) and op.placement_id not in seen_removes:
            seen_removes.add(op.placement_id)
            p = by_id[op.placement_id]
            asked = p.id in request.remove or (p.course and p.course in request.avoid_courses)
            reason = "You asked to drop it" if asked else "Not needed once the rest moves"
            out.append(s.ProposedChange(course=_label(p), from_term=p.term, reason=reason))
        elif isinstance(op, s.ReplaceOp):
            p = by_id[op.placement_id]
            label = p.slot_label or labels.get(p.slot, p.slot)
            out.append(
                s.ProposedChange(
                    course=op.course, to_term=p.term, reason=f"Fills your open {label} slot"
                )
            )
        elif isinstance(op, s.AddOp):
            wished = op.course and any(
                catalog.get(w.course) and catalog.get(w.course).code == op.course
                for w in request.add
            )
            name = op.course or labels.get(op.slot, op.slot)
            reason = "You asked for it" if wished else "Keeps that requirement on track"
            if op.slot:
                name = f"Open slot: {name}"
            out.append(s.ProposedChange(course=name, to_term=op.term, reason=reason))
    return out


def _label(p: s.Placement) -> str:
    return p.course or f"Open slot: {p.slot_label or p.slot}"
