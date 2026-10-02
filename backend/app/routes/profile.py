from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete

from app import models, services
from app.models import now
from app.routes.auth import DB, CurrentStudent
from app.schemas.profile import FactCreate, FactUpdate, Profile, ProfileFact, Student, StudentUpdate

router = APIRouter(tags=["profile"])


@router.get("/profile")
def get_profile(db: DB, student: CurrentStudent) -> Profile:
    facts = [services.fact_schema(f) for f in services.visible_facts(db, student)]
    return Profile(student=services.student_schema(student), facts=facts)


@router.patch("/profile/student")
def update_student(body: StudentUpdate, db: DB, student: CurrentStudent) -> Student:
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(student, key, value)
    db.commit()
    return services.student_schema(student)


@router.post("/profile/facts")
def add_fact(body: FactCreate, db: DB, student: CurrentStudent) -> ProfileFact:
    row = models.ProfileFact(student_id=student.id, **body.model_dump())
    if body.status == "stated":
        row.last_confirmed_at = now()
    db.add(row)
    db.commit()
    return services.fact_schema(row)


@router.patch("/profile/facts/{fact_id}")
def update_fact(fact_id: int, body: FactUpdate, db: DB, student: CurrentStudent) -> ProfileFact:
    row = db.get(models.ProfileFact, fact_id)
    if row is None or row.student_id != student.id:
        raise HTTPException(404, "no such fact")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    if body.status == "stated":
        row.last_confirmed_at = now()
    db.commit()
    return services.fact_schema(row)


@router.delete("/profile/facts/{fact_id}", status_code=204)
def delete_fact(fact_id: int, db: DB, student: CurrentStudent) -> None:
    row = db.get(models.ProfileFact, fact_id)
    if row is None or row.student_id != student.id:
        raise HTTPException(404, "no such fact")
    db.delete(row)
    db.commit()


@router.get("/profile/export")
def export_profile(db: DB, student: CurrentStudent) -> Profile:
    return get_profile(db, student)


@router.delete("/profile", status_code=204)
def clear_profile(db: DB, student: CurrentStudent) -> None:
    db.execute(delete(models.ProfileFact).where(models.ProfileFact.student_id == student.id))
    db.commit()


class StudyEventIn(BaseModel):
    kind: str
    data: dict[str, Any] = {}


@router.post("/study/events", status_code=204, tags=["study"])
def log_event(body: StudyEventIn, db: DB, student: CurrentStudent) -> None:
    db.add(models.StudyEvent(student_id=student.id, kind=body.kind, data=body.data))
    db.commit()
