"""Turn the assumptions in a conflict into sentences the advisor can relay."""

from app.catalog.store import Catalog
from app.planner.ops import term_index, term_label
from app.planner.validate import missing_courses
from app.schemas.courses import AllOf, AnyOf, CourseReq
from app.schemas.plans import Placement
from app.schemas.requirements import Program


def describe(
    key: tuple,
    placements: dict[str, Placement],
    program: Program,
    requested_caps: dict[str, int],
) -> str:
    kind, *rest = key

    def name(pid: str) -> str:
        p = placements.get(pid)
        return (p.course or p.slot_label or pid) if p else pid

    match kind:
        case "cap":
            term, cap = rest
            whose = "your request" if term in requested_caps else "your credit limit"
            return f"At most {cap} credits in {term_label(term)} ({whose})"
        case "keep":
            (pid,) = rest
            return f"Keep {name(pid)} in {term_label(placements[pid].term)}"
        case "move":
            pid, term = rest
            return f"Put {name(pid)} in {term_label(term)}"
        case "remove":
            (pid,) = rest
            return f"Drop {name(pid)}"
        case "stays":
            (pid,) = rest
            return f"Keep {name(pid)} in your plan (dropping courses wasn't part of the request)"
        case "add":
            code, term = rest
            return f"Add {code}" + (f" in {term_label(term)}" if term else "")
        case "avoid":
            (code,) = rest
            return f"Don’t take {code}"
        case "graduate":
            (term,) = rest
            return f"Graduate by {term_label(term)}"
        case "floor":
            term, floor = rest
            if floor >= 12:
                return f"Keep {term_label(term)} at 12 credits or more (the full-time minimum)"
            return f"Keep {term_label(term)} at {floor} credits or more (your limit)"
        case "lighter":
            term, load = rest
            return f"Make {term_label(term)} lighter than its {load} credits"
        case "met":
            (rid,) = rest
            label = next((r.label for r in program.all_requirements() if r.id == rid), rid)
            return f"Keep {label} on track"
    return str(key)


def explain_conflict(
    keys: list[tuple],
    placements: dict[str, Placement],
    program: Program,
    requested_caps: dict[str, int],
    catalog: Catalog | None = None,
) -> list[str]:
    """One sentence per clashing request or setting; the requirements that need the room
    are folded into one. A course that has to stay gets its prerequisite when that's
    what ties it to the rest ("it needs CS 3410 or CS 3420")."""
    reasons = []
    staying: list[str] = []
    dropped = {placements[k[1]].course for k in keys if k[0] == "remove" and k[1] in placements}
    for k in keys:
        if k[0] == "met":
            continue
        if k[0] in ("move", "add") and catalog:
            code = placements[k[1]].course if k[0] == "move" and k[1] in placements else k[1]
            term = k[2]
            course = catalog.get(code or "")
            if (
                course
                and term
                and course.typical_seasons
                and term[:2] not in course.typical_seasons
            ):
                seasons = " and ".join(
                    {"FA": "fall", "SP": "spring"}.get(x, x) for x in course.typical_seasons
                )
                wish = describe(k, placements, program, requested_caps)
                reasons.append(f"{wish}, but it has only run in {seasons}")
                continue
            missing = _missing_before(course, term, placements, catalog) if course and term else []
            if missing:
                wish = describe(k, placements, program, requested_caps)
                reasons.append(f"{wish}, but it needs {' and '.join(missing)} first")
                continue
        if k[0] == "stays":
            course = catalog.get(placements[k[1]].course or "") if catalog else None
            if course and dropped & _prereq_codes(course.prereqs):
                needs = course.prereq_text.rstrip(".") or " and ".join(
                    sorted(_prereq_codes(course.prereqs))
                )
                reasons.append(f"Keep {course.code} in your plan; it needs {needs}")
            else:
                staying.append(placements[k[1]].course or k[1])
            continue
        reasons.append(describe(k, placements, program, requested_caps))
    if staying:
        reasons.append(
            f"Keep {_listed(staying)} in your plan (dropping courses wasn't part of the request)"
        )
    labels = {r.id: r.label for r in program.all_requirements()}
    met = [labels.get(k[1], k[1]) for k in keys if k[0] == "met"]
    if met:
        reasons.append(f"Keep {_listed(met)} on track")
    return reasons


def _prereq_codes(expr) -> set[str]:
    match expr:
        case CourseReq():
            return {expr.code}
        case AllOf() | AnyOf():
            return set().union(*(_prereq_codes(e) for e in expr.items))
    return set()


def _missing_before(course, term: str, placements: dict[str, Placement], catalog: Catalog):
    """Prerequisites of `course` that nothing in the plan covers before `term`."""
    done: set[str] = set()
    for p in placements.values():
        if p.course and (p.status == "completed" or term_index(p.term) < term_index(term)):
            done |= catalog.prereq_credit(p.course)
    return missing_courses(course.prereqs, done, set())


def _listed(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"
