"""Global repair and the rebuild baseline on a small catalog where every answer can be
checked by hand (and one by brute force)."""

from itertools import product

import pytest

from app.catalog.store import Catalog
from app.planner.ops import apply_ops
from app.planner.solver.repair import RequestError, rebuild, repair
from app.planner.solver.types import AddWish, RepairRequest
from app.planner.validate import validate
from app.schemas.courses import Course, CourseReq
from app.schemas.plans import Placement
from app.schemas.requirements import CourseFilter, Program, Requirement, RequirementSet

TERMS = ["FA25", "SP26", "FA26", "SP27", "FA27", "SP28"]
NOW = "FA25"


def course(code, credits=4, prereq=None, seasons=("FA", "SP")):
    subject, number = code.split()
    return Course(
        code=code,
        subject=subject,
        number=number,
        title=code,
        credits_min=credits,
        credits_max=credits,
        terms_offered=["FA24", "SP25"],
        typical_seasons=list(seasons),
        prereqs=CourseReq(code=prereq) if prereq else None,
    )


CATALOG = Catalog(
    [
        course("CS 1100"),
        course("CS 2100", prereq="CS 1100"),
        course("CS 3100", prereq="CS 2100"),
        course("CS 3200", seasons=("FA",)),
        course("CS 4410", prereq="CS 2100"),
        course("CS 4414", prereq="CS 2100"),
        course("ECON 3000", 3),
        course("ECON 3100", 3),
        course("PSYCH 1000", 3),
    ]
)

PROGRAM = Program(
    id="t",
    label="t",
    college="t",
    catalog_year="2024-25",
    sets=[
        RequirementSet(
            id="t",
            label="t",
            catalog_year="2024-25",
            source_url="x",
            requirements=[
                Requirement(
                    id="core",
                    label="Core",
                    kind="courses",
                    courses=["CS 1100", "CS 2100", "CS 3100"],
                ),
                Requirement(
                    id="os",
                    label="Systems",
                    kind="courses",
                    courses=["CS 4410", "CS 4414"],
                    count=1,
                ),
                Requirement(
                    id="econ",
                    label="Economics",
                    kind="filter",
                    filter=CourseFilter(subjects=["ECON"]),
                    count=2,
                ),
            ],
        )
    ],
)


def place(code, term, pid=None, **kw):
    i, now = TERMS.index(term), TERMS.index(NOW)
    status = "completed" if i < now else "in_progress" if i == now else "planned"
    c = CATALOG.get(code)
    return Placement(id=pid or code, term=term, course=code, credits=c.credits, status=status, **kw)


def slot(rid, term, pid):
    return Placement(id=pid, term=term, slot=rid, slot_label=rid, credits=3)


def plan():
    return [
        place("CS 1100", "FA25"),
        place("CS 2100", "SP26"),
        place("CS 3100", "FA26"),
        place("CS 4410", "SP27"),
        slot("econ", "SP26", "e1"),
        slot("econ", "FA26", "e2"),
    ]


def run(placements, request=None, **kw):
    kw.setdefault("max_credits", 18)
    return repair(placements, TERMS, NOW, CATALOG, PROGRAM, request, **kw)


def applied(placements, result, caps=None, max_credits=18):
    after = apply_ops(placements, result.ops, CATALOG, TERMS)
    blocking = [v for v in validate(after, TERMS, CATALOG, max_credits, caps) if v.blocking]
    return after, blocking


def test_a_valid_plan_needs_no_change():
    r = run(plan())
    assert r.status == "solved" and r.ops == [] and r.optimal


def test_a_tighter_cap_moves_as_little_as_possible():
    request = RepairRequest(term_caps={"SP26": 4})  # SP26 holds 7 credits
    r = run(plan(), request)
    assert r.status == "solved" and r.optimal
    assert (r.moved, r.added, r.removed) == (1, 0, 0)
    after, blocking = applied(plan(), r, {"SP26": 4})
    assert blocking == [] and r.blocking == 0
    assert sum(p.credits for p in after if p.term == "SP26") <= 4

    baseline = rebuild(plan(), TERMS, NOW, CATALOG, PROGRAM, request, max_credits=18)
    assert baseline.status == "solved" and baseline.blocking == 0
    assert baseline.moved >= r.moved


