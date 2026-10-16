"""Global minimum-disruption repair, and the rebuild baseline.

Both solve the same model; only the cost differs. Repair minimises
2 × (courses or slots added + dropped) + 1 × moves, then, among those plans, balances the
load (lighter-term wishes, the soft 12-credit minimum, the heaviest term). Rebuild leaves
moves free, so its plan is whatever balances best; its moves are counted afterwards.

What a repair may do: move any planned course or slot that isn't locked; drop open slots
(and courses, only when asked); add open slots for filter requirements and long course
lists, and a course from a short list of alternatives (CS 4410 or CS 4414). It never
picks electives. Every top-level requirement
the plan meets now must still be met. The request and saved caps sit behind assumption
literals, so an impossible request comes back as the short list of things that clash.
"""

import time
from dataclasses import replace
from typing import Literal

from ortools.sat.python import cp_model

from app.catalog.store import Catalog, normalize_code
from app.planner.audit import audit, needed
from app.planner.ops import SLOT_CREDITS, OpError, apply_ops, term_label
from app.planner.solver.explain import explain_conflict
from app.planner.solver.model import Options, PlanModel, Result
from app.planner.solver.types import AddWish, RepairRequest, RepairResult
from app.planner.solver.units import Unit, build_units
from app.planner.validate import validate
from app.schemas.plans import AddOp, MoveOp, Placement, PlanOp, RemoveOp, ReplaceOp
from app.schemas.requirements import Program

ADD_OR_DROP = 2
MOVE = 1
LIGHT = 12  # credits below which a term is "light" (a soft minimum)
# a list this short is a choice between alternatives (CS 4410 or CS 4414), which the solver
# may make; a longer one (the practicum list) is an elective pick, so it gets open slots
NAMED_LIST_LIMIT = 4


class RequestError(ValueError):
    """The request names something that isn't in the plan or the catalog."""


