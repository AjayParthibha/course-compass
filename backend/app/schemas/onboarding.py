from typing import Literal

from app.schemas.base import Schema
from app.schemas.profile import CreditCap, Term

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
    # something to know about the row that needs no answer ("taken in Summer 2025")
    note: str | None = None


class OnboardingOptions(Schema):
    current_term: str
    # entering terms we have rules for, oldest first, through the term after this one
    entering_terms: list[str]
    # program id -> catalog years with rule files, e.g. {"cs-eng": ["2024-25"]}
    rule_years: dict[str, list[str]]


class ParseRequest(Schema):
    text: str
    program: str
    entering_term: str


class ParseResult(Schema):
    courses: list[ParsedCourse]
    catalog_year: str
    # lines that look like they name a course but that nothing could be read from
    unread: list[str] = []


class TranscriptRequest(Schema):
    # the unofficial transcript PDF, base64-encoded; read in memory and never stored
    pdf_base64: str


class TranscriptResult(Schema):
    courses: list[ParsedCourse]
    unread: list[str] = []
    # courses on the transcript that earned no credit ("CS 1110 (Fall 2024): grade W")
    skipped: list[str] = []
    # what the transcript says, to prefill the form
    entering_term: str | None = None
    program: str | None = None


class ConfirmedCourse(Schema):
    term: str | None
    code: str
    credits: int | None = None  # defaults to the roster's credits


class ConfirmRequest(Schema):
    program: str
    entering_term: Term
    graduation_term: Term
    courses: list[ConfirmedCourse]
    # the semester load the student picked; the starter plan stays under it
    max_credits: CreditCap | None = None
