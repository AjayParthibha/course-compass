from fastapi import APIRouter, HTTPException

from app import models, services
from app.catalog.store import get_catalog
from app.config import get_settings
from app.onboarding import parse_history
from app.planner.initial import seed_slots
from app.planner.ops import new_id, terms_between
from app.requirements.loader import PROGRAMS, available_years, catalog_year_for, get_program
from app.routes.auth import DB, CurrentStudent
from app.schemas.onboarding import ConfirmRequest, ParseRequest, ParseResult
from app.schemas.plans import Placement, PlanState

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _catalog_year(program: str, entering_term: str) -> str:
    if program not in PROGRAMS:
        raise HTTPException(400, f"unknown program {program}")
    year = catalog_year_for(entering_term)
    if year not in available_years(program):
        raise HTTPException(400, f"we don't have {year} rules for {program} yet")
    return year


@router.post("/parse")
def parse(body: ParseRequest, student: CurrentStudent) -> ParseResult:
    year = _catalog_year(body.program, body.entering_term)
    return ParseResult(courses=parse_history(body.text, get_catalog()), catalog_year=year)


@router.post("/confirm")
def confirm(body: ConfirmRequest, db: DB, student: CurrentStudent) -> PlanState:
    """Save the confirmed history and create the student's first plan."""
    current = get_settings().current_term
    try:
        terms = terms_between(body.entering_term, body.graduation_term)
    except ValueError:
        raise HTTPException(
            400, f"{body.entering_term} to {body.graduation_term} isn't a valid range of terms"
        ) from None
    student.program = body.program
    student.entering_term = body.entering_term
    student.graduation_term = body.graduation_term
    student.catalog_year = _catalog_year(body.program, body.entering_term)
    # caps only make sense for terms still in the (possibly new) plan
    student.term_caps = {t: c for t, c in (student.term_caps or {}).items() if t in terms}
    now = terms.index(current) if current in terms else len(terms)
    placements = []
    for c in body.courses:
        term = c.term or body.entering_term
        if term not in terms:
            raise HTTPException(400, f"{c.code}: {term} is outside {terms[0]}–{terms[-1]}")
        course = get_catalog().get(c.code)
        if course is None:
            raise HTTPException(400, f"unknown course {c.code}")
        idx = terms.index(term)
        status = "completed" if idx < now else "in_progress" if idx == now else "planned"
        placements.append(
            Placement(
                id=new_id(),
                term=term,
                course=course.code,
                credits=c.credits or course.credits,
                status=status,
                origin="import",
            )
        )

    program = get_program(student.program, student.catalog_year)
    placements = seed_slots(placements, terms, current, program, get_catalog())

    plan = student.plans[0] if student.plans else models.Plan(student_id=student.id, version=0)
    db.add(plan)
    db.flush()
    # a new history: undo shouldn't bring back a plan built for another program or start term
    services.commit(db, plan, placements, "import", "onboarding", parent=None)
    db.refresh(student)
    return services.plan_state(db, student)
