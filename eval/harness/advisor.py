"""Run the real advisor on scenarios, with and without the solver tool.

    OPENAI_API_KEY=... uv run python -m harness.advisor
    OPENAI_API_KEY=... uv run python -m harness.advisor --modes llm_direct --only adv-1

Modes:
  llm_direct      today's advisor: the model writes the edits with propose_changes, the
                  planner checks them, and it may retry within its tool budget
  advisor_repair  the same advisor with the repair_plan tool and the prompt that uses it

Every run gets a fresh student in a throwaway database, built the way onboarding builds
one (history plus the starter plan's open slots), so nothing touches real data. If the
advisor stops to ask a question, it gets one "Yes, go ahead." reply. The last proposal
is then scored independently: blocking violations under the saved settings, whether it
does what the student asked (the scenario's `request.constraints`), and how many changes
it makes against the solver's proven minimum.
"""

import os
import tempfile

# the throwaway database has to be configured before the app is imported
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"

import argparse  # noqa: E402
import asyncio  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import secrets  # noqa: E402
import time  # noqa: E402
from dataclasses import replace  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import patch  # noqa: E402

import openai  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import models, services  # noqa: E402
from app.advisor import loop, prompts, tools  # noqa: E402
from app.catalog.store import get_catalog  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import Base, SessionLocal, engine  # noqa: E402
from app.planner import initial  # noqa: E402
from app.planner.audit import audit  # noqa: E402
from app.planner.initial import seed_slots  # noqa: E402
from app.planner.ops import OpError, apply_ops  # noqa: E402
from app.planner.solver import Options, PlanModel, RepairRequest, build_units, repair  # noqa: E402
from app.planner.validate import validate  # noqa: E402
from app.requirements.loader import load_program  # noqa: E402
from app.schemas.plans import AddOp, MoveOp, PlanOp, RemoveOp  # noqa: E402
from harness.scenario import Scenario, load_scenarios  # noqa: E402
from harness.summary import summarize  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
parse_ops = TypeAdapter(list[PlanOp])

# what the prompt said before repair_plan existed, for llm_direct
REPAIR_RULE_START = "- You never edit the plan directly."
OLD_RULE = (
    "- You never edit the plan directly. Use propose_changes; the student reviews and applies it.\n"
)
# words a student shouldn't see: the system talking about itself
JARGON = re.compile(
    r"\b(solver|constraints?|planner|placements?|proposal \d+|repair_plan|propose_changes"
    r"|infeasible|feasible)\b",
    re.IGNORECASE,
)
# a reply that turns the request down: "No.", "Not with…", "can't", "couldn't", "infeasible"
IMPOSSIBLE = re.compile(
    r"^\W*(no|not with)\b|can['’]t|cannot|couldn['’]t|not possible|isn['’]t possible"
    r"|impossible|infeasible|(isn['’]t|not) feasible|won['’]t fit|doesn['’]t fit|no way",
    re.IGNORECASE,
)


def prompt_without_repair(system: str) -> str:
    start = system.index(REPAIR_RULE_START)
    end = system.index("- Placements marked locked")
    return system[:start] + OLD_RULE + system[end:]


def make_student(db, s: Scenario) -> models.Student:
    """The student onboarding would create. Slot ids come from the scenario id, so a saved
    proposal's edits can be re-scored later against the same starting plan."""
    catalog = get_catalog()
    program = load_program(s.program, s.catalog_year)
    st = models.Student(
        code=f"EVAL-{secrets.token_hex(6)}",
        token=secrets.token_urlsafe(24),
        program=s.program,
        catalog_year=s.catalog_year,
        entering_term=s.entering,
        graduation_term=s.graduating,
        max_credits=s.max_credits,
        term_caps={},
    )
    db.add(st)
    db.flush()
    plan = models.Plan(student_id=st.id, version=0)
    db.add(plan)
    db.flush()
    counter = iter(range(1000))
    with patch.object(initial, "new_id", lambda: f"{s.id[:6]}-slot{next(counter)}"):
        placements = seed_slots(s.placements(catalog), s.terms, s.current, program, catalog)
    services.commit(db, plan, placements, "import", "onboarding", parent=None)
    db.refresh(st)
    return st


