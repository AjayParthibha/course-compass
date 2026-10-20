from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, model_validator

from app.schemas.base import Schema


class RuleSchema(Schema):
    """Rule files are hand-written: an unknown key is a typo (or a label cut short at a
    comma in an inline YAML map), so it's an error rather than silently dropped."""

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class QualifyingPrereq(RuleSchema):
    """A course qualifies when it lists one of these as a prerequisite or corequisite
    (the CS technical-elective rule). Prerequisites marked "recommended" don't count."""

    exempt_subjects: list[str] = []  # courses in these subjects qualify on their own (CS)
    courses: list[str] = []  # a listed prerequisite or corequisite from here qualifies
    subjects: list[str] = []  # so does any course in these subjects ("any ENGRD course")
    text_any: list[str] = []  # or prerequisite text naming one of these ("probability")
    chain: bool = False  # or a prerequisite that itself has a qualifying one


class CourseFilter(RuleSchema):
    subjects: list[str] = []
    exclude_subjects: list[str] = []
    min_level: int | None = None
    max_level: int | None = None
    attributes_any: list[str] = []
    min_credits: int | None = None
    exclude: list[str] = []
    # e.g. "FWS:" — every first-year writing seminar's roster title starts with it
    title_prefix: str | None = None
    # leave out courses whose title contains any of these (case-insensitive), e.g.
    # "Independent Study" for rules that don't take research or independent study credit
    exclude_titles: list[str] = []
    # named courses that count even though the rest of the filter wouldn't take them,
    # e.g. CS 3700 for the 4000+ CS electives (exclude still wins)
    include: list[str] = []
    # a subject's courses only count from this level up, e.g. {AIRS: 3000} for ROTC
    min_level_for: dict[str, int] = {}
    qualifying_prereq: QualifyingPrereq | None = None


class RequirementGroup(RuleSchema):
    """One category inside a requirement (a liberal studies group, an engineering
    distribution category). A course belongs to it by attribute or by course code."""

    id: str
    label: str
    attributes_any: list[str] = []
    courses: list[str] = []
    min_credits: int | None = None  # at least this many counted credits from this group
    max_courses: int | None = None  # at most this many counted courses from this group


class Requirement(RuleSchema):
    id: str
    label: str
    # total_credits: a credit total over every course matching `filter` (123 for the
    # degree); it shares courses with everything else and needs no count
    kind: Literal["courses", "filter", "all_of", "any_of", "flag_only", "total_credits"]
    courses: list[str] = []
    filter: CourseFilter | None = None
    count: int | None = None
    credits: int | None = None
    children: list[Requirement] = []
    # ids of other requirements this one may share a course with
    double_count: list[str] = []
    source_url: str | None = None
    notes: str | None = None
    # where the starter plan puts open slots for it: spread to balance load, or in the
    # earliest remaining terms (first-year writing seminars)
    seed: Literal["spread", "earliest"] = "spread"
    # every course counted here shares one subject prefix (a cross-listing's counts)
    same_subject: bool = False
    # at most this many counted courses may be cross-listed with a subject, e.g. {CS: 1}
    max_cross_listed: dict[str, int] = {}
    # what an advisor may approve instead of the one-subject rule, as the catalog allows
    # ("courses from different subjects on one topic"); a student who says they have that
    # approval gets the rule without same_subject
    approval: str | None = None
    # courses that may not count here and in another requirement at once even though
    # double_count allows the pair, e.g. COMM 3020 can't fill engineering communications
    # and liberal studies together: {ls: [COMM 3020]}
    double_count_except: dict[str, list[str]] = {}
    groups: list[RequirementGroup] = []
    min_groups: int | None = None  # counted courses must span at least this many groups
    # {2000: 2}: at least two counted courses at the 2000 level or above
    min_at_level: dict[int, int] = {}
    # {3000: 1}: at most one counted course below the 3000 level
    max_below_level: dict[int, int] = {}

    @model_validator(mode="after")
    def check_shape(self):
        if self.kind == "courses" and not self.courses:
            raise ValueError(f"{self.id}: 'courses' requirement needs a course list")
        if self.kind in ("filter", "total_credits") and self.filter is None:
            raise ValueError(f"{self.id}: 'filter' requirement needs a filter")
        if self.kind in ("all_of", "any_of") and not self.children:
            raise ValueError(f"{self.id}: '{self.kind}' needs children")
        return self

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


class RequirementSet(RuleSchema):
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

    def with_approvals(self, approved: list[str]) -> Program:
        """The program as it applies to a student whose advisor approved the rules in
        `approved`: each one that allows an approval drops its one-subject rule."""
        ids = {r.id for r in self.all_requirements() if r.approval and r.id in approved}
        if not ids:
            return self
        program = self.model_copy(deep=True)
        for r in program.all_requirements():
            if r.id in ids:
                r.same_subject = False
        return program
