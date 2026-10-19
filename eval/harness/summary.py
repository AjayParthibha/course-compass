"""Summarise advisor eval results: the comparison table for the report, the spread across
repeats, and how often each scenario passed.

    uv run python -m harness.summary results/20261016-105458-advisor.csv
"""

import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

# third-party rates for gpt-5.6-terra (USD per million tokens); confirm on OpenAI's page
PRICE_INPUT, PRICE_CACHED, PRICE_OUTPUT = 2.00, 0.20, 12.00


def load(path: Path) -> list[dict]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.open()]
    return list(csv.DictReader(path.open()))


def _num(v) -> float:
    if v in ("", None):
        return 0.0
    if isinstance(v, bool) or v in ("True", "False"):
        return float(v in (True, "True"))
    return float(v)


def _true(v) -> bool:
    return v is True or v == "True"


def cost(rows: list[dict]) -> float:
    total_in = sum(_num(r.get("input_tokens")) for r in rows)
    cached = sum(_num(r.get("cached_tokens")) for r in rows)
    out = sum(_num(r.get("output_tokens")) for r in rows)
    return ((total_in - cached) * PRICE_INPUT + cached * PRICE_CACHED + out * PRICE_OUTPUT) / 1e6


def summarize(rows: list[dict]) -> str:
    lines = []
    modes = list(dict.fromkeys(r["mode"] for r in rows))
    for mode in modes:
        m = [r for r in rows if r["mode"] == mode]
        by_rep = defaultdict(list)
        for r in m:
            by_rep[r.get("repeat", 1)].append(r)
        scores = [sum(_true(r["correct"]) for r in rs) for rs in by_rep.values()]
        n = len(next(iter(by_rep.values())))
        made = [r for r in m if r.get("blocking") not in ("", None)]
        broke = sum(bool(r.get("broke_requirements")) for r in made)
        feas = [r for r in m if r["expected"] == "feasible"]
        inf = [r for r in m if r["expected"] == "infeasible"]
        spread = f"{min(scores)}–{max(scores)}" if len(scores) > 1 else str(scores[0])
        runs = f"{len(scores)} run{'s' if len(scores) > 1 else ''}"
        lines.append(
            f"{mode}: {st.mean(scores):.1f}/{n} correct on average (range {spread}, {runs})"
        )
        lines.append(
            f"  possible {sum(_true(r['correct']) for r in feas)}/{len(feas)}"
            f" · impossible {sum(_true(r['correct']) for r in inf)}/{len(inf)}"
            f" · blocking proposals {sum(_num(r['blocking']) > 0 for r in made)}/{len(made)}"
            f" · broke a requirement {broke}/{len(made)}"
            f" · jargon {sum(bool(r.get('jargon')) for r in m)}/{len(m)}"
        )
        total = sum(_num(r.get("input_tokens")) for r in m)
        cached = sum(_num(r.get("cached_tokens")) for r in m)
        if total:
            lines.append(
                f"  median {st.median(_num(r['tool_calls']) for r in m):.0f} tool calls"
                f" · {st.median(_num(r['seconds']) for r in m):.1f} s"
                f" · {total / len(m) / 1000:.1f}k input tokens per request"
                f" ({cached / total:.0%} cached)"
                f" · ≈${cost(m):.2f} total"
            )
    lines.append("")
    lines.append("pass rate per scenario:")
    for sid in dict.fromkeys(r["scenario"] for r in rows):
        cells = []
        for mode in modes:
            rs = [r for r in rows if r["scenario"] == sid and r["mode"] == mode]
            cells.append(f"{mode} {sum(_true(r['correct']) for r in rs)}/{len(rs)}")
        lines.append(f"  {sid:30} " + " · ".join(cells))
    return "\n".join(lines)


if __name__ == "__main__":
    print(summarize(load(Path(sys.argv[1]))))
