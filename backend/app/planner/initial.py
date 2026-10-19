"""Starter plan after onboarding: one open slot per unfilled requirement seat (more
if a rule's category limits still aren't met), then elective slots up to the degree's
credit total, spread across the remaining terms (or in the earliest ones for
requirements marked `seed: earliest`)."""

from app.catalog.store import Catalog
from app.planner.audit import audit, fill_order, needed
from app.planner.ops import SLOT_CREDITS, new_id
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

    def add(req: Requirement, i: int, label: str | None = None) -> bool:
        room = [t for t in future if load[t] + SLOT_CREDITS <= caps[t]]
        if not room:
            return False
        if req.seed == "earliest":
            term = room[min(i, len(room) - 1)]
        else:
            term = min(room, key=lambda t: load[t])
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
        leaves = [r for r in stage.all_requirements() if r.kind in ("courses", "filter")]
        # place the early ones first so the spread ones balance around them
        leaves.sort(key=lambda r: r.seed != "earliest")
        statuses = _statuses(out, stage, catalog)
        for req in leaves:
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


def _catch_all(r: Requirement) -> bool:
    """An elective that takes nearly anything (the advisor- and major-approved
    electives), as opposed to one with a rule of its own (same subject, qualifying
    prerequisite)."""
    f = r.filter
    if r.kind != "filter" or f is None or fill_order(r) != 2:
        return False
    return not (f.qualifying_prereq or r.same_subject or r.groups)


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
