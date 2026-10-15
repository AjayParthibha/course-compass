from fastapi import APIRouter, HTTPException

from app import services
from app.planner.ops import OpError
from app.routes.auth import DB, CurrentStudent
from app.schemas.plans import OpsRequest, PlanState, Proposal

router = APIRouter(tags=["plans"])


@router.get("/plan")
def get_plan(db: DB, student: CurrentStudent) -> PlanState:
    try:
        return services.plan_state(db, student)
    except services.NotReady:
        raise HTTPException(409, "finish onboarding first") from None


@router.post("/plan/ops")
def apply_ops(body: OpsRequest, db: DB, student: CurrentStudent) -> PlanState:
    """Apply manual edits. With dry_run the plan isn't saved, just checked."""
    try:
        if body.dry_run:
            return services.preview_ops(db, student, body.ops)
        return services.apply_plan_ops(db, student, body.ops)
    except OpError as e:
        raise HTTPException(400, str(e)) from None
    except services.NotReady:
        raise HTTPException(409, "finish onboarding first") from None


@router.post("/plan/undo")
def undo(db: DB, student: CurrentStudent) -> PlanState:
    return services.undo(db, student)


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: int, db: DB, student: CurrentStudent) -> Proposal:
    row = services.get_proposal(db, student, proposal_id)
    if row is None:
        raise HTTPException(404, "no such proposal")
    return services.proposal_schema(row, services.get_plan(db, student).version)


@router.post("/proposals/{proposal_id}/preview")
def preview_proposal(proposal_id: int, db: DB, student: CurrentStudent) -> PlanState:
    """The plan as it would look with this proposal applied."""
    row = services.get_proposal(db, student, proposal_id)
    if row is None:
        raise HTTPException(404, "no such proposal")
    ops = services.parse_ops.validate_python(row.ops)
    try:
        return services.preview_ops(db, student, ops, "advisor")
    except OpError:
        # only happens once the plan has moved on and the ops no longer fit it
        raise HTTPException(409, services.OUTDATED) from None


@router.post("/proposals/{proposal_id}/apply")
def apply_proposal(proposal_id: int, db: DB, student: CurrentStudent) -> PlanState:
    row = services.get_proposal(db, student, proposal_id)
    if row is None:
        raise HTTPException(404, "no such proposal")
    try:
        return services.apply_proposal(db, student, row)
    except services.Stale as e:
        raise HTTPException(409, str(e)) from None


@router.post("/proposals/{proposal_id}/discard")
def discard_proposal(proposal_id: int, db: DB, student: CurrentStudent) -> Proposal:
    row = services.get_proposal(db, student, proposal_id)
    if row is None:
        raise HTTPException(404, "no such proposal")
    if row.status == "pending":
        row.status = "discarded"
        db.commit()
    return services.proposal_schema(row, services.get_plan(db, student).version)