def repair(
    placements: list[Placement],
    terms: list[str],
    current_term: str,
    catalog: Catalog,
    program: Program,
    request: RepairRequest | None = None,
    *,
    max_credits: int = 18,
    term_caps: dict[str, int] | None = None,
    strategy: Literal["global", "rebuild"] = "global",
    slot_labels: dict[str, str] | None = None,
    time_limit: float = 2.0,
    seed: int = 0,
    suggest: bool = True,
) -> RepairResult:
    """`suggest`: when the request can't be met, also try nearby versions of it and
    return the ones that work as `alternatives`."""
    start = time.perf_counter()
    request = request or RepairRequest()
    by_id = {p.id: p for p in placements}
    _check(request, by_id, terms, catalog)
    caps = {**(term_caps or {}), **request.term_caps}
    avoid = {code for c in request.avoid_courses for code in catalog.equivalents(normalize_code(c))}

    units = build_units(placements, catalog, program)
    extra, wishes = _candidates(placements, catalog, program, avoid, request)
    avoided = [u for u in units if u.course and u.course in avoid and u.status == "planned"]
    optional = {u.id for u in extra} | set(request.remove) | {u.id for u in avoided}
    # planned courses and open slots may come out; a course without the student's say-so
    # only behind a "stays" assumption, so a conflict can name the course that's in the way
    optional |= {u.id for u in units if u.status == "planned" and not u.locked}
    stays = [
        u
        for u in units
        if u.status == "planned"
        and not u.locked
        and u.course
        and not request.allow_removing_courses
        and u.id not in request.remove
        and u not in avoided
    ]
    # don't break what works: every top-level requirement met now stays met
    keep_met = {
        r.id
        for r in audit(placements, program, catalog).requirements
        if r.status in ("done", "planned")
    }

    model = PlanModel(
        units + extra,
        terms,
        current_term,
        program,
        max_credits=max_credits,
        term_caps=caps,
        options=Options(
            fixed=False,
            offerings=True,
            optional=frozenset(optional),
            keep_met=frozenset(keep_met),
            check_fixed=False,
            explain=True,
        ),
    )
    _request_constraints(model, request, units, avoided, wishes)
    for u in stays:
        model.only_if(model.m.Add(model.present[u.id] == 1), model.guard(("stays", u.id)))

    moves = [
        _moved(model, u)
        for u in units
        if u.status == "planned" and not u.locked and u.term in model.index
    ]
    drops = [1 - model.present[u.id] for u in units if u.id in optional]
    adds = [model.present[u.id] for u in extra]
    fills = _fills(model, units, extra, optional)
    # a course that takes over an open slot for the same requirement is one change (a
    # replace), not an add plus a drop
    cost = (
        ADD_OR_DROP * (sum(adds) + sum(drops))
        - (2 * ADD_OR_DROP - 1) * sum(fills.values())
        + (MOVE * sum(moves) if strategy == "global" else 0)
    )
    model.m.Minimize(cost)
    for u in units:  # start from the plan as it is
        if (t := model.index.get(u.term)) in model.x[u.id]:
            model.m.AddHint(model.x[u.id][t], 1)

    first = model.solve(time_limit, seed)
    if first.status == "infeasible":
        conflicts = _smallest_conflict(model, first.core, time_limit, seed)
        reasons = explain_conflict(conflicts, by_id, program, request.term_caps, catalog)
        options: list[str] = []
        if suggest:
            options = _alternatives(
                conflicts,
                request,
                by_id,
                lambda req: repair(
                    placements,
                    terms,
                    current_term,
                    catalog,
                    program,
                    req,
                    max_credits=max_credits,
                    term_caps=term_caps,
                    strategy=strategy,
                    time_limit=time_limit,
                    seed=seed,
                    suggest=False,
                ),
                terms[terms.index(current_term) + 1 :] if current_term in terms else terms,
                (term_caps or {}),
                max_credits,
            )
        return RepairResult(
            status="infeasible",
            strategy=strategy,
            conflicts=reasons,
            alternatives=options,
            runtime_ms=_ms(start),
        )
    if first.status == "unknown":
        return RepairResult(status="timeout", strategy=strategy, runtime_ms=_ms(start))

    best = _balance(model, first, request, cost, time_limit, seed)
    filled = [pair for pair, var in fills.items() if best.values.get(var.Name())]
    ops = diff_ops(units, extra, best, optional, filled)
    result = RepairResult(
        status="solved",
        strategy=strategy,
        ops=ops,
        moved=sum(isinstance(op, MoveOp) for op in ops),
        added=sum(isinstance(op, AddOp) for op in ops),
        replaced=sum(isinstance(op, ReplaceOp) for op in ops),
        removed=sum(1 for u in units if u.id in optional and _absent(model, u, best)) - len(filled),
        optimal=first.optimal,
        runtime_ms=0,
    )
    try:
        repaired = apply_ops(placements, ops, catalog, terms, slot_labels=slot_labels)
        result.blocking = sum(
            v.blocking for v in validate(repaired, terms, catalog, max_credits, caps)
        )
    except OpError as e:  # would mean diff_ops is wrong; surface it rather than hide it
        result.status, result.conflicts = "infeasible", [f"Internal error applying the repair: {e}"]
    result.runtime_ms = _ms(start)
    return result


def rebuild(*args, **kwargs) -> RepairResult:
    return repair(*args, **kwargs, strategy="rebuild")


# the request ---------------------------------------------------------------------


def _check(request: RepairRequest, by_id: dict[str, Placement], terms: list[str], catalog: Catalog):
    named = (("keep", request.keep), ("remove", request.remove), ("move", list(request.move)))
    for field, ids in named:
        for pid in ids:
            if pid not in by_id:
                raise RequestError(f"{field}: no placement {pid} in the plan")
    for term in [
        *request.term_caps,
        *request.lighter_terms,
        *request.move.values(),
        *[w.term for w in request.add if w.term],
    ]:
        if term not in terms:
            raise RequestError(f"{term} isn't one of the plan's terms")
    if request.graduate_by and request.graduate_by not in terms:
        raise RequestError(f"graduate_by: {request.graduate_by} isn't one of the plan's terms")
    for w in request.add:
        if catalog.get(w.course) is None:
            raise RequestError(f"add: unknown course {w.course}")


