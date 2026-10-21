from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, services
from app.catalog.store import get_catalog
from app.models import now
from app.planner.audit import audit, cross_listed_with, needed, subjects_of
from app.planner.eligible import by_offering, courses_by_subject, list_eligible, listed_under
from app.planner.recommend import rank, rank_areas, standard_courses
from app.routes.auth import DB, CurrentStudent
from app.schemas.courses import Course
from app.schemas.explore import (
    ApprovalState,
    Area,
    BlockedCourse,
    Candidate,
    HiddenCourse,
    OfficialInfo,
    SlotAreas,
    SlotCandidates,
)
from app.schemas.plans import Placement
from app.schemas.profile import ProfileFact
from app.schemas.requirements import Requirement

router = APIRouter(tags=["explore"])

NOT_INTERESTED = "not_interested"


def not_interested_facts(db: Session, student: models.Student, code: str | None = None):
    """The student's "not for me" facts; with `code`, only those that hide that course,
    including facts saved under one of its cross-listings."""
    q = select(models.ProfileFact).where(
        models.ProfileFact.student_id == student.id,
        models.ProfileFact.dimension == NOT_INTERESTED,
        models.ProfileFact.status == "stated",
    )
    facts = list(db.scalars(q.order_by(models.ProfileFact.id)))
    if code is None:
        return facts
    catalog = get_catalog()
    same = catalog.equivalents(code)
    return [f for f in facts if f.value in same or code in catalog.equivalents(f.value)]


def _slot(slot_id: str, term: str, db: Session, student: models.Student):
    program = services.program_for(student)
    req = next((r for r in program.all_requirements() if r.id == slot_id), None)
    if req is None:
        raise HTTPException(404, f"no requirement {slot_id}")
    plan = services.plan_schema(db, student, services.get_plan(db, student))
    if term not in plan.terms:
        raise HTTPException(400, f"{term} isn't in your plan")
    return program, req, plan


def counted_toward(req: Requirement, placements: list[Placement], program, skip: str | None):
    """Courses the audit already counts toward `req`, leaving out placement `skip` (the
    one being filled or replaced)."""
    status = {r.id: r for r in _walk(audit(placements, program, get_catalog()).requirements)}
    ids = set(status[req.id].filled) if req.id in status else set()
    return [p for p in placements if p.id in ids and p.course and p.id != skip]


def _walk(statuses):
    for r in statuses:
        yield r
        yield from _walk(r.children)


def shared_subject(req: Requirement, courses: list[Course]) -> str | None:
    excluded = set(req.filter.exclude_subjects) if req.filter else set()
    common = set.intersection(*(subjects_of(c) for c in courses)) - excluded if courses else set()
    return min(common) if common else None


