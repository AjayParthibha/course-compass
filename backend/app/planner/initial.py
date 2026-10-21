"""Starter plan after onboarding: one open slot per unfilled requirement seat (more
if a rule's category limits still aren't met), then elective slots up to the degree's
credit total.

Slots follow prerequisites: a slot for named courses (CS 3410 or 3420) goes in the
first term after its prerequisites, whether those are courses in the plan or slots placed
before it, and an elective goes no earlier than its level suggests (a 4000-level elective
from the third year), in the lightest such term. Requirements marked `seed: earliest`
(writing seminars) take the earliest terms."""

from app.catalog.store import Catalog
from app.planner.audit import audit, fill_order, needed
from app.planner.ops import SLOT_CREDITS, new_id
from app.schemas.courses import AllOf, AnyOf, CourseReq, PrereqExpr
from app.schemas.plans import Placement
from app.schemas.requirements import Program, Requirement


def seed_slots(
    placements: list[Placement],
    terms: list[str],
    current: str,
    program: Program,
    catalog: Catalog,
    max_credits: int = 18,
    term_caps: dict[str, int] | None = None,
) -> list[Placement]:
    """Open slots for what the plan still needs, never past a term's credit cap: when
    everything doesn't fit, the plan shows the shortfall instead of an overload."""
    future = terms[terms.index(current) + 1 :] if current in terms else terms
    if not future:
        return placements
    caps = {t: (term_caps or {}).get(t, max_credits) for t in future}
    load = {t: sum(p.credits for p in placements if p.term == t) for t in future}
    out = list(placements)
    index = {t: i for i, t in enumerate(terms)}
    order = Order(terms, future, catalog)
    for p in placements:
        if p.course and p.term in index:
            order.place(catalog.prereq_credit(p.course), index[p.term])

    def add(req: Requirement, i: int, label: str | None = None) -> bool:
        room = [t for t in future if load[t] + SLOT_CREDITS <= caps[t]]
        if not room:
            return False
        if req.seed == "earliest":
            term = room[min(i, len(room) - 1)]
        else:
            code, start = order.next_course(req)
            later = [t for t in room if index[t] >= start] or room[-1:]
            # a named course as soon as its prerequisites allow, so the courses that need
            # it can follow; an elective wherever the load is lightest
            term = later[0] if req.kind == "courses" else min(later, key=lambda t: load[t])
            if code:
                order.place([code], index[term])
        load[term] += SLOT_CREDITS
        out.append(
            Placement(
                id=new_id(),
                term=term,
                slot=req.id,
                slot_label=label or req.label,
                credits=SLOT_CREDITS,
                origin="planner",
            )
        )
        return True

    # specific requirements first, catch-all electives after, so a course the student
    # already has counts where only it could (liberal studies) and the electives that
    # take anything get the open slots
    specific = _without_catch_alls(program)
    for stage in (specific, program):
        statuses = _statuses(out, stage, catalog)
        skip = _other_branches(stage, statuses)
        leaves = [
            r
            for r in stage.all_requirements()
            if r.kind in ("courses", "filter") and r.id not in skip
        ]
        # writing seminars first, then named courses in prerequisite order (each one can
        # move the courses that need it later), then the electives around them
        todo = sorted(leaves, key=lambda r: (r.seed != "earliest", r.kind != "courses"))
        while todo:
            named = [r for r in todo if r.kind == "courses" and r.seed != "earliest"]
            first = lambda r: order.next_course(r)[1]  # noqa: E731
            req = min(named, key=first) if named and todo[0] in named else todo[0]
            todo.remove(req)
            for i in range(max(needed(req) - len(statuses[req.id].filled), 0)):
                add(req, i)
        # a rule can still be short with every seat filled (liberal studies from too few
        # groups, credits short): add slots until it's met, at most one round per seat
        for req in leaves:
            for i in range(needed(req)):
                if _statuses(out, stage, catalog)[req.id].status != "missing" or not add(req, i):
                    break

    # then electives up to the degree's credit total (123 for CS)
    for req in program.all_requirements():
        if req.kind != "total_credits":
            continue
        short = (req.credits or 0) - (_statuses(out, program, catalog)[req.id].credits or 0)
        for i in range(max(0, -(-short // SLOT_CREDITS))):
            if not add(req, i, "Elective"):
                break
    return out


class Order:
    """When the courses a slot stands for could first be taken: after the courses or
    slots that satisfy their prerequisites. Term positions index `terms`; nothing still
    to take goes before the first future term."""

    def __init__(self, terms: list[str], future: list[str], catalog: Catalog):
        self.first = terms.index(future[0])
        self.catalog = catalog
        self.at: dict[str, int] = {}  # course code -> the term index it's taken in

    def place(self, codes, term: int):
        for code in codes:
            self.at[code] = min(self.at.get(code, term), term)

    def next_course(self, req: Requirement) -> tuple[str | None, int]:
        """For a course list, the listed course not yet in the plan that could come first
        (the one a new slot stands for) and its earliest term; for an elective, the
        earliest term its level suggests."""
        if req.kind == "courses":
            memo: dict[str, int] = {}
            # a listed course the roster doesn't have can't be taken, so a slot isn't it
            left = [c for c in req.courses if c not in self.at and c in self.catalog]
            if not left:
                return None, self.first
            start, code = min((self._start(c, memo, frozenset()), c) for c in left)
            return code, start
        level = req.filter.min_level if req.filter and req.filter.min_level else 0
        return None, max(self.first, _floor(level))

    def _start(self, code: str, memo: dict, seen: frozenset) -> int:
        if code in self.at:
            return self.at[code]
        if code not in memo:
            course = self.catalog.get(code)
            ready = self._ready(course.prereqs, memo, seen | {code}) if course else 0
            memo[code] = max(self.first, ready, _floor(course.level if course else 0))
        return memo[code]

    def _ready(self, expr: PrereqExpr | None, memo: dict, seen: frozenset) -> int:
        """The first term index at which `expr` is satisfied."""
        if isinstance(expr, CourseReq):
            if expr.code in seen:
                return 0  # a cycle in the roster data
            after = 0 if expr.concurrent else 1
            return self._start(expr.code, memo, seen) + after
        if isinstance(expr, AllOf):
            return max((self._ready(e, memo, seen) for e in expr.items), default=0)
        if isinstance(expr, AnyOf):
            return min((self._ready(e, memo, seen) for e in expr.items), default=0)
        return 0  # no prerequisites, or one only a person can check


def _floor(level: int) -> int:
    """The earliest term index (from the first term) for a course at this level: 2000-
    level from the first year, 3000 from the second, 4000 and up from the third."""
    return 2 * min(3, max(0, level // 1000 - 2))


def _catch_all(r: Requirement) -> bool:
    """An elective that takes nearly anything (the advisor- and major-approved
    electives), as opposed to one with a rule of its own (same subject, qualifying
    prerequisite)."""
    f = r.filter
    if r.kind != "filter" or f is None or fill_order(r) != 2:
        return False
    return not (f.qualifying_prereq or r.same_subject or r.groups)


def _other_branches(program: Program, statuses: dict) -> set[str]:
    """Ids under "one of" rules that shouldn't get slots: every option once one is met
    or planned, and otherwise every option but the one with the most progress (the
    first listed on a tie). Options the student only confirms (flag_only) are never
    picked, so "an intermediate course or 11 credits" seeds the intermediate course."""
    skip: set[str] = set()
    for r in program.all_requirements():
        if r.kind != "any_of" or r.id in skip:
            continue
        if statuses[r.id].status in ("done", "planned"):
            keep = None
        else:
            options = [c for c in r.children if c.kind != "flag_only"]
            keep = max(options, key=lambda c: _progress(c, statuses), default=None)
        for child in r.children:
            if child is not keep:
                skip.update(d.id for d in child.walk())
    return skip


def _progress(req: Requirement, statuses: dict) -> tuple[int, int]:
    """How far along an option is: its status, then how many courses count toward it."""
    st = statuses[req.id]
    filled = len(st.filled) + sum(_progress(c, statuses)[1] for c in req.children)
    return ["missing", "flagged", "planned", "done"].index(st.status), filled


def _without_catch_alls(program: Program) -> Program:
    """The program minus its top-level catch-all electives and credit totals."""
    sets = [
        s.model_copy(
            update={
                "requirements": [
                    r for r in s.requirements if r.kind != "total_credits" and not _catch_all(r)
                ]
            }
        )
        for s in program.sets
    ]
    return program.model_copy(update={"sets": sets})


def _statuses(placements, program, catalog) -> dict:
    found = {}

    def collect(reqs):
        for r in reqs:
            found[r.id] = r
            collect(r.children)

    collect(audit(placements, program, catalog).requirements)
    return found