def _candidates(
    placements, catalog, program, avoid, request
) -> tuple[list[Unit], dict[str, tuple]]:
    """Units the solver may add: open slots for filter requirements and long course lists
    (as many as each needs), a course from a short list of alternatives when the plan
    doesn't already cover that requirement (CS 4414 once CS 4410 is dropped), and the
    courses the request asks for. An alternative only counts for its own requirement, so
    the solver can't use one as an elective."""
    leaving = set(request.remove)
    staying = [p for p in placements if p.course and p.id not in leaving]
    in_plan = {code for p in staying for code in catalog.equivalents(p.course)} - avoid
    # a course on its way out can't come back as its own replacement
    gone = {
        code
        for p in placements
        if p.course and p.id in leaving
        for code in catalog.equivalents(p.course)
    }
    extra: dict[str, Placement] = {}
    only_for: dict[str, str] = {}  # candidate id -> the one requirement it may fill
    for r in program.all_requirements():
        if r.kind == "filter" or (r.kind == "courses" and len(r.courses) > NAMED_LIST_LIMIT):
            for i in range(needed(r)):
                pid = f"new-slot:{r.id}:{i}"
                extra[pid] = Placement(
                    id=pid, term="", slot=r.id, slot_label=r.label, credits=SLOT_CREDITS
                )
        elif r.kind == "courses":
            options = [c for code in r.courses if (c := catalog.get(code))]
            if any(catalog.equivalents(c.code) & in_plan for c in options):
                continue  # already covered by a course that's staying
            for course in options:
                if catalog.equivalents(course.code) & (avoid | gone | in_plan):
                    continue
                pid = f"new:{course.code}"
                extra[pid] = Placement(id=pid, term="", course=course.code, credits=course.credits)
                only_for[pid] = r.id
    wishes: dict[str, tuple] = {}
    for w in request.add:
        course = catalog.get(w.course)
        pid = f"new:{course.code}"
        extra.setdefault(
            pid, Placement(id=pid, term="", course=course.code, credits=course.credits)
        )
        only_for.pop(pid, None)  # asked for by name: it counts wherever it fits
        wishes[pid] = ("add", course.code, w.term)
    units = build_units(list(extra.values()), catalog, program)
    units = [replace(u, eligible=(only_for[u.id],)) if u.id in only_for else u for u in units]
    return units, wishes


def _request_constraints(model: PlanModel, request: RepairRequest, units, avoided, wishes):
    m, x, present = model.m, model.x, model.present
    by_id = {u.id: u for u in units}
    for pid in request.keep:
        g = model.guard(("keep", pid))
        spot = x[pid].get(model.index.get(by_id[pid].term))
        model.only_if(m.Add(spot == 1) if spot is not None else m.AddBoolOr([]), g)
    for pid, term in request.move.items():
        g = model.guard(("move", pid, term))
        spot = x[pid].get(model.index[term])
        model.only_if(m.Add(spot == 1) if spot is not None else m.AddBoolOr([]), g)
    for pid in request.remove:
        model.only_if(m.Add(present[pid] == 0), model.guard(("remove", pid)))
    for u in avoided:
        model.only_if(m.Add(present[u.id] == 0), model.guard(("avoid", u.course)))
    for pid, key in wishes.items():
        g = model.guard(key)
        model.only_if(m.Add(present[pid] == 1), g)
        if term := key[2]:
            spot = x[pid].get(model.index[term])
            model.only_if(m.Add(spot == 1) if spot is not None else m.AddBoolOr([]), g)
    if request.graduate_by:
        last = model.index[request.graduate_by]
        g = model.guard(("graduate", request.graduate_by))
        for spots in x.values():
            for t, var in spots.items():
                if t > last:
                    model.only_if(m.Add(var == 0), g)


