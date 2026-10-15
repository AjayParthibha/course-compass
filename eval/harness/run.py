"""Run evaluation scenarios and write a CSV of results.

    uv run python -m harness.run --mode validate
    uv run python -m harness.run --mode validate --split heldout

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
from app.planner.ops import OpError, apply_ops
from app.planner.solver import check_plan
from app.planner.validate import validate
from app.requirements.loader import load_program
from app.schemas.plans import PlanOp
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


MODES = {"validate": run_validate, "model": run_model}


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
