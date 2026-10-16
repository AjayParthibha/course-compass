"""Greedy requirement audit (v0).

Assigns placements to requirement leaves one at a time, specific course lists
first and broad filters after. Good enough to drive the UI; Track A swaps this
for the CP-SAT assignment model, which handles double-counting properly.
"""

from collections import Counter

from app.catalog.store import Catalog
from app.schemas.courses import Course
from app.schemas.plans import AuditResult, Placement, RequirementStatus
from app.schemas.requirements import CourseFilter, Program, Requirement


def matches(course: Course, req: Requirement, catalog: Catalog) -> bool:
    if req.kind == "courses":
        return bool(catalog.equivalents(course.code) & set(req.courses))
    if req.kind == "filter" and req.filter:
        return matches_filter(course, req.filter)
    return False


def subjects_of(course: Course) -> set[str]:
    """Its own subject and its cross-listings': CS 2110 is also ENGRD 2110."""
    return {course.subject, *(code.split()[0] for code in course.cross_listed)}


def cross_listed_with(course: Course, subject: str) -> bool:
    return any(code.split()[0] == subject for code in course.cross_listed)


def within_limits(options: list[tuple[Placement, Course]], req: Requirement):
    """Drop courses past the rule's cap on cross-listings, keeping plan order."""
    used: Counter[str] = Counter()
    out = []
    for p, course in options:
        crossed = [s for s in req.max_cross_listed if cross_listed_with(course, s)]
        if any(used[s] >= req.max_cross_listed[s] for s in crossed):
            continue
        used.update(crossed)
        out.append((p, course))
    return out


def best_subject(options: list[tuple[Placement, Course]], req: Requirement):
    """For a same-subject rule, the courses from the subject that covers the most of it;
    ties go to the subject that appears first in the plan."""
    best: list[tuple[Placement, Course]] = []
    for subject in dict.fromkeys(s for _, c in options for s in sorted(subjects_of(c))):
        group = within_limits([(p, c) for p, c in options if subject in subjects_of(c)], req)
        if len(group) > len(best):
            best = group
    return best


def matches_filter(course: Course, f: CourseFilter) -> bool:
    subjects = subjects_of(course)
    if f.subjects and not subjects & set(f.subjects):
        return False
    if course.subject in f.exclude_subjects or course.code in f.exclude:
        return False
    if f.min_level is not None and course.level < f.min_level:
        return False
    if f.max_level is not None and course.level > f.max_level:
        return False
    if f.min_credits is not None and course.credits < f.min_credits:
        return False
    if f.attributes_any and not set(f.attributes_any) & set(course.attributes):
        return False
    if f.title_prefix and not course.title.startswith(f.title_prefix):
        return False
    if f.exclude_titles and any(t.lower() in course.title.lower() for t in f.exclude_titles):
        return False
    return True


def needed(req: Requirement) -> int:
    if req.count is not None:
        return req.count
    return len(req.courses) if req.kind == "courses" else 1


def fill_order(req: Requirement) -> int:
    """Course lists first, then filters that name a subject, attribute or title, then
    catch-all electives, so a broad elective can't take a course a narrower rule needs."""
    if req.kind == "courses":
        return 0
    f = req.filter
    return 1 if f and (f.subjects or f.attributes_any or f.title_prefix) else 2


def audit(placements: list[Placement], program: Program, catalog: Catalog) -> AuditResult:
    leaves = [r for r in program.all_requirements() if r.kind in ("courses", "filter")]
    leaves.sort(key=fill_order)

    used_by: dict[str, set[str]] = {}  # placement id -> requirement ids it counts toward
    filled: dict[str, list[Placement]] = {r.id: [] for r in program.all_requirements()}

    # open slots count toward the requirement they were created for
    for p in placements:
        if p.slot and not p.course and p.slot in filled:
            filled[p.slot].append(p)
            used_by[p.id] = {p.slot}

    for req in leaves:
        target = needed(req)
        options = []
        for p in placements:
            if not p.course or p in filled[req.id]:
                continue
            course = catalog.get(p.course)
            if course is None or not matches(course, req, catalog):
                continue
            prior = used_by.get(p.id, set())
            if prior and not prior <= set(req.double_count):
                continue
            options.append((p, course))
        options = best_subject(options, req) if req.same_subject else within_limits(options, req)
        for p, _ in options:
            if len(filled[req.id]) >= target and _credits(filled[req.id]) >= (req.credits or 0):
                break
            filled[req.id].append(p)
            used_by.setdefault(p.id, set()).add(req.id)

    def status_of(req: Requirement) -> RequirementStatus:
        children = [status_of(c) for c in req.children]
        open_slots = 0
        if req.kind == "flag_only":
            st, n, ids = "flagged", needed(req), []
        elif req.kind in ("all_of", "any_of"):
            ranks = [_rank(c.status) for c in children]
            best = max(ranks) if req.kind == "any_of" else min(ranks)
            st, n, ids = _unrank(best), len(children), []
            open_slots = sum(1 for c in children if c.status != "missing" and c.open_slots)
        else:
            got = filled[req.id]
            n = needed(req)
            enough = len(got) >= n and _credits(got) >= (req.credits or 0)
            if enough and all(p.status == "completed" for p in got[:n]):
                st = "done"
            elif enough:
                st = "planned"
            else:
                st = "missing"
            ids = [p.id for p in got]
            chosen = sum(1 for p in got if p.course)
            open_slots = max(0, min(len(got), n) - min(chosen, n))
        return RequirementStatus(
            id=req.id,
            label=req.label,
            status=st,
            needed=n,
            filled=ids,
            open_slots=open_slots,
            children=children,
        )

    top = [status_of(r) for s in program.sets for r in s.requirements]
    unassigned = [p.id for p in placements if p.course and p.id not in used_by]
    complete = all(r.status in ("done", "planned", "flagged") for r in top)
    return AuditResult(complete=complete, requirements=top, unassigned=unassigned)


def _credits(ps: list[Placement]) -> int:
    return sum(p.credits for p in ps)


_ORDER = ["missing", "flagged", "planned", "done"]


def _rank(status: str) -> int:
    return _ORDER.index(status)


def _unrank(rank: int) -> str:
    return _ORDER[rank]