def test_prerequisites_out_of_order_get_fixed():
    broken = plan()
    broken[2] = place("CS 3100", "SP26")  # needs CS 2100, which is also in SP26
    r = run(broken)
    assert r.status == "solved" and r.moved == 1
    assert applied(broken, r)[1] == []


def test_an_off_season_course_moves_to_a_season_it_runs():
    p = plan() + [place("CS 3200", "SP27")]  # fall only
    r = run(p)
    assert [(op.placement_id, op.term) for op in r.ops] in (
        [("CS 3200", "FA26")],
        [("CS 3200", "FA27")],
    )


def test_dropping_a_course_brings_in_the_other_named_option():
    r = run(plan(), RepairRequest(remove=["CS 4410"]))
    assert r.status == "solved" and (r.removed, r.added) == (1, 1)
    after, blocking = applied(plan(), r)
    assert blocking == [] and "CS 4414" in {p.course for p in after}
    assert "CS 4410" not in {p.course for p in after}  # not dropped and re-added


def test_courses_stay_unless_the_request_allows_dropping_them():
    p = plan() + [place("PSYCH 1000", "SP27")]
    # 7 + 7 + 4 + 0 credits of room for 21 credits of courses and slots
    tight = RepairRequest(
        graduate_by="FA27", term_caps={"SP26": 7, "FA26": 7, "SP27": 4, "FA27": 0}
    )
    r = run(p, tight)
    assert r.status == "infeasible"
    assert any("Graduate by Fall ’27" == c for c in r.conflicts)

    r = run(p, tight.model_copy(update={"allow_removing_courses": True}))
    assert r.status == "solved" and r.removed == 1 and r.blocking == 0
    assert "PSYCH 1000" not in {q.course for q in applied(p, r)[0]}


def test_an_impossible_request_names_what_clashes():
    r = run(plan(), RepairRequest(term_caps={"SP26": 0, "FA26": 0, "SP27": 0}, keep=["CS 3100"]))
    assert r.status == "infeasible" and r.ops == []
    assert "At most 0 credits in Fall ’26 (your request)" in r.conflicts
    assert "Keep CS 3100 in Fall ’26" in r.conflicts
    # caps that aren't part of the clash are left out
    assert "At most 0 credits in Spring ’26 (your request)" not in r.conflicts


def test_keep_add_and_avoid():
    request = RepairRequest(
        term_caps={"FA26": 4},
        keep=["CS 3100"],
        add=[AddWish(course="ECON 3100", term="SP28")],
        avoid_courses=["CS 4410"],
    )
    r = run(plan(), request)
    assert r.status == "solved" and r.blocking == 0
    after = {p.course or p.id: p.term for p in applied(plan(), r)[0]}
    assert after["CS 3100"] == "FA26" and after["ECON 3100"] == "SP28"
    assert "CS 4410" not in after and "CS 4414" in after  # avoided, so the other option


def test_requests_naming_unknown_things_are_rejected():
    with pytest.raises(RequestError):
        run(plan(), RepairRequest(keep=["nope"]))
    with pytest.raises(RequestError):
        run(plan(), RepairRequest(add=[AddWish(course="CS 9999")]))
    with pytest.raises(RequestError):
        run(plan(), RepairRequest(term_caps={"SP30": 12}))


def test_the_move_count_is_minimal_by_brute_force():
    """Every way to place the movable courses; the fewest moves of any valid one."""
    p = [
        place("CS 1100", "FA25"),
        place("CS 2100", "SP26"),
        place("CS 3100", "SP26"),  # out of order
        place("CS 4410", "SP26"),  # out of order too
        place("ECON 3000", "SP26"),
        place("ECON 3100", "SP26"),
    ]
    caps = {"SP26": 7, "FA26": 8}
    r = run(p, RepairRequest(term_caps=caps))
    assert r.status == "solved" and r.optimal

    movable = [q for q in p if q.status == "planned"]
    future = TERMS[TERMS.index(NOW) + 1 :]
    best = None
    for terms in product(future, repeat=len(movable)):
        trial = [
            q if q.status != "planned" else q.model_copy(update={"term": terms[movable.index(q)]})
            for q in p
        ]
        if any(v.blocking for v in validate(trial, TERMS, CATALOG, 18, caps)):
            continue
        moves = sum(t != q.term for t, q in zip(terms, movable, strict=True))
        best = moves if best is None else min(best, moves)
    assert r.moved == best