FOLLOW_UPS = 2  # answers the stand-in student gives before the run is scored
TURN_TIMEOUT = 240  # seconds; a stalled stream counts as a failed run, not a hang


JUDGE = """You grade one reply from an academic advisor to a student. Answer only "yes" or \
"no". Does the reply tell the student that what they asked for can't be done as asked? \
Offering an alternative is fine. Going ahead with the change, or only asking a question \
without saying it can't be done, is "no"."""


async def says_it_cant(request_text: str, reply: str) -> bool:
    """Whether the reply turns the request down, judged by the model (the phrase list
    misses natural wordings like "Spring ’28 won't work"); the phrase list is the fallback."""
    if not reply.strip():
        return False
    try:
        client = openai.AsyncOpenAI()
        r = await client.responses.create(
            model=get_settings().advisor_model,
            instructions=JUDGE,
            input=f"Student asked: {request_text}\n\nAdvisor replied: {reply}",
            reasoning={"effort": "low"},
            store=False,
        )
        return r.output_text.strip().lower().startswith("yes")
    except openai.OpenAIError:
        return bool(IMPOSSIBLE.search(reply.strip()))


async def converse(db, st, text: str, convo: int | None = None) -> tuple[list, int | None]:
    events = []

    async def collect():
        nonlocal convo
        async for event in loop.run_turn(db, st, convo, text):
            events.append(event)
            convo = getattr(event, "conversation_id", convo)

    try:
        await asyncio.wait_for(collect(), TURN_TIMEOUT)
    except TimeoutError:
        events.append(
            SimpleNamespace(type="error", message=f"turn timed out after {TURN_TIMEOUT}s")
        )
    return events, convo


def met_request(after, before_by_id, request: RepairRequest, terms) -> list[str]:
    """What the final plan fails of the student's request (empty = all of it)."""
    misses = []
    load = {t: sum(p.credits for p in after if p.term == t) for t in terms}
    for term, cap in request.term_caps.items():
        if load[term] > cap and term not in request.lighter_terms:
            misses.append(f"{term} has {load[term]} > {cap}")
    by_id = {p.id: p for p in after}
    for pid, term in request.move.items():
        if by_id.get(pid) is None or by_id[pid].term != term:
            misses.append(f"{before_by_id[pid].course} not in {term}")
    for pid in request.remove:
        if pid in by_id and by_id[pid].course:
            misses.append(f"{before_by_id[pid].course} still in the plan")
    for w in request.add:
        here = [p for p in after if p.course == w.course]
        if not here or (w.term and here[0].term != w.term):
            misses.append(f"{w.course} not added" + (f" in {w.term}" if w.term else ""))
    for code in request.avoid_courses:
        if any(p.course == code for p in after):
            misses.append(f"{code} still in the plan")
    for pid in request.keep:
        if by_id.get(pid) is None or by_id[pid].term != before_by_id[pid].term:
            misses.append(f"{before_by_id[pid].course} moved")
    before_load = {t: sum(p.credits for p in before_by_id.values() if p.term == t) for t in terms}
    for term in request.lighter_terms:
        if load[term] >= before_load[term]:
            misses.append(f"{term} isn't lighter ({load[term]} vs {before_load[term]})")
    if request.graduate_by:
        last = terms.index(request.graduate_by)
        late = [p.course or p.slot_label for p in after if terms.index(p.term) > last]
        if late:
            misses.append(f"still planned after {request.graduate_by}: {', '.join(map(str, late))}")
    return misses


