from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from app.schemas.base import Schema

Season = Literal["FA", "SP", "SU", "WI"]


class CourseReq(Schema):
    kind: Literal["course"] = "course"
    code: str
    concurrent: bool = False


class AllOf(Schema):
    kind: Literal["all"] = "all"
    items: list[PrereqExpr]


class AnyOf(Schema):
    kind: Literal["any"] = "any"
    items: list[PrereqExpr]


class Flag(Schema):
    """Something we can't check automatically, like instructor permission."""

    kind: Literal["flag"] = "flag"
    text: str


PrereqExpr = Annotated[CourseReq | AllOf | AnyOf | Flag, Field(discriminator="kind")]
AllOf.model_rebuild()
AnyOf.model_rebuild()


class CourseSummary(Schema):
    code: str
    title: str
    credits: int


class Course(Schema):
    code: str
    subject: str
    number: str
    title: str
    description: str = ""
    credits_min: float | None = None
    credits_max: float | None = None
    attributes: list[str] = []
    cross_listed: list[str] = []
    terms_offered: list[str] = []
    typical_seasons: list[Season] = []
    instructors: list[str] = []
    prereq_text: str = ""
    coreq_text: str = ""
    # the roster's "no credit for both" list, as written; see app/catalog/overlaps.py
    forbidden_overlaps: str = ""
    prereqs: PrereqExpr | None = None
    prereqs_reviewed: bool = False

    @property
    def credits(self) -> int:
        return int((self.credits_max or self.credits_min or 0) + 0.5)

    @property
    def level(self) -> int:
        """The course number as a number (CS 1110 -> 1110), so level rules compare the
        way the catalog states them: "courses under the 1100-level", "3000+"."""
        digits = "".join(ch for ch in self.number if ch.isdigit())
        return int(digits[:4].ljust(4, "0")) if digits else 0

    def summary(self) -> CourseSummary:
        return CourseSummary(code=self.code, title=self.title, credits=self.credits)
