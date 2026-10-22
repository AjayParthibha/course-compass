"""Run evaluation scenarios and write a CSV of results.

    uv run python -m harness.run --mode validate
    uv run python -m harness.run --mode validate --split heldout
    uv run python -m harness.run --mode repair_global --scenarios advisor_scenarios.yaml

    uv run python -m harness.run --mode elicit

Each mode is a function (scenario, catalog, program) -> dict of result columns.
Add new modes (repair, rebuild, llm_direct, advisor...) to MODES.
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from app.catalog.store import get_catalog
from app.planner.audit import audit
from app.planner.elicit import plan_question
from app.planner.eligible import list_eligible
from app.planner.initial import seed_slots
from app.planner.ops import OpError, apply_ops
from app.planner.recommend import standard_courses
from app.planner.solver import RepairRequest, check_plan, repair
from app.planner.validate import validate
from app.requirements.loader import load_program
from app.schemas.plans import PlanOp
from app.schemas.profile import ProfileFact
from harness.scenario import Scenario, load_scenarios

ROOT = Path(__file__).resolve().parents[1]
parse_ops = TypeAdapter(list[PlanOp])


def run_validate(s: Scenario, catalog, program) -> dict:
    """Baseline: apply the requested edits as-is and check the result."""
    placements = s.placements(catalog)
    try:
        placements = apply_ops(
            placements, parse_ops.validate_python(s.resolved_ops()), catalog, s.terms
        )
    except OpError as e:
        return {"predicted": "infeasible", "error": str(e)}
    violations = validate(placements, s.terms, catalog, s.max_credits)
    blocking = [v for v in violations if v.blocking]
    result = audit(placements, program, catalog)
    missing = [r.id for r in result.requirements if r.status == "missing"]
    return {
        "predicted": "feasible" if not blocking else "infeasible",
        "blocking_violations": len(blocking),
        "warnings": len(violations) - len(blocking),
        "missing_requirements": " ".join(missing),
        "moves": 0,
    }


def run_model(s: Scenario, catalog, program) -> dict:
    """The CP-SAT model in check mode on the same edited plan; should match validate."""
    placements = s.placements(catalog)
    try:
        placements = apply_ops(
            placements, parse_ops.validate_python(s.resolved_ops()), catalog, s.terms
        )
    except OpError as e:
        return {"predicted": "infeasible", "error": str(e)}
    checked = check_plan(
        placements, s.terms, s.current, catalog, program, max_credits=s.max_credits
    )
    if not checked.feasible:
        return {"predicted": checked.status, "moves": 0}
    best = check_plan(
        placements,
        s.terms,
        s.current,
        catalog,
        program,
        max_credits=s.max_credits,
        requirements="maximize",
    )
    tops = [r.id for st in program.sets for r in st.requirements]
    return {
        "predicted": checked.status,
        "missing_requirements": " ".join(r for r in tops if r not in best.satisfied),
        "moves": 0,
    }


def _solve(s: Scenario, catalog, program, strategy: str) -> dict:
    """The solver alone on the scenario's structured request, starting from the plan
    onboarding would build (history plus open slots)."""
    if s.request.constraints is None:
        return {"predicted": "n/a", "error": "scenario has no request.constraints"}
    placements = seed_slots(s.placements(catalog), s.terms, s.current, program, catalog)
    request = RepairRequest(**s.request.constraints)
    r = repair(
        placements,
        s.terms,
        s.current,
        catalog,
        program,
        request,
        max_credits=s.max_credits,
        strategy=strategy,
    )
    return {
        "predicted": {"solved": "feasible", "infeasible": "infeasible"}.get(r.status, "timeout"),
        "moves": r.moved,
        "changes": r.moved + r.added + r.removed + r.replaced,
        "optimal": r.optimal,
        "blocking_violations": r.blocking,
        "conflicts": " | ".join(r.conflicts),
    }


def _elicit(s: Scenario, catalog, program, fixed: bool) -> dict:
    """Should the advisor ask before recommending for the request's slot? Adaptive
    (planner/elicit.py) asks only when likely answers lead to different top picks;
    the fixed questionnaire baseline always asks. "feasible" here means it can
    recommend right away, "needs_info" that it asks first."""
    if s.request.slot is None:
        return {"predicted": "n/a", "error": "scenario has no request.slot"}
    req = next((r for r in program.all_requirements() if r.id == s.request.slot.requirement), None)
    if req is None:
        return {"predicted": "n/a", "error": f"no requirement {s.request.slot.requirement}"}
    placements = s.placements(catalog)
    courses = list_eligible(req, s.request.slot.term, placements, catalog)
    if fixed:
        return {"predicted": "needs_info", "questions": 1, "eligible": len(courses)}
    when = datetime.now()
    facts = [
        ProfileFact(
            id=i,
            dimension=d,
            value=v,
            text=v,
            status="stated",
            created_at=when,
            updated_at=when,
        )
        for i, (d, v) in enumerate(s.profile.items(), 1)
    ]
    plan = plan_question(
        courses, facts, placements, catalog, standard_courses(program), req.label.lower()
    )
    q = plan.ask
    return {
        "predicted": "needs_info" if q else "feasible",
        "questions": int(q is not None),
        "eligible": len(courses),
        "question": q.dimension if q else "",
        "options": len(q.options) if q else 0,
        "disagreement": round(q.disagreement, 2) if q else "",
        "reason": plan.reason,
    }


def run_elicit(s: Scenario, catalog, program) -> dict:
    return _elicit(s, catalog, program, fixed=False)


def run_elicit_fixed(s: Scenario, catalog, program) -> dict:
    return _elicit(s, catalog, program, fixed=True)


def run_repair_global(s: Scenario, catalog, program) -> dict:
    return _solve(s, catalog, program, "global")


def run_rebuild(s: Scenario, catalog, program) -> dict:
    return _solve(s, catalog, program, "rebuild")


MODES = {
    "validate": run_validate,
    "model": run_model,
    "repair_global": run_repair_global,
    "rebuild": run_rebuild,
    "elicit": run_elicit,
    "elicit_fixed": run_elicit_fixed,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(MODES), default="validate")
    parser.add_argument("--split", choices=["dev", "heldout"])
    parser.add_argument("--scenarios", type=Path, default=ROOT / "scenarios.yaml")
    args = parser.parse_args()

    catalog = get_catalog()
    rows = []
    for s in load_scenarios(args.scenarios, args.split):
        program = load_program(s.program, s.catalog_year)
        start = time.perf_counter()
        result = MODES[args.mode](s, catalog, program)
        rows.append(
            {
                "scenario": s.id,
                "mode": args.mode,
                "expected": s.expected.outcome,
                **result,
                "correct": result.get("predicted") == s.expected.outcome,
                "runtime_ms": round((time.perf_counter() - start) * 1000, 1),
            }
        )

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{args.mode}.csv"
    columns = list(dict.fromkeys(k for row in rows for k in row))
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    correct = sum(r["correct"] for r in rows)
    print(f"{correct}/{len(rows)} correct · wrote {out.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