def broken_requirements(
    before, after, s: Scenario, program, catalog
) -> tuple[list[str], list[str]]:
    """Top-level requirements met before the change and not after it, judged by the exact
    assignment (CP-SAT) on requirements alone (prerequisites and caps are scored as
    blocking violations instead): (broken, ones the app's greedy audit would show as
    missing although they are still met)."""
    ok = ("done", "planned", "flagged")
    was = {r.id for r in audit(before, program, catalog).requirements if r.status in ok}
    units = [replace(u, prereqs=None) for u in build_units(after, catalog, program)]
    exact = PlanModel(
        units,
        s.terms,
        s.current,
        program,
        max_credits=99,
        options=Options(fixed=True, keep_met=frozenset(was), explain=True),
    ).solve()
    broken = sorted(k[1] for k in exact.core if k[0] == "met") if not exact.feasible else []
    greedy = {r.id for r in audit(after, program, catalog).requirements if r.status in ok}
    looks_missing = sorted((was - greedy) - set(broken))
    return broken, looks_missing


def count_changes(ops) -> dict:
    removed = len({op.placement_id for op in ops if isinstance(op, RemoveOp)})
    return {
        "moved": sum(isinstance(op, MoveOp) for op in ops),
        "added": sum(isinstance(op, AddOp) for op in ops),
        "removed": removed,
        "replaced": sum(op.op == "replace" for op in ops),
    }


async def run_one(s: Scenario, mode: str) -> dict:
    catalog = get_catalog()
    request = RepairRequest(**(s.request.constraints or {}))
    with SessionLocal() as db:
        st = make_student(db, s)
        plan_row = services.get_plan(db, st)
        before = services.current_placements(db, plan_row)
        before_by_id = {p.id: p for p in before}
        program = services.program_for(st)
        minimum = repair(
            before, s.terms, s.current, catalog, program, request, max_credits=s.max_credits
        )

        start = time.perf_counter()

        def proposals():
            q = select(models.Proposal).where(models.Proposal.plan_id == plan_row.id)
            return db.scalars(q.order_by(models.Proposal.id)).all()

        turn, convo = await converse(db, st, s.request.text)
        events = list(turn)
        questions: list[str] = []
        # a stand-in student: when the advisor stops to ask, pick its first option
        for _ in range(FOLLOW_UPS):
            asked = [e for e in turn if getattr(e, "type", "") == "question"]
            if not asked or proposals():
                break
            answer = asked[-1].options[0] if asked[-1].options else "Yes, go ahead."
            questions.append(f"{asked[-1].question} -> {answer}")
            turn, convo = await converse(db, st, answer, convo)
            events += turn
        every = proposals()
        # drafts the advisor withdrew (or the student discarded) aren't on screen any more
        latest = [p for p in every if p.status != "discarded"]
        seconds = time.perf_counter() - start

        rows = db.scalars(
            select(models.AgentEvent).where(models.AgentEvent.conversation_id == convo)
        ).all()
        tool_calls = [r.name for r in rows if r.kind == "tool"]
        text = "".join(getattr(e, "delta", "") for e in events if getattr(e, "type", "") == "text")
        errors = [e.message for e in events if getattr(e, "type", "") == "error"]

        row = {
            "scenario": s.id,
            "mode": mode,
            "expected": s.expected.outcome,
            "solver_status": minimum.status,
            "min_changes": minimum.moved + minimum.added + minimum.removed + minimum.replaced
            if minimum.status == "solved"
            else "",
            "proposals": len(latest),
            "withdrawn": len(every) - len(latest),
            "tool_calls": len(tool_calls),
            "tools": " ".join(tool_calls),
            "input_tokens": sum(r.input_tokens or 0 for r in rows if r.kind == "llm"),
            "output_tokens": sum(r.output_tokens or 0 for r in rows if r.kind == "llm"),
            "cached_tokens": sum(r.cache_read_tokens or 0 for r in rows if r.kind == "llm"),
            "seconds": round(seconds, 1),
            "says_impossible": await says_it_cant(s.request.text, text)
            if s.expected.outcome == "infeasible"
            else bool(IMPOSSIBLE.search(text.strip())),
            "jargon": " ".join(sorted({m.lower() for m in JARGON.findall(text)})),
            "errors": " | ".join(errors),
        }
        if latest:
            proposal = latest[-1]
            ops = parse_ops.validate_python(proposal.ops)
            try:
                after = apply_ops(before, ops, catalog, s.terms, origin="advisor")
            except OpError as e:
                row.update(error=str(e))
                after = None
            if after is not None:
                blocking = [
                    v.message
                    for v in validate(after, s.terms, catalog, s.max_credits)
                    if v.blocking
                ]
                misses = met_request(after, before_by_id, request, s.terms)
                broke, looks_missing = broken_requirements(before, after, s, program, catalog)
                changes = count_changes(ops)
                row.update(
                    blocking=len(blocking),
                    request_met=not misses,
                    misses="; ".join(misses),
                    broke_requirements=" ".join(broke),
                    audit_shows_missing=" ".join(looks_missing),
                    changes=sum(changes.values()),
                    **changes,
                    ops=json.dumps(proposal.ops),
                )
        # a correct answer: a valid plan that does what was asked without breaking a
        # requirement that was met, or, for an impossible request, no plan that claims to
        # and a reply that says so
        if s.expected.outcome == "infeasible":
            row["correct"] = row["says_impossible"] and not row.get("request_met")
        else:
            row["correct"] = (
                row.get("blocking") == 0
                and bool(row.get("request_met"))
                and not row.get("broke_requirements")
            )
        row["questions"] = " || ".join(questions)
        row["reply"] = " ".join(text.split())[:600]
        return row


