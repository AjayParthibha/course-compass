from fastapi import APIRouter, HTTPException

from app import services
from app.catalog.store import get_catalog
from app.planner.eligible import list_eligible
from app.routes.auth import DB, CurrentStudent
from app.schemas.courses import Course
from app.schemas.explore import Candidate, OfficialInfo, SlotCandidates

router = APIRouter(tags=["explore"])


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
    eligible = list_eligible(req, term, plan.terms, plan.placements, catalog)
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
    )


@router.get("/courses", tags=["courses"])
def search_courses(q: str, limit: int = 20) -> list[Course]:
    return get_catalog().search(q, limit)


@router.get("/courses/{code}", tags=["courses"])
def get_course(code: str) -> Course:
    course = get_catalog().get(code)
    if course is None:
        raise HTTPException(404, f"no course {code}")
    return course