def test_moving_a_course_to_a_term_makes_room_there():
    request = RepairRequest(move={"CS 4410": "FA26"}, term_caps={"FA26": 8})  # FA26: CS 3100 + slot
    r = run(plan(), request)
    assert r.status == "solved" and r.blocking == 0
    after = applied(plan(), r, {"FA26": 8})[0]
    assert next(p.term for p in after if p.id == "CS 4410") == "FA26"
    assert sum(p.credits for p in after if p.term == "FA26") <= 8
    assert r.moved == 2  # CS 4410 in, one of the others out


def test_conflicts_say_why_a_course_cant_go_there():
    # fall only
    r = run(plan(), RepairRequest(add=[AddWish(course="CS 3200", term="SP27")]))
    assert r.conflicts == ["Add CS 3200 in Spring ’27, but it has only run in fall"]
    # CS 3100 needs CS 2100, which is in Spring ’26
    r = run(plan(), RepairRequest(move={"CS 3100": "SP26"}))
    assert r.conflicts == ["Put CS 3100 in Spring ’26, but it needs CS 2100 first"]
    # dropping CS 2100 strands the courses that need it
    r = run(plan(), RepairRequest(remove=["CS 2100"]))
    assert r.status == "infeasible" and "Drop CS 2100" in r.conflicts
    # CS 3100 and CS 4410 both need it; either one is enough to explain the clash
    assert any(c.endswith("in your plan; it needs CS 2100") for c in r.conflicts)


def test_a_requested_course_fills_a_matching_open_slot():
    r = run(plan(), RepairRequest(add=[AddWish(course="ECON 3000", term="FA26")]))
    assert r.status == "solved" and r.blocking == 0
    assert (r.replaced, r.added, r.removed, r.moved) == (1, 0, 0, 0)
    assert [op.model_dump(exclude_none=True) for op in r.ops] == [
        {"op": "replace", "placement_id": "e2", "course": "ECON 3000"}
    ]


def test_impossible_requests_come_with_checked_alternatives():
    r = run(plan(), RepairRequest(add=[AddWish(course="CS 3200", term="SP27")]))  # fall only
    assert r.alternatives == ["CS 3200 could go in Fall ’26 or Fall ’27 instead"]

    r = run(plan(), RepairRequest(move={"CS 3100": "SP26"}))  # needs CS 2100 first
    assert r.alternatives and r.alternatives[0].startswith(
        "CS 3100 could go in Fall ’26 (where it is now)"
    )

    # the lowest cap that works: SP26 holds CS 2100 (4) and an econ slot (3)
    r = run(
        plan(), RepairRequest(term_caps={"SP26": 0, "FA26": 4, "SP27": 4, "FA27": 4, "SP28": 4})
    )
    assert r.status == "infeasible" and any("can go down to" in a for a in r.alternatives)

    # a solved request doesn't search for alternatives
    assert run(plan()).alternatives == []


def five_slots():
    # Fall ’26 holds 15 credits of open slots
    return [slot("econ", "FA26", f"e{i}") for i in range(5)]


def test_lighter_takes_a_course_out_but_stays_full_time():
    r = run(five_slots(), RepairRequest(lighter_terms=["FA26"]))
    assert r.status == "solved" and r.moved == 1  # 15 → 12, not lower
    assert "Fall ’26: 15 → 12 credits" in r.term_loads
    after, _ = applied(five_slots(), r)
    assert sum(p.credits for p in after if p.term == "FA26") == 12


def test_a_term_at_12_cant_be_made_lighter_without_saying_so():
    plan = five_slots()[:4]  # 12 credits
    r = run(plan, RepairRequest(lighter_terms=["FA26"]))
    assert r.status == "infeasible"
    assert "Keep Fall ’26 at 12 credits or more (the full-time minimum)" in r.conflicts
    # a cap the student names below 12 is their call
    r = run(plan, RepairRequest(term_caps={"FA26": 9}))
    assert r.status == "solved"
