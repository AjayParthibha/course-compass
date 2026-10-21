"""Requirement matching and the requirement audit.

`audit` is exact: it runs the CP-SAT assignment in app.planner.solver.audit.
`greedy_audit` assigns placements to requirement leaves one at a time, specific
course lists first and broad filters after; it's kept as the fallback when a solve
runs out of time, and doesn't check category rules (groups, levels).
"""

import re
from collections import Counter

from app.catalog.store import Catalog
from app.planner.ops import term_index
from app.planner.validate import credit_clashes
from app.schemas.courses import AllOf, AnyOf, Course, CourseReq
from app.schemas.plans import AuditResult, Placement, RequirementStatus
from app.schemas.requirements import CourseFilter, Program, QualifyingPrereq, Requirement


def matches(course: Course, req: Requirement, catalog: Catalog) -> bool:
    if req.kind == "courses":
        return bool(catalog.equivalents(course.code) & set(req.courses))
    if req.kind in ("filter", "total_credits") and req.filter:
        return matches_filter(course, req.filter, catalog)
    return False


def groups_of(course: Course, req: Requirement, catalog: Catalog) -> set[str]:
    """The requirement's groups this course belongs to (by attribute or course code)."""
    codes = catalog.equivalents(course.code)
    return {
        g.id
        for g in req.groups
        if set(g.attributes_any) & set(course.attributes) or codes & set(g.courses)
    }


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


def matches_filter(course: Course, f: CourseFilter, catalog: Catalog | None = None) -> bool:
    # a course named in `exclude` stays out under every code it's listed as: LING 4474 is
    # also COGST 4740, and the checklist bars the course, not one of its numbers
    codes = {course.code, *course.cross_listed}
    if course.subject in f.exclude_subjects or codes & set(f.exclude):
        return False
    if course.level < f.min_level_for.get(course.subject, 0):
        return False
    if course.code in f.include:
        return True
    subjects = subjects_of(course)
    if f.subjects and not subjects & set(f.subjects):
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
    if f.qualifying_prereq and not qualifies(course, f.qualifying_prereq, catalog):
        return False
    return True


CODE = re.compile(r"\b([A-Z]{2,7}) ?(\d{4})\b")


def requisite_text(course: Course) -> str:
    """Prerequisite and corequisite text, cut where "recommended" begins: a recommended
    course doesn't count as a requirement."""
    text = f"{course.prereq_text} {course.coreq_text}"
    cut = text.lower().find("recommended")
    return text if cut < 0 else text[:cut]


def requisite_codes(course: Course) -> set[str]:
    codes = {f"{a} {b}" for a, b in CODE.findall(requisite_text(course))}
    return codes | prereq_codes(course.prereqs)


def prereq_codes(expr) -> set[str]:
    match expr:
        case CourseReq():
            return {expr.code}
        case AllOf() | AnyOf():
            return set().union(*(prereq_codes(e) for e in expr.items))
    return set()


_qualifies: dict[tuple[str, int], bool] = {}


def qualifies(course: Course, q: QualifyingPrereq, catalog: Catalog | None) -> bool:
    """The CS technical-elective test: a CS course qualifies on its own; anything else
    needs a qualifying prerequisite or corequisite listed (by course, by subject, by
    wording such as "probability"), or one that itself has a qualifying one."""
    key = (course.code, id(q))
    if key not in _qualifies:
        _qualifies[key] = _qualifies_now(course, q, catalog)
    return _qualifies[key]


def _qualifies_now(course: Course, q: QualifyingPrereq, catalog: Catalog | None) -> bool:
    if subjects_of(course) & set(q.exempt_subjects):
        return True

    def direct(c: Course) -> bool:
        codes = requisite_codes(c)
        text = requisite_text(c).lower()
        return (
            bool(codes & set(q.courses))
            or any(code.split()[0] in q.subjects for code in codes)
            or any(phrase.lower() in text for phrase in q.text_any)
        )

    if direct(course):
        return True
    if q.chain and catalog is not None:
        return any((p := catalog.get(code)) and direct(p) for code in requisite_codes(course))
    return False


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
    from app.planner.solver.audit import exact_audit  # the solver builds on this module

    return exact_audit(placements, program, catalog)


def greedy_audit(placements: list[Placement], program: Program, catalog: Catalog) -> AuditResult:
    leaves = [r for r in program.all_requirements() if r.kind in ("courses", "filter")]
    leaves.sort(key=fill_order)

    used_by: dict[str, set[str]] = {}  # placement id -> requirement ids it counts toward
    filled: dict[str, list[Placement]] = {r.id: [] for r in program.all_requirements()}
    # a later copy of a course, or the later of two overlapping courses, earns no credit
    no_credit = {q.id for _, q in credit_clashes(placements, catalog)}
    seen: dict[str, str] = {}
    for p in sorted((p for p in placements if p.course), key=lambda p: term_index(p.term)):
        key = min(catalog.equivalents(p.course))
        if key in seen:
            no_credit.add(p.id)
        seen.setdefault(key, p.id)

    # open slots count toward the requirement they were created for
    for p in placements:
        if p.slot and not p.course and p.slot in filled:
            filled[p.slot].append(p)
            used_by[p.id] = {p.slot}

    for req in leaves:
        target = needed(req)
        options = []
        for p in placements:
            if not p.course or p in filled[req.id] or p.id in no_credit:
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
        credits = credits_needed = None
        if req.kind == "flag_only":
            st, n, ids = "flagged", needed(req), []
        elif req.kind == "total_credits":
            here = [
                p
                for p in placements
                if p.id not in no_credit
                and (
                    not p.course or (c := catalog.get(p.course)) is None or matches(c, req, catalog)
                )
            ]
            credits, credits_needed = _credits(here), req.credits or 0
            done = _credits([p for p in here if p.status == "completed"])
            st = (
                "done"
                if done >= credits_needed
                else "planned"
                if credits >= credits_needed
                else "missing"
            )
            n, ids = 1, []
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
            credits=credits,
            credits_needed=credits_needed,
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
