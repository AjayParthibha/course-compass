import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.schemas.profile import Student
from app.services import student_schema

DB = Annotated[Session, Depends(models.get_db)]


def current_student(
    db: DB, authorization: Annotated[str | None, Header()] = None
) -> models.Student:
    token = (authorization or "").removeprefix("Bearer ").strip()
    student = (
        db.scalar(select(models.Student).where(models.Student.token == token)) if token else None
    )
    if student is None:
        raise HTTPException(401, "not signed in")
    return student


CurrentStudent = Annotated[models.Student, Depends(current_student)]


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    code: str


class LoginResponse(BaseModel):
    token: str
    student: Student


@router.post("/login")
def login(body: LoginRequest, db: DB) -> LoginResponse:
    """Sign in with a participant code. Unknown codes create a new participant."""
    code = body.code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{4,32}", code):
        raise HTTPException(400, "codes are 4-32 letters, digits or dashes")
    student = db.scalar(select(models.Student).where(models.Student.code == code))
    if student is None:
        student = models.Student(code=code, token=secrets.token_urlsafe(32))
        db.add(student)
        db.commit()
    return LoginResponse(token=student.token, student=student_schema(student))


@router.get("/me")
def me(student: CurrentStudent) -> Student:
    return student_schema(student)
