from dataclasses import dataclass, field

from app.catalog.store import Catalog, season
from app.planner.audit import matches, subjects_of
from app.planner.ops import term_index
from app.planner.validate import missing_courses
from app.schemas.courses import Course
from app.schemas.plans import Placement
from app.schemas.requirements import Requirement

SEASONS = {"FA": "fall", "SP": "spring", "SU": "summer", "WI": "winter"}


@dataclass
class PlanContext:
    """What the plan holds as of `term`: prerequisites done by then and courses anywhere in it."""

    before: set[str]
    in_plan: set[str]


def plan_context(term: str, placements: list[Placement], catalog: Catalog) -> PlanContext:
    # by calendar position, so a placement outside the plan's terms can't break this
    idx = term_index(term)
    before: set[str] = set()
    in_plan: set[str] = set()
    for p in placements:
        if not p.course:
            continue
        in_plan |= catalog.equivalents(p.course)
        if p.status == "completed" or term_index(p.term) < idx:
            before |= catalog.prereq_credit(p.course)
    return PlanContext(before, in_plan)


def why_not(course: Course, term: str, ctx: PlanContext, catalog: Catalog) -> str | None:
    """Why a course that fits the rule can't go in `term`, or None if it can."""
    if catalog.offered_in(course.code, term) is False:
        return f"Not offered in {SEASONS.get(season(term), season(term))}"
    missing = missing_courses(course.prereqs, ctx.before, set())
    if missing:
        return f"Needs {' and '.join(missing[:2])} first"
    return None


def offering_order(c: Course):
    """Undergraduate courses before x99 project numbers and graduate ones; within each,
    courses offered often first (more reliable to plan around)."""
    return (
        c.level >= 6000,
        c.number.endswith("99"),
        c.level >= 5000,
        -len(c.terms_offered),
        c.code,
    )


def by_offering(courses: list[Course]) -> list[Course]:
    return sorted(courses, key=offering_order)


def listed_under(course: Course, subject: str, catalog: Catalog) -> Course:
    """The course's own listing under `subject` (ORIE 5252 rather than CEE 5252)."""
    for code in course.cross_listed:
        if code.split()[0] == subject and (other := catalog.get(code)):
            return other
    return course


def list_eligible(
    req: Requirement,
    term: str,
    placements: list[Placement],
    catalog: Catalog,
) -> list[Course]:
    """Courses that would fill `req` in `term`: match the rule, prereqs done by then,
    not already in the plan, and offered in that season at some point."""
    ctx = plan_context(term, placements, catalog)
    out = []
    seen: set[str] = set()
    for course in sorted(catalog.courses.values(), key=lambda c: c.code):
        if course.code in ctx.in_plan or course.code in seen or not matches(course, req, catalog):
            continue
        if why_not(course, term, ctx, catalog):
            continue
        out.append(course)
        seen |= catalog.equivalents(course.code)  # one entry per cross-listed course
    return by_offering(out)


@dataclass
class AreaCourses:
    subject: str
    ready: list[Course] = field(default_factory=list)
    blocked: list[tuple[Course, str]] = field(default_factory=list)


def courses_by_subject(
    req: Requirement, term: str, placements: list[Placement], catalog: Catalog
) -> dict[str, AreaCourses]:
    """For a same-subject rule: every course that fits it, grouped by subject (a course
    joins each subject it's listed under) and split into ready for `term` or not, with why."""
    ctx = plan_context(term, placements, catalog)
    excluded = set(req.filter.exclude_subjects) if req.filter else set()
    areas: dict[str, AreaCourses] = {}
    seen: dict[str, set[str]] = {}
    for course in sorted(catalog.courses.values(), key=lambda c: c.code):
        if course.code in ctx.in_plan or not matches(course, req, catalog):
            continue
        reason = why_not(course, term, ctx, catalog)
        for subject in sorted(subjects_of(course) - excluded):
            done = seen.setdefault(subject, set())
            shown = listed_under(course, subject, catalog)
            # cross-listing data isn't always symmetric, so check both codes
            if course.code in done or shown.code in done:
                continue
            done |= catalog.equivalents(course.code) | catalog.equivalents(shown.code)
            area = areas.setdefault(subject, AreaCourses(subject))
            if reason:
                area.blocked.append((shown, reason))
            else:
                area.ready.append(shown)
    for area in areas.values():
        area.ready = by_offering(area.ready)
        area.blocked.sort(key=lambda pair: offering_order(pair[0]))
    return areas
