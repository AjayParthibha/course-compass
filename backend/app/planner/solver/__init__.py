"""CP-SAT planner. See docs in model.py; repair lands on top of `PlanModel`."""

from app.catalog.store import Catalog
from app.planner.solver.model import Options, PlanModel, RequirementMode, Result
from app.planner.solver.units import Unit, build_units
from app.schemas.plans import Placement
from app.schemas.requirements import Program

__all__ = ["Options", "PlanModel", "Result", "Unit", "build_units", "check_plan"]


def check_plan(
    placements: list[Placement],
    terms: list[str],
    current_term: str,
    catalog: Catalog,
    program: Program,
    *,
    max_credits: int = 18,
    term_caps: dict[str, int] | None = None,
    requirements: RequirementMode = "off",
) -> Result:
    """Is this plan allowed as it stands? With requirements off it answers what
    validate() answers; "maximize" also returns the best requirement assignment."""
    units = build_units(placements, catalog, program)
    model = PlanModel(
        units,
        terms,
        current_term,
        program,
        max_credits=max_credits,
        term_caps=term_caps,
        options=Options(fixed=True, requirements=requirements),
    )
    return model.solve()
