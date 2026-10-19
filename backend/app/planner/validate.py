"""Naive plan checks: prerequisite order, credit caps, offerings, duplicates.

This is the v0 validator from the foundation build. Track A replaces the
audit side with the CP-SAT model; these checks stay as the fast path for drags.
"""

from collections import defaultdict

from app.catalog.store import Catalog
from app.planner.ops import term_index, term_label
from app.schemas.courses import AllOf, AnyOf, CourseReq, Flag, PrereqExpr
from app.schemas.plans import Placement, Violation

MIN_CREDITS = 12


def satisfied(expr: PrereqExpr | None, before: set[str], same_term: set[str]) -> bool:
    match expr:
        case None | Flag():
            return True
        case CourseReq():
            return expr.code in before or (expr.concurrent and expr.code in same_term)
        case AllOf():
            return all(satisfied(e, before, same_term) for e in expr.items)
        case AnyOf():
            return any(satisfied(e, before, same_term) for e in expr.items)
    return True


def missing_courses(expr: PrereqExpr | None, before: set[str], same_term: set[str]) -> list[str]:
    """Course codes that would satisfy the unmet parts (first option of each OR)."""
    if satisfied(expr, before, same_term):
        return []
    match expr:
        case CourseReq():
            return [expr.code]
        case AllOf():
            return [c for e in expr.items for c in missing_courses(e, before, same_term)]
        case AnyOf():
            return missing_courses(expr.items[0], before, same_term)
    return []


def prereq_codes(expr: PrereqExpr | None) -> set[str]:
    match expr:
        case CourseReq():
            return {expr.code}
        case AllOf() | AnyOf():
            return set().union(*(prereq_codes(e) for e in expr.items))
    return set()


def credit_clashes(
    placements: list[Placement], catalog: Catalog
) -> list[tuple[Placement, Placement]]:
    """Pairs of different courses in the plan that earn credit once between them, because
    the roster lists them as forbidden overlaps (MATH 2210 and MATH 2940). The earlier
    one comes first. The same course twice is a duplicate, reported on its own."""
    courses = sorted((p for p in placements if p.course), key=lambda p: term_index(p.term))
    out = []
    for i, p in enumerate(courses):
        overlaps = catalog.overlaps(p.course)
        out += [(p, q) for q in courses[i + 1 :] if q.course in overlaps]
    return out


def prereq_edges(placements: list[Placement], catalog: Catalog) -> list[tuple[str, str]]:
    """(prereq placement id, dependent placement id) pairs within the plan."""
    edges = []
    courses = [p for p in placements if p.course]
    for p in courses:
        course = catalog.get(p.course)
        needs = prereq_codes(course.prereqs) if course else set()
        for q in courses:
            if q is not p and catalog.prereq_credit(q.course) & needs:
                edges.append((q.id, p.id))
    return edges


def _expand(codes: set[str], catalog: Catalog) -> set[str]:
    """Everything these courses count as when checking prerequisites."""
    out = set()
    for code in codes:
        out |= catalog.prereq_credit(code)
    return out


def validate(
    placements: list[Placement],
    terms: list[str],
    catalog: Catalog,
    max_credits: int = 18,
    term_caps: dict[str, int] | None = None,
) -> list[Violation]:
    """`term_caps` overrides `max_credits` for individual terms, e.g. {"SP27": 15}."""
    violations: list[Violation] = []
    order = {t: i for i, t in enumerate(terms)}
    courses = [p for p in placements if p.course]

    seen: dict[str, Placement] = {}
    for p in courses:
        course = catalog.get(p.course)
        if course is None:
            violations.append(
                Violation(
                    kind="unknown_course",
                    message=f"{p.course} isn't in the roster",
                    placement_ids=[p.id],
                )
            )
            continue
        key = min(catalog.equivalents(p.course))
        if key in seen:
            violations.append(
                Violation(
                    kind="duplicate",
                    message=f"{p.course} is in the plan twice",
                    placement_ids=[seen[key].id, p.id],
                    blocking=True,
                )
            )
        seen[key] = p

    for p, q in credit_clashes(placements, catalog):
        violations.append(
            Violation(
                kind="no_credit",
                message=f"You won't get credit for both {p.course} and {q.course}; "
                "the roster lists them as overlapping",
                placement_ids=[p.id, q.id],
            )
        )

    by_term: dict[str, list[Placement]] = defaultdict(list)
    for p in placements:
        by_term[p.term].append(p)

    def taken_before(term: str) -> set[str]:
        idx = order.get(term, 0)
        codes = {p.course for p in courses if p.status == "completed" or order.get(p.term, 0) < idx}
        return _expand(codes, catalog)

    for p in courses:
        if p.status == "completed":
            continue
        course = catalog.get(p.course)
        if course is None:
            continue
        before = taken_before(p.term)
        same = _expand({q.course for q in by_term[p.term] if q.course}, catalog)
        if not satisfied(course.prereqs, before, same):
            need = ", ".join(missing_courses(course.prereqs, before, same)) or "its prerequisites"
            violations.append(
                Violation(
                    kind="prereq",
                    message=f"{p.course} needs {need} first",
                    placement_ids=[p.id],
                    blocking=True,
                )
            )
        offered = catalog.offered_in(p.course, p.term)
        if offered is False:
            seasons = "/".join(course.typical_seasons)
            violations.append(
                Violation(
                    kind="offering",
                    message=f"{p.course} has only been offered in {seasons} recently",
                    placement_ids=[p.id],
                )
            )

    for term, items in by_term.items():
        if all(p.status == "completed" for p in items):
            continue
        total = sum(p.credits for p in items)
        # a cap of 0 is a real cap (a term off), so check for None rather than falsy
        cap = (term_caps or {}).get(term)
        if total > (cap if cap is not None else max_credits):
            message = (
                f"{term_label(term)} has {total} credits, over your {cap}-credit cap for that term"
                if cap is not None
                else f"{term_label(term)} has {total} credits, over your limit of {max_credits}"
            )
            violations.append(
                Violation(
                    kind="credits_high",
                    message=message,
                    placement_ids=[p.id for p in items],
                    blocking=True,
                )
            )
        elif total < MIN_CREDITS:
            violations.append(
                Violation(
                    kind="credits_low",
                    message=(
                        f"{term_label(term)} has {total} credits, "
                        f"under the {MIN_CREDITS}-credit minimum"
                    ),
                    placement_ids=[p.id for p in items],
                )
            )
    return violations
