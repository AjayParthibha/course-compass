"""The requirement audit, done exactly: CP-SAT assigns courses to requirements, so a
course goes wherever it does the most good (the greedy audit could spend a course on a
broad rule that a narrower one needed), and category rules such as "liberal studies
from at least three groups" or "two different distribution categories" are checked.

The result has the same shape as the greedy audit's, which stays as a fallback if a
solve ever runs out of time.
"""

from app.catalog.store import Catalog
from app.planner import audit as greedy
from app.planner.ops import term_index
from app.planner.solver.model import Options, PlanModel, Result
from app.planner.solver.units import Unit, build_units
from app.schemas.plans import AuditResult, Placement, RequirementStatus
from app.schemas.requirements import Program, Requirement

TIME_LIMIT = 2.0


def exact_audit(placements: list[Placement], program: Program, catalog: Catalog) -> AuditResult:
    units = build_units(placements, catalog, program)
    terms = sorted({p.term for p in placements}, key=term_index)
    if not terms:
        return greedy.greedy_audit(placements, program, catalog)
    model = PlanModel(
        units,
        terms,
        terms[0],
        program,
        options=Options(fixed=True, requirements="audit", requirements_only=True),
    )
    result = model.solve(TIME_LIMIT)
    if not result.feasible:
        return greedy.greedy_audit(placements, program, catalog)
    return _statuses(placements, units, program, result)


def _statuses(placements, units: list[Unit], program: Program, result: Result) -> AuditResult:
    order = {p.id: i for i, p in enumerate(placements)}
    by_id = {u.id: u for u in units}
    counted: dict[str, list[str]] = {
        rid: sorted(ids, key=order.get) for rid, ids in result.assigned.items()
    }

    def status_of(req: Requirement) -> RequirementStatus:
        children = [status_of(c) for c in req.children]
        open_slots = 0
        credits = credits_needed = None
        if req.kind == "flag_only":
            st, n, ids = "flagged", greedy.needed(req), []
        elif req.kind in ("all_of", "any_of"):
            ranks = [greedy._rank(c.status) for c in children]
            best = max(ranks) if req.kind == "any_of" else min(ranks)
            st, n, ids = greedy._unrank(best), len(children), []
            open_slots = sum(1 for c in children if c.status != "missing" and c.open_slots)
        elif req.kind == "total_credits":
            here = [u for u in units if req.id in u.totals and u.id not in result.no_credit]
            credits = sum(u.credits for u in here)
            credits_needed = req.credits or 0
            done = sum(u.credits for u in here if u.status == "completed")
            st = (
                "done"
                if done >= credits_needed
                else "planned"
                if req.id in result.satisfied
                else "missing"
            )
            n, ids = 1, []
        else:
            ids = counted.get(req.id, [])
            n = greedy.needed(req)
            got = [by_id[i] for i in ids]
            if req.id not in result.satisfied:
                st = "missing"
            elif all(u.status == "completed" for u in got):
                st = "done"
            else:
                st = "planned"
            chosen = sum(1 for u in got if u.course)
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
    used = {i for ids in counted.values() for i in ids}
    unassigned = [p.id for p in placements if p.course and p.id not in used]
    complete = all(r.status in ("done", "planned", "flagged") for r in top)
    return AuditResult(complete=complete, requirements=top, unassigned=unassigned)
