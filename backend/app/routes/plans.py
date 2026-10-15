from fastapi import APIRouter, HTTPException

from app import services
from app.planner.ops import OpError
from app.routes.auth import DB, CurrentStudent
from app.schemas.plans import OpsRequest, PlanState, Proposal
from app.schemas.profile import PlanSettingsUpdate, Student

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


@router.patch("/plan/settings")
def update_settings(body: PlanSettingsUpdate, db: DB, student: CurrentStudent) -> Student:
    """Change graduation term and credit caps. Applies to every plan of the student.

    Moving graduation earlier fails with 409 while later terms still hold courses or slots.
    """
    try:
        services.update_plan_settings(db, student, **body.model_dump(exclude_none=True))
    except services.SettingsConflict as e:
        raise HTTPException(409, str(e)) from None
    except services.NotReady:
        raise HTTPException(409, "finish onboarding first") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return services.student_schema(student)


@router.post("/plan/undo")
def undo(db: DB, student: CurrentStudent) -> PlanState:
    """Step back one edit. Repeating it keeps going back through the plan's history.

    Fails with 409 when the earlier plan used terms that are no longer in the plan."""
    try:
        return services.undo(db, student)
    except services.CannotUndo as e:
        raise HTTPException(409, str(e)) from None
    except services.NotReady:
        raise HTTPException(409, "finish onboarding first") from None


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
    if services.proposal_status(row, services.get_plan(db, student).version) == "outdated":
        raise HTTPException(409, services.OUTDATED)
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