def _fills(model: PlanModel, units, extra, optional) -> dict[tuple[str, str], cp_model.IntVar]:
    """(open slot, course) pairs where the course can take the slot's place: same
    requirement, the slot's term, the slot dropped and the course added."""
    m, x, present = model.m, model.x, model.present
    fills: dict[tuple[str, str], cp_model.IntVar] = {}
    slots = [u for u in units if u.course is None and u.id in optional and u.term in model.index]
    for c in (u for u in extra if u.course):
        for s in slots:
            t = model.index[s.term]
            if t not in x[c.id] or not set(c.eligible) & set(s.eligible):
                continue
            f = m.NewBoolVar(f"fill:{s.id}:{c.id}")
            m.Add(f <= present[c.id])
            m.Add(f <= 1 - present[s.id])
            m.AddImplication(f, x[c.id][t])
            model.watch[f.Name()] = f
            fills[(s.id, c.id)] = f
    for key in {s for s, _ in fills} | {c for _, c in fills}:
        m.AddAtMostOne(f for pair, f in fills.items() if key in pair)
    return fills


def _moved(model: PlanModel, u: Unit):
    stay = model.x[u.id].get(model.index[u.term])
    return model.present[u.id] - stay if stay is not None else model.present[u.id]


# solving ---------------------------------------------------------------------------


def _balance(
    model: PlanModel, first: Result, request: RepairRequest, cost, time_limit, seed
) -> Result:
    """Second phase: keep the disruption at its minimum and even out the terms."""
    m = model.m
    m.Add(cost <= round(first.objective or 0))
    last = model.index[request.graduate_by] if request.graduate_by else len(model.terms) - 1
    future = range(model.now + 1, last + 1)
    lighter = sum(
        model.credits_in(model.index[t])
        for t in request.lighter_terms
        if model.index[t] > model.now
    )
    short, peak = [], m.NewIntVar(0, 60, "peak")
    for t in future:
        load = model.credits_in(t)
        s = m.NewIntVar(0, LIGHT, f"short[{t}]")
        m.Add(s >= LIGHT - load)
        m.Add(peak >= load)
        short.append(s)
    m.ClearObjective()
    m.Minimize(10 * lighter + 3 * sum(short) + peak)
    m.ClearHints()
    for uid, term in first.terms.items():
        m.AddHint(model.x[uid][model.index[term]], 1)
    second = model.solve(time_limit, seed)
    return second if second.feasible else first


def _smallest_conflict(model: PlanModel, core: list[tuple], time_limit, seed) -> list[tuple]:
    """Shrink CP-SAT's conflict by dropping one assumption at a time: whatever can go
    while the rest still clash wasn't part of the reason."""
    keys = list(core) or list(model.guards)
    for key in list(keys):
        if len(keys) <= 1:
            break
        trial = [k for k in keys if k != key]
        r = model.solve(
            min(time_limit, 0.5), seed, assume=[model.guards[k] for k in trial], first_solution=True
        )
        if r.status == "infeasible":
            keys = [k for k in trial if not r.core or k in r.core]
    return keys