async def run_all(
    modes: list[str], scenarios: list[Scenario], progress: Path, repeats: int = 1, first: int = 1
) -> list[dict]:
    """One event loop for the whole run, so the OpenAI client isn't torn down between
    conversations. Repeats go round all modes in turn, so a slow or flaky stretch of the
    API hits both modes alike."""
    with_repair = prompts.SYSTEM
    repair_tool = tools.REGISTRY["repair_plan"]
    rows = []
    for rep in range(first - 1, first - 1 + repeats):
        for mode in modes:
            if mode == "llm_direct":
                tools.REGISTRY.pop("repair_plan", None)
                loop.SYSTEM = prompt_without_repair(with_repair)
            else:
                tools.REGISTRY["repair_plan"] = repair_tool
                loop.SYSTEM = with_repair
            for s in scenarios:
                print(f"running {s.id} · {mode} · repeat {rep + 1}", flush=True)
                row = {"repeat": rep + 1, **await run_one(s, mode)}
                rows.append(row)
                with progress.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                print(json.dumps({k: v for k, v in row.items() if k != "reply"}), flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", nargs="+", default=["llm_direct", "advisor_repair"])
    parser.add_argument("--scenarios", type=Path, default=ROOT / "advisor_scenarios.yaml")
    parser.add_argument("--only", help="run scenarios whose id contains this")
    parser.add_argument("--limit", type=int, help="run only the first N scenarios")
    parser.add_argument("--ids", nargs="+", help="run only these scenario ids")
    parser.add_argument("--repeats", type=int, default=1, help="run everything N times")
    # to finish an interrupted run: number these repeats from N, then merge the files
    parser.add_argument("--first-repeat", type=int, default=1)
    args = parser.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("set OPENAI_API_KEY")

    Base.metadata.create_all(engine)
    scenarios = [s for s in load_scenarios(args.scenarios) if not args.only or args.only in s.id]
    scenarios = scenarios[: args.limit] if args.limit else scenarios
    if args.ids:
        scenarios = [s for s in scenarios if s.id in args.ids]
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    # every row is saved as it finishes, so a crash late in a paid run loses nothing
    progress = out_dir / f"{stamp}-advisor.jsonl"
    rows = asyncio.run(run_all(args.modes, scenarios, progress, args.repeats, args.first_repeat))

    out = out_dir / f"{stamp}-advisor.csv"
    columns = list(dict.fromkeys(k for row in rows for k in row))
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(summarize(rows))
    print(f"wrote {out.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
