from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, services
from app.catalog.store import get_catalog
from app.models import now
from app.planner.eligible import list_eligible
from app.routes.auth import DB, CurrentStudent
from app.schemas.courses import Course
from app.schemas.explore import Candidate, HiddenCourse, OfficialInfo, SlotCandidates
from app.schemas.profile import ProfileFact

router = APIRouter(tags=["explore"])

NOT_INTERESTED = "not_interested"


def not_interested_facts(db: Session, student: models.Student, code: str | None = None):
    q = select(models.ProfileFact).where(
        models.ProfileFact.student_id == student.id,
        models.ProfileFact.dimension == NOT_INTERESTED,
        models.ProfileFact.status == "stated",
    )
    if code is not None:
        q = q.where(models.ProfileFact.value == code)
    return list(db.scalars(q.order_by(models.ProfileFact.id)))


@router.get("/slots/{slot_id}/candidates")
def candidates(
    slot_id: str, term: str, db: DB, student: CurrentStudent, limit: int = 3
) -> SlotCandidates:
    """Eligible courses for a requirement slot. Ranking is a placeholder until the
    profile-aware recommender lands (Track C); reasons are empty for now."""
    program = services.program_for(student)
    req = next((r for r in program.all_requirements() if r.id == slot_id), None)
    if req is None:
        raise HTTPException(404, f"no requirement {slot_id}")
    plan = services.plan_schema(db, student, services.get_plan(db, student))
    if term not in plan.terms:
        raise HTTPException(400, f"{term} isn't in your plan")

    catalog = get_catalog()
    eligible = list_eligible(req, term, plan.placements, catalog)
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
    current_idx = plan.terms.index(plan.current_term) if plan.current_term in plan.terms else -1
    assumed = plan.terms.index(term) > current_idx + 1
    top = [
        Candidate(
            course=c.summary(),
            rank=i + 1,
            reasons=[],
            official=OfficialInfo(
                prereqs_met=True,
                prereq_note=c.prereq_text or "No prerequisites listed",
                offering_note=f"Offered in {len(c.terms_offered)} of the recent terms we have",
                assumed=assumed,
            ),
        )
        for i, c in enumerate(eligible[:limit])
    ]
    return SlotCandidates(
        slot_id=req.id,
        slot_label=req.label,
        term=term,
        eligible_count=len(eligible),
        candidates=top,
        ordering="Sorted by how often it’s been offered, most often first",
        hidden=hidden,
    )


def _course_or_404(code: str) -> Course:
    course = get_catalog().get(code)
    if course is None:
        raise HTTPException(404, f"no course {code}")
    return course


@router.put("/courses/{code}/not-interested", tags=["profile"])
def mark_not_interested(code: str, db: DB, student: CurrentStudent) -> ProfileFact:
    """Remember that the student doesn't want this course suggested. Saved as a stated
    profile fact, so it shows on the profile page and can be removed there."""
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