@router.get("/slots/{slot_id}/areas")
def areas(
    slot_id: str, term: str, db: DB, student: CurrentStudent, placement: str | None = None
) -> SlotAreas:
    """Subjects a same-subject rule (the external specialization) could be filled from,
    best fit first: the one the plan already uses, then ones with courses ready to take,
    then ones that match the student's interests (with the reasons), then ones that
    build on courses in the plan."""
    program, req, plan = _slot(slot_id, term, db, student)
    catalog = get_catalog()
    counted = counted_toward(req, plan.placements, program, placement)
    counted_courses = [c for p in counted if (c := catalog.get(p.course))]
    chosen = shared_subject(req, counted_courses)
    groups = courses_by_subject(req, term, plan.placements, catalog)
    facts = [services.fact_schema(f) for f in services.visible_facts(db, student)]
    interest = rank_areas(
        {s: g.ready + [c for c, _ in g.blocked] for s, g in groups.items()},
        facts,
        catalog,
        req.max_cross_listed,
    )

    out: list[Area] = []
    fit: dict[str, int] = {}
    for subject, group in groups.items():
        here = [c.code for c in counted_courses if subject in subjects_of(c)]
        if len(group.ready) + len(group.blocked) + len(here) < needed(req):
            continue  # too few courses under this subject to make a specialization
        builds_on = [
            c
            for p in sorted(plan.placements, key=lambda p: plan.terms.index(p.term))
            if p.course and (c := catalog.get(p.course)) and subject in subjects_of(c)
        ]
        # an upper-level course in the subject says more than an intro one
        fit[subject] = sum(c.level // 1000 for c in builds_on)
        out.append(
            Area(
                subject=subject,
                name=catalog.subject_name(subject),
                ready=len(group.ready),
                blocked=len(group.blocked),
                builds_on=[c.code for c in builds_on],
                counted=here,
                sample=[c.summary() for c in _sample(group.ready, interest[subject])],
                reasons=interest[subject].reasons,
            )
        )
    out.sort(
        key=lambda a: (
            a.subject != chosen,
            -len(a.counted),
            a.ready == 0,
            -interest[a.subject].score,
            -interest[a.subject].count,
            -fit[a.subject],
            -a.ready,
            a.subject,
        )
    )
    return SlotAreas(
        slot_id=req.id,
        slot_label=req.label,
        term=term,
        needed=needed(req),
        chosen=chosen,
        counted=[c.summary() for c in counted_courses],
        caps=req.max_cross_listed,
        areas=out,
        approval=approval_state(req, student),
    )


@router.get("/slots/{slot_id}/candidates")
def candidates(
    slot_id: str,
    term: str,
    db: DB,
    student: CurrentStudent,
    limit: int = 3,
    subject: str | None = None,
    placement: str | None = None,
) -> SlotCandidates:
    """Eligible courses for a requirement slot, optionally narrowed to one subject (with
    the courses there that can't go in this term, and why), best fit first: ranked by the
    student's profile and plan (app/planner/recommend.py), each with its reasons. With
    nothing in the profile that bears on the slot, the order is how often each course has
    been offered and no ranking factors are sent, so the page doesn't call it personal."""
    program, req, plan = _slot(slot_id, term, db, student)
    catalog = get_catalog()
    eligible = list_eligible(req, term, plan.placements, catalog)
    blocked: list[BlockedCourse] = []
    if subject:
        shown = {
            listed_under(c, subject, catalog).code: c for c in eligible if subject in subjects_of(c)
        }
        eligible = by_offering([catalog.get(code) or c for code, c in shown.items()])
        group = courses_by_subject(req, term, plan.placements, catalog).get(subject)
        blocked = [
            BlockedCourse(course=c.summary(), reason=why)
            for c, why in (group.blocked if group else [])
        ]
    # a capped cross-listing (at most one CS course) that the plan has already used up
    counted = [
        c
        for p in counted_toward(req, plan.placements, program, placement)
        if (c := catalog.get(p.course))
    ]
    full = [
        s
        for s, cap in req.max_cross_listed.items()
        if sum(cross_listed_with(c, s) for c in counted) >= cap
    ]
    for s in full:
        over = [c for c in eligible if cross_listed_with(c, s)]
        eligible = [c for c in eligible if not cross_listed_with(c, s)]
        cap = req.max_cross_listed[s]
        reason = f"Only {cap} course{'s' if cap > 1 else ''} cross-listed with {s} can count"
        blocked = [BlockedCourse(course=c.summary(), reason=reason) for c in over] + blocked
    not_for_me: dict[str, int] = {}
    for fact in not_interested_facts(db, student):
        for code in catalog.equivalents(fact.value):
            not_for_me.setdefault(code, fact.id)
    hidden = [
        HiddenCourse(course=c.summary(), fact_id=not_for_me[c.code])
        for c in eligible
        if c.code in not_for_me
    ]
    eligible = [c for c in eligible if c.code not in not_for_me]
    # the same facts the advisor sees outside a chat: with memory off, only the ones
    # entered on the profile page or in onboarding
    facts = [services.fact_schema(f) for f in services.visible_facts(db, student)]
    ranking = rank(eligible, facts, plan.placements, catalog, standard_courses(program))
    current_idx = plan.terms.index(plan.current_term) if plan.current_term in plan.terms else -1
    assumed = plan.terms.index(term) > current_idx + 1
    top = [
        Candidate(
            course=c.summary(),
            rank=i + 1,
            reasons=r.reasons,
            official=OfficialInfo(
                prereqs_met=True,
                prereq_note=c.prereq_text or "No prerequisites listed",
                offering_note=f"Offered in {len(c.terms_offered)} of the recent terms we have",
                assumed=assumed,
            ),
            capped_cross_listings=[s for s in req.max_cross_listed if cross_listed_with(c, s)],
        )
        for i, r in enumerate(ranking.courses[:limit])
        for c in [r.course]
    ]
    return SlotCandidates(
        slot_id=req.id,
        slot_label=req.label,
        term=term,
        eligible_count=len(eligible),
        candidates=top,
        factors=ranking.factors if ranking.personalized else [],
        ordering=(
            "Ranked by what you’ve told us and what’s in your plan, then by how often "
            "it’s been offered"
            if ranking.personalized
            else "Sorted by how often it’s been offered, most often first"
        ),
        hidden=hidden,
        same_subject=req.same_subject,
        subject=subject,
        blocked=blocked,
        approval=approval_state(req, student),
    )


def _sample(ready: list[Course], fit, n: int = 3) -> list[Course]:
    """The courses shown under an area: ones that match an interest first, then the
    rest of what's ready, in order."""
    matched = {c.code for c in fit.matches}
    return sorted(ready, key=lambda c: c.code not in matched)[:n]


def approval_state(req: Requirement, student: models.Student) -> ApprovalState | None:
    if not req.approval:
        return None
    return ApprovalState(label=req.approval, approved=req.id in (student.approvals or []))


def _course_or_404(code: str) -> Course:
    course = get_catalog().get(code)
    if course is None:
        raise HTTPException(404, f"no course {code}")
    return course


@router.put("/courses/{code}/not-interested", tags=["profile"])
def mark_not_interested(code: str, db: DB, student: CurrentStudent) -> ProfileFact:
    """Remember that the student doesn't want this course suggested. Saved as a stated
    profile fact, so it shows on the profile page and can be removed there. Marking a
    course whose cross-listing is already marked returns the existing fact."""
    course = _course_or_404(code)
    existing = not_interested_facts(db, student, course.code)
    if existing:
        return services.fact_schema(existing[0])
    row = models.ProfileFact(
        student_id=student.id,
        dimension=NOT_INTERESTED,
        value=course.code,
        text=f"Not interested in {course.code} ({course.title})",
        status="stated",
        evidence="Marked “Not for me” on Explore",
        last_confirmed_at=now(),
    )
    db.add(row)
    db.commit()
    return services.fact_schema(row)


@router.delete("/courses/{code}/not-interested", status_code=204, tags=["profile"])
def unmark_not_interested(code: str, db: DB, student: CurrentStudent) -> None:
    """Show the course again, whichever of its cross-listed codes it was hidden under."""
    course = _course_or_404(code)
    for row in not_interested_facts(db, student, course.code):
        db.delete(row)
    db.commit()


@router.get("/courses", tags=["courses"])
def search_courses(q: str, limit: int = 20) -> list[Course]:
    return get_catalog().search(q, limit)


@router.get("/courses/{code}", tags=["courses"])
def get_course(code: str) -> Course:
    return _course_or_404(code)
