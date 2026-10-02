"""Starter plan after onboarding: one open slot per unfilled requirement seat,
spread across the remaining terms. Placeholder until the CP-SAT planner exists."""

from app.catalog.store import Catalog
from app.planner.audit import audit, needed
from app.planner.ops import new_id
from app.schemas.plans import Placement
from app.schemas.requirements import Program

SLOT_CREDITS = 3


def seed_slots(
    placements: list[Placement], terms: list[str], current: str, program: Program, catalog: Catalog
) -> list[Placement]:
    future = terms[terms.index(current) + 1 :] if current in terms else terms
    if not future:
        return placements
    result = audit(placements, program, catalog)
    statuses = {}

    def collect(reqs):
        for r in reqs:
            statuses[r.id] = r
            collect(r.children)

    collect(result.requirements)

    load = {t: sum(p.credits for p in placements if p.term == t) for t in future}
    out = list(placements)
    for req in program.all_requirements():
        if req.kind not in ("courses", "filter"):
            continue
        missing = needed(req) - len(statuses[req.id].filled)
        for _ in range(max(missing, 0)):
            term = min(future, key=lambda t: load[t])
            load[term] += SLOT_CREDITS
            out.append(
                Placement(
                    id=new_id(),
                    term=term,
                    slot=req.id,
                    slot_label=req.label,
                    credits=SLOT_CREDITS,
                    origin="planner",
                )
            )
    return out