def _alternatives(conflicts, request, by_id, attempt, future, saved_caps, max_credits) -> list[str]:
    """Nearby versions of an impossible request, each checked: other terms for a course
    the student wanted somewhere specific, the lowest cap that works, a later graduation,
    dropping what depends on a course they want to drop. Only the ones with a plan are
    returned, so the advisor never offers an option that fails too."""

    def works(**update) -> RepairResult | None:
        r = attempt(request.model_copy(update=update))
        return r if r.status == "solved" else None

    def name(pid: str) -> str:
        p = by_id[pid]
        return p.course or p.slot_label or "that slot"

    out: list[str] = []
    for kind, *rest in conflicts:
        if kind == "move":
            pid, wanted = rest
            ok = [t for t in future if t != wanted and works(move={**request.move, pid: t})]
            if ok:
                here = [
                    term_label(t) + (" (where it is now)" if t == by_id[pid].term else "")
                    for t in ok
                ]
                out.append(f"{name(pid)} could go in {_either(here)} instead")
        elif kind == "add":
            code, wanted = rest
            others = [w for w in request.add if w.course != code]
            ok = [
                t
                for t in future
                if t != wanted and works(add=[*others, AddWish(course=code, term=t)])
            ]
            if ok:
                out.append(f"{code} could go in {_either([term_label(t) for t in ok])} instead")
        elif kind == "cap" and rest[0] in request.term_caps:
            term, cap = rest
            limit = saved_caps.get(term, max_credits)

            def fits(c: int, term=term) -> bool:
                return works(term_caps={**request.term_caps, term: c}) is not None

            # a higher cap only ever allows more plans, so search for the lowest that works
            lowest = None
            if cap < limit and fits(limit):
                lo, hi = cap + 1, limit
                while lo < hi:
                    mid = (lo + hi) // 2
                    lo, hi = (lo, mid) if fits(mid) else (mid + 1, hi)
                lowest = lo
            if lowest is not None:
                out.append(f"{term_label(term)} can go down to {lowest} credits")
        elif kind == "graduate":
            (wanted,) = rest
            later = future[future.index(wanted) + 1 :] if wanted in future else []
            when = next((t for t in later if works(graduate_by=t)), None)
            if when:
                out.append(f"Graduating in {term_label(when)} works")
        elif kind == "remove":
            (pid,) = rest
            r = works(allow_removing_courses=True)
            if r:
                gone = [name(op.placement_id) for op in r.ops if isinstance(op, RemoveOp)]
                also = [g for g in dict.fromkeys(gone) if g != name(pid)]
                if also:
                    out.append(f"Dropping {name(pid)} works if {_either(also, 'and')} go too")
    return list(dict.fromkeys(out))


def _either(items: list[str], joiner: str = "or") -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {joiner} {items[-1]}"


# the result as plan edits ----------------------------------------------------------


def _absent(model: PlanModel, u: Unit, result: Result) -> bool:
    # a completed course outside the plan's terms has no term but is still there
    return u.id not in result.terms and u.id in model.opts.optional


def diff_ops(
    units: list[Unit],
    extra: list[Unit],
    result: Result,
    optional: set[str],
    filled: list[tuple[str, str]] = (),
) -> list[PlanOp]:
    """Drops first, then slots filled in place, then moves, then additions, so every op
    lands on a valid plan."""
    drops: list[PlanOp] = []
    moves: list[PlanOp] = []
    course_of = {u.id: u.course for u in extra}
    replaces: list[PlanOp] = [
        ReplaceOp(placement_id=slot, course=course_of[cand]) for slot, cand in filled
    ]
    taken = {slot for slot, _ in filled} | {cand for _, cand in filled}
    for u in units:
        term = result.terms.get(u.id)
        if u.id in taken:
            continue
        if term is None and u.id in optional:
            drops.append(RemoveOp(placement_id=u.id))
            if u.course and u.slot:
                # the first remove only empties a filled slot; the second drops the slot
                drops.append(RemoveOp(placement_id=u.id))
        elif term is not None and term != u.term:
            moves.append(MoveOp(placement_id=u.id, term=term))
    adds: list[PlanOp] = [
        AddOp(term=result.terms[u.id], course=u.course)
        if u.course
        else AddOp(term=result.terms[u.id], slot=u.slot)
        for u in extra
        if u.id in result.terms and u.id not in taken
    ]
    return drops + replaces + moves + adds


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)
