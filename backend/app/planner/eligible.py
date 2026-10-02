from app.catalog.store import Catalog
from app.planner.audit import matches
from app.planner.validate import satisfied
from app.schemas.courses import Course
from app.schemas.plans import Placement
from app.schemas.requirements import Requirement


def list_eligible(
    req: Requirement,
    term: str,
    terms: list[str],
    placements: list[Placement],
    catalog: Catalog,
) -> list[Course]:
    """Courses that would fill `req` in `term`: match the rule, prereqs done by then,
    not already in the plan, and offered in that season at some point."""
    idx = terms.index(term)
    before: set[str] = set()
    in_plan: set[str] = set()
    for p in placements:
        if not p.course:
            continue
        in_plan |= catalog.equivalents(p.course)
        if p.status == "completed" or terms.index(p.term) < idx:
            before |= catalog.equivalents(p.course)

    out = []
    seen: set[str] = set()
    for course in sorted(catalog.courses.values(), key=lambda c: c.code):
        if course.code in in_plan or course.code in seen or not matches(course, req, catalog):
            continue
        if catalog.offered_in(course.code, term) is False:
            continue
        if not satisfied(course.prereqs, before, set()):
            continue
        out.append(course)
        seen |= catalog.equivalents(course.code)  # one entry per cross-listed course
    # prefer courses offered often (more reliable to plan around)
    out.sort(key=lambda c: (-len(c.terms_offered), c.code))
    return out
