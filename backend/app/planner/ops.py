import re
import uuid

from app.catalog.store import Catalog
from app.schemas.plans import AddOp, LockOp, MoveOp, Placement, PlanOp, RemoveOp, ReplaceOp


class OpError(ValueError):
    pass


def next_term(term: str) -> str:
    season, year = term[:2], int(term[2:])
    return f"SP{year + 1:02d}" if season == "FA" else f"FA{year:02d}"


def term_index(term: str) -> int:
    """Sortable position of a term: SP26 < FA26 < SP27."""
    return int(term[2:]) * 2 + (term[:2] == "FA")


def terms_between(start: str, end: str) -> list[str]:
    """Fall/spring terms from start to end inclusive, e.g. FA24..SP28."""
    terms = [start]
    while terms[-1] != end:
        terms.append(next_term(terms[-1]))
        if len(terms) > 20:
            raise ValueError(f"{end} is not reachable from {start}")
    return terms


def term_label(term: str) -> str:
    return f"{'Fall' if term.startswith('FA') else 'Spring'} ’{term[2:]}"


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def apply_ops(
    placements: list[Placement],
    ops: list[PlanOp],
    catalog: Catalog,
    terms: list[str],
    origin: str = "user",
    slot_labels: dict[str, str] | None = None,
) -> list[Placement]:
    """Return a new placement list with the ops applied. Raises OpError on bad ops.
    `terms` are the plan's terms; adds and moves have to land in one of them.
    The advisor can't touch placements the student locked; the student can still
    remove or replace them, just not move them."""
    result = [p.model_copy() for p in placements]
    by_id = {p.id: p for p in result}

    def check_term(term: str) -> None:
        if term not in terms:
            label = term_label(term) if re.fullmatch(r"(FA|SP)\d{2}", term) else repr(term)
            raise OpError(
                f"{label} isn't in your plan, which runs "
                f"{term_label(terms[0])} to {term_label(terms[-1])}"
            )

    def check_lock(p: Placement) -> None:
        if origin == "advisor" and p.locked:
            raise OpError(
                f"{_name(p)} is locked in {term_label(p.term)} by the student. "
                "Leave it there, or ask them to unlock it."
            )

    for op in ops:
        match op:
            case AddOp():
                check_term(op.term)
                if bool(op.course) == bool(op.slot):
                    raise OpError("add needs exactly one of course or slot")
                credits = 3
                if op.course:
                    course = catalog.get(op.course)
                    if course is None:
                        raise OpError(f"unknown course {op.course}")
                    credits = course.credits
                p = Placement(
                    id=new_id(),
                    term=op.term,
                    course=catalog.get(op.course).code if op.course else None,
                    title=catalog.get(op.course).title if op.course else None,
                    slot=op.slot,
                    slot_label=(slot_labels or {}).get(op.slot) if op.slot else None,
                    credits=credits,
                    origin=origin,
                )
                result.append(p)
                by_id[p.id] = p
            case RemoveOp():
                p = _find(by_id, op.placement_id)
                check_lock(p)
                result.remove(p)
                del by_id[p.id]
            case MoveOp():
                p = _find(by_id, op.placement_id)
                if p.status == "completed":
                    raise OpError(f"{p.course} is already completed")
                check_lock(p)
                if p.locked and p.term != op.term:
                    raise OpError(
                        f"{_name(p)} is kept in {term_label(p.term)}. Unlock it before moving it."
                    )
                check_term(op.term)
                p.term = op.term
                p.origin = origin
            case ReplaceOp():
                p = _find(by_id, op.placement_id)
                if p.status != "planned":
                    taken = "already completed" if p.status == "completed" else "in progress"
                    raise OpError(f"{p.course} is {taken}, so it can't be swapped for another")
                check_lock(p)
                course = catalog.get(op.course)
                if course is None:
                    raise OpError(f"unknown course {op.course}")
                # slot stays set so the audit still knows what this course was meant to fill
                p.course, p.title, p.credits = course.code, course.title, course.credits
                p.origin = origin
            case LockOp():
                if origin == "advisor":
                    raise OpError("Only the student can lock or unlock a placement")
                _find(by_id, op.placement_id).locked = op.locked
    return result


def _name(p: Placement) -> str:
    return p.course or p.slot_label or "That slot"


def _find(by_id: dict[str, Placement], placement_id: str) -> Placement:
    if placement_id not in by_id:
        raise OpError(f"no placement {placement_id}")
    return by_id[placement_id]
