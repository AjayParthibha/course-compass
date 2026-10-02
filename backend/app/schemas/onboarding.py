from typing import Literal

from app.schemas.base import Schema

IssueKind = Literal["ambiguous_code", "credit_mismatch", "ap_credit", "unknown_course", "duplicate"]


class IssueOption(Schema):
    label: str
    value: str


class Issue(Schema):
    kind: IssueKind
    message: str
    options: list[IssueOption]


class ParsedCourse(Schema):
    id: str
    raw: str
    term: str | None
    code: str | None
    title: str | None = None
    credits: int | None = None
    issue: Issue | None = None


class ParseRequest(Schema):
    text: str
    program: str
    entering_term: str


class ParseResult(Schema):
    courses: list[ParsedCourse]
    catalog_year: str


class ConfirmedCourse(Schema):
    term: str | None
    code: str
    credits: int | None = None  # defaults to the roster's credits


class ConfirmRequest(Schema):
    program: str
    entering_term: str
    graduation_term: str
    courses: list[ConfirmedCourse]
