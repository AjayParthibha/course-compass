"""Turn a plan into the units the CP-SAT model reasons about.

A unit is one placement (a course or an open slot) with everything the model needs
precomputed from the catalog and the program, so the model never touches either.
"""

from dataclasses import dataclass

from app.catalog.store import Catalog
from app.planner.audit import matches, subjects_of
from app.schemas.courses import PrereqExpr
from app.schemas.plans import Placement
from app.schemas.requirements import Program


@dataclass(frozen=True)
class Unit:
    id: str
    course: str | None  # catalog code; None for an open slot
    slot: str | None  # requirement id an open slot was made for
    credits: int
    status: str  # completed | in_progress | planned
    term: str  # where it sits in the plan now
    locked: bool
    prereqs: PrereqExpr | None
    # codes whose prerequisites this unit satisfies: itself, cross-listings, equivalents
    credit_for: frozenset[str]
    # equivalent courses share a key; a plan may hold each key once
    dup_key: str | None
    # seasons the course has run in ("FA", "SP"); empty = no history
    seasons: tuple[str, ...]
    # requirement leaves (courses / filter) this unit may count toward
    eligible: tuple[str, ...]
    # its subject and its cross-listings' (for same-subject rules)
    subjects: frozenset[str] = frozenset()
    # subjects it is cross-listed with (for caps like "at most one CS cross-listing")
    cross_listed: frozenset[str] = frozenset()

    @property
    def fixed(self) -> bool:
        """Completed and in-progress units can't move; locked ones stay by request."""
        return self.status != "planned" or self.locked


def build_units(placements: list[Placement], catalog: Catalog, program: Program) -> list[Unit]:
    leaves = [r for r in program.all_requirements() if r.kind in ("courses", "filter")]
    leaf_ids = {r.id for r in leaves}
    units = []
    for p in placements:
        course = catalog.get(p.course) if p.course else None
        if course is None:
            # an open slot, or a course the snapshot doesn't know: credits only
            eligible = (p.slot,) if p.slot in leaf_ids and not p.course else ()
            units.append(
                Unit(
                    id=p.id,
                    course=p.course,
                    slot=p.slot,
                    credits=p.credits,
                    status=p.status,
                    term=p.term,
                    locked=p.locked,
                    prereqs=None,
                    credit_for=frozenset({p.course} if p.course else ()),
                    dup_key=None,
                    seasons=(),
                    eligible=eligible,
                )
            )
            continue
        units.append(
            Unit(
                id=p.id,
                course=course.code,
                slot=p.slot,
                credits=p.credits,
                status=p.status,
                term=p.term,
                locked=p.locked,
                prereqs=course.prereqs,
                credit_for=frozenset(catalog.prereq_credit(course.code)),
                dup_key=min(catalog.equivalents(course.code)),
                seasons=tuple(course.typical_seasons),
                eligible=tuple(r.id for r in leaves if matches(course, r, catalog)),
                subjects=frozenset(subjects_of(course)),
                cross_listed=frozenset(code.split()[0] for code in course.cross_listed),
            )
        )
    return units
