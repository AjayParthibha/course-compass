from fastapi import APIRouter, HTTPException

from app import models, services
from app.catalog.store import get_catalog
from app.config import get_settings
from app.onboarding import parse_history
from app.planner.initial import seed_slots
from app.planner.ops import new_id, next_term, term_index, terms_between
from app.requirements.loader import PROGRAMS, available_years, get_program, rules_year_for
from app.routes.auth import DB, CurrentStudent
from app.schemas.onboarding import ConfirmRequest, OnboardingOptions, ParseRequest, ParseResult
from app.schemas.plans import Placement, PlanState

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _catalog_year(program: str, entering_term: str) -> str:
    if program not in PROGRAMS:
        raise HTTPException(400, f"unknown program {program}")
    year = rules_year_for(program, entering_term)
    if year is None:
        first = min(available_years(program), default=None)
        since = f" for students who started in Fall {first[:4]} or later" if first else ""
        raise HTTPException(400, f"we only have {PROGRAMS[program][0]} rules{since}")
    return year


@router.get("/options")
def options(student: CurrentStudent) -> OnboardingOptions:
    """The current term, the entering terms we have rules for (through the next term, for
    students about to start), and each program's rule years."""
    current = get_settings().current_term
    years = {p: available_years(p) for p in PROGRAMS}
    firsts = [ys[0] for ys in years.values() if ys]
    entering = []
    if firsts:
        term = f"FA{min(firsts)[2:4]}"
        while term_index(term) <= term_index(next_term(current)):
            entering.append(term)
            term = next_term(term)
    return OnboardingOptions(current_term=current, entering_terms=entering, rule_years=years)


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
    # a student who hasn't started yet has nothing completed; one who has, everything
    # before the current term
    if current in terms:
        now = terms.index(current)
    else:
        now = -1 if term_index(current) < term_index(terms[0]) else len(terms)
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
    placements = seed_slots(
        placements,
        terms,
        current,
        program,
        get_catalog(),
        max_credits=student.max_credits,
        term_caps=student.term_caps,
    )

    plan = student.plans[0] if student.plans else models.Plan(student_id=student.id, version=0)
    db.add(plan)
    db.flush()
    # a new history: undo shouldn't bring back a plan built for another program or start term
    services.commit(db, plan, placements, "import", "onboarding", parent=None)
    db.refresh(student)
    return services.plan_state(db, student)
