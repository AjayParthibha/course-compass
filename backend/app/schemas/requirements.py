from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from app.schemas.base import Schema


class CourseFilter(Schema):
    subjects: list[str] = []
    exclude_subjects: list[str] = []
    min_level: int | None = None
    max_level: int | None = None
    attributes_any: list[str] = []
    min_credits: int | None = None
    exclude: list[str] = []


class Requirement(Schema):
    id: str
    label: str
    kind: Literal["courses", "filter", "all_of", "any_of", "flag_only"]
    courses: list[str] = []
    filter: CourseFilter | None = None
    count: int | None = None
    credits: int | None = None
    children: list[Requirement] = []
    # ids of other requirements this one may share a course with
    double_count: list[str] = []
    source_url: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def check_shape(self):
        if self.kind == "courses" and not self.courses:
            raise ValueError(f"{self.id}: 'courses' requirement needs a course list")
        if self.kind == "filter" and self.filter is None:
            raise ValueError(f"{self.id}: 'filter' requirement needs a filter")
        if self.kind in ("all_of", "any_of") and not self.children:
            raise ValueError(f"{self.id}: '{self.kind}' needs children")
        return self

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


class RequirementSet(Schema):
    id: str
    label: str
    catalog_year: str
    source_url: str
    verified: bool = False
    requirements: list[Requirement]


class Program(Schema):
    """A degree pathway: one college rule set plus the CS major."""

    id: str
    label: str
    college: str
    catalog_year: str
    sets: list[RequirementSet]

    def all_requirements(self):
        for s in self.sets:
            for r in s.requirements:
                yield from r.walk()
