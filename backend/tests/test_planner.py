import pytest

from app.catalog.prereq_parse import parse
from app.catalog.store import Catalog
from app.planner.audit import audit, matches_filter
from app.planner.eligible import list_eligible
from app.planner.ops import OpError, apply_ops
from app.planner.validate import validate
from app.requirements.loader import get_program
from app.schemas.courses import AllOf, AnyOf, CourseReq, Flag
from app.schemas.plans import AddOp, LockOp, MoveOp, Placement, RemoveOp, ReplaceOp
from app.schemas.requirements import CourseFilter

TERMS = ["FA24", "SP25", "FA25", "SP26", "FA26", "SP27"]


def place(code, term, credits=4, status="planned", pid=None):
    return Placement(id=pid or code, term=term, course=code, credits=credits, status=status)


def test_parse_or_with_bare_number():
    assert parse("CS 2110 or 2112.") == AnyOf(
        items=[CourseReq(code="CS 2110"), CourseReq(code="CS 2112")]
    )


def test_parse_semicolon_or():
    expr = parse("CS 2800 and CS 3110; or CS 2110 and CS 2800.")
    assert isinstance(expr, AnyOf)
    assert isinstance(expr.items[0], AllOf)


def test_parse_permission_is_a_flag():
    assert parse("Permission of instructor.") == Flag(text="Permission of instructor")


def codes(*cs):
    return [CourseReq(code=c) for c in cs]


def test_parse_example_list_is_one_of():
    # CS 4780's real text: each "(e.g. ...)" names options for one requirement
    expr = parse(
        "Prerequisite: CS 2800, probability theory (e.g. BTRY 3080, ECON 3130, MATH 4710, "
        "ENGRD 2700) and linear algebra (e.g. MATH 2940), calculus (e.g. MATH 1920) and "
        "programming proficiency (e.g. CS 2110)."
    )
    probability = AnyOf(items=codes("BTRY 3080", "ECON 3130", "MATH 4710", "ENGRD 2700"))
    assert expr == AllOf(
        items=[CourseReq(code="CS 2800"), probability, *codes("MATH 2940", "MATH 1920", "CS 2110")]
    )


def test_parse_oxford_comma_list_is_one_of():
    expr = parse("CS 4670, CS 4700, CS 4740, or CS 4780.")
    assert expr == AnyOf(items=codes("CS 4670", "CS 4700", "CS 4740", "CS 4780"))


def test_parse_plain_commas_still_mean_and():
    expr = parse("CS 2800, MATH 1910, MATH 2210 or MATH 2940.")
    assert expr == AllOf(
        items=[*codes("CS 2800", "MATH 1910"), AnyOf(items=codes("MATH 2210", "MATH 2940"))]
    )


def test_parse_semicolon_parts_are_and_until_or():
    expr = parse("CS 2110; CS 3410; or permission of instructor.")
    assert expr == AnyOf(
        items=[AllOf(items=codes("CS 2110", "CS 3410")), Flag(text="permission of instructor")]
    )


def test_parse_slash_and_bare_numbers():
    assert parse("CS 4320/5320.") == AnyOf(items=codes("CS 4320", "CS 5320"))
    assert parse("PHYS 2218 and 2210.") == AllOf(items=codes("PHYS 2218", "PHYS 2210"))


def test_parse_ignores_recommended():
    assert parse("CS 2110. Recommended prerequisite: CS 3110.") == CourseReq(code="CS 2110")
    assert parse("Recommended prerequisite: CS 3110.") is None


def test_prereq_order(catalog):
    plan = [
        place("CS 1110", "FA24", status="completed"),
        place("CS 2110", "FA24", status="completed"),
    ]
    ok = plan + [place("CS 2800", "SP25", status="completed"), place("CS 3110", "FA25")]
    assert not [v for v in validate(ok, TERMS, catalog) if v.kind == "prereq"]

    bad = plan + [place("CS 3110", "SP25"), place("CS 2800", "FA25")]
    errors = [v for v in validate(bad, TERMS, catalog) if v.kind == "prereq"]
    assert len(errors) == 1 and "CS 2800" in errors[0].message


def test_prereq_equivalents(catalog):
    # CS 2800 asks for "MATH 1110 or equivalent"; Engineering students take MATH 1910
    cs2800 = catalog.get("CS 2800").model_copy(
        update={"prereqs": AllOf(items=[CourseReq(code="MATH 1110"), CourseReq(code="CS 1110")])}
    )
    courses = [c for c in catalog.courses.values() if c.code != "CS 2800"] + [cs2800]
    plan = [
        place("MATH 1910", "FA24", status="completed"),
        place("CS 1110", "FA24", status="completed"),
        place("CS 2800", "SP25"),
    ]
    strict = Catalog(courses)
    assert [v for v in validate(plan, TERMS, strict) if v.kind == "prereq"]

    lenient = Catalog(courses, {"MATH 1910": ["MATH 1110"]})
    assert not [v for v in validate(plan, TERMS, lenient) if v.kind == "prereq"]
    # one-directional, and degree requirements / duplicate checks don't see it
    assert "MATH 1910" not in lenient.prereq_credit("MATH 1110")
    assert lenient.equivalents("MATH 1910") == {"MATH 1910"}


def test_credit_cap(catalog):
    plan = [place(c, "FA26") for c in ["CS 1110", "CS 2800", "MATH 1910", "CS 4740", "CS 2110"]]
    kinds = {v.kind for v in validate(plan, TERMS, catalog, max_credits=18)}
    assert "credits_high" in kinds


def test_offering_warning(catalog):
    plan = [
        place("CS 1110", "FA24", status="completed"),
        place("CS 2110", "SP25", status="completed"),
    ]
    plan.append(place("CS 4780", "SP27"))
    offering = [v for v in validate(plan, TERMS, catalog) if v.kind == "offering"]
    assert offering and not offering[0].blocking


def test_audit_counts_courses(catalog):
    program = get_program("cs-eng", "2024-25")
    plan = [
        place("CS 1110", "FA24", status="completed"),
        place("CS 2110", "SP25", status="completed"),
        place("ECON 1110", "FA25", 3, "completed"),
        place("GOVT 1111", "SP26", 3),
    ]
    result = audit(plan, program, catalog)
    by_id = {r.id: r for r in result.requirements}
    assert by_id["intro"].status == "done"
    assert by_id["ls"].status == "planned"
    assert by_id["core"].status == "missing"
    assert not result.complete


def test_audit_separates_open_slots_from_courses(catalog):
    program = get_program("cs-eng", "2024-25")
    plan = [
        place("ECON 1110", "FA25", 3, "completed"),
        Placement(id="slot1", term="SP27", slot="ls", slot_label="Liberal studies", credits=3),
    ]
    by_id = {r.id: r for r in audit(plan, program, catalog).requirements}
    assert by_id["ls"].status == "planned"
    assert by_id["ls"].filled == ["slot1", "ECON 1110"]
    assert by_id["ls"].open_slots == 1


def test_title_prefix_filter(catalog):
    fws = catalog.get("GOVT 1111").model_copy(update={"title": "FWS: Politics and Writing"})
    assert matches_filter(fws, CourseFilter(title_prefix="FWS:"))
    assert not matches_filter(catalog.get("GOVT 1111"), CourseFilter(title_prefix="FWS:"))


def test_move_op(catalog):
    plan = [place("CS 4740", "FA26", pid="a")]
    moved = apply_ops(plan, [MoveOp(placement_id="a", term="SP27")], catalog, TERMS)
    assert moved[0].term == "SP27" and plan[0].term == "FA26"


def test_locked_placement_cannot_move(catalog):
    plan = [place("CS 4740", "FA26", pid="a")]
    locked = apply_ops(plan, [LockOp(placement_id="a")], catalog, TERMS)
    assert locked[0].locked and not plan[0].locked
    with pytest.raises(OpError, match="kept in Fall ’26"):
        apply_ops(locked, [MoveOp(placement_id="a", term="SP27")], catalog, TERMS)
    unlock = LockOp(placement_id="a", locked=False)
    moved = apply_ops(locked, [unlock, MoveOp(placement_id="a", term="SP27")], catalog, TERMS)
    assert moved[0].term == "SP27"


def test_term_cap_overrides_default(catalog):
    plan = [place(c, "FA26") for c in ["CS 1110", "CS 2800", "MATH 1910", "CS 4740"]]
    assert not [v for v in validate(plan, TERMS, catalog) if v.kind == "credits_high"]
    capped = validate(plan, TERMS, catalog, term_caps={"FA26": 15})
    high = [v.message for v in capped if v.kind == "credits_high"]
    assert high == ["Fall ’26 has 16 credits, over your 15-credit cap for that term"]


def test_ops_stay_inside_plan_terms(catalog):
    plan = [place("CS 4740", "FA26", pid="a")]
    with pytest.raises(OpError, match="Fall ’27 isn't in your plan"):
        apply_ops(plan, [MoveOp(placement_id="a", term="FA27")], catalog, TERMS)
    with pytest.raises(OpError, match="isn't in your plan"):
        apply_ops(plan, [AddOp(term="SP28", course="CS 3110")], catalog, TERMS)


def test_eligible_tolerates_placements_outside_terms(catalog):
    program = get_program("cs-eng", "2024-25")
    ls = next(r for r in program.all_requirements() if r.id == "ls")
    plan = [place("CS 1110", "FA24", status="completed"), place("CS 4740", "SP29")]
    assert list_eligible(ls, "SP27", plan, catalog)


def test_replace_only_planned_placements(catalog):
    plan = [
        place("CS 1110", "FA24", status="completed", pid="done"),
        place("CS 2110", "FA26", status="in_progress", pid="now"),
        Placement(id="slot", term="SP27", slot="ls", credits=3),
    ]
    for pid, word in [("done", "already completed"), ("now", "in progress")]:
        with pytest.raises(OpError, match=word):
            apply_ops(plan, [ReplaceOp(placement_id=pid, course="CS 1112")], catalog, TERMS)
    filled = apply_ops(plan, [ReplaceOp(placement_id="slot", course="GOVT 1111")], catalog, TERMS)
    assert filled[2].course == "GOVT 1111" and filled[2].slot == "ls"


def test_advisor_respects_locks(catalog):
    plan = [place("CS 4740", "FA26", pid="a").model_copy(update={"locked": True})]
    for op in [
        RemoveOp(placement_id="a"),
        MoveOp(placement_id="a", term="SP27"),
        ReplaceOp(placement_id="a", course="CS 4780"),
    ]:
        with pytest.raises(OpError, match="locked in Fall ’26 by the student"):
            apply_ops(plan, [op], catalog, TERMS, origin="advisor")
    with pytest.raises(OpError, match="Only the student"):
        apply_ops(plan, [LockOp(placement_id="a", locked=False)], catalog, TERMS, "advisor")
    # the student can still remove or swap a locked course; only moving it is blocked
    assert apply_ops(plan, [RemoveOp(placement_id="a")], catalog, TERMS) == []
    swapped = apply_ops(plan, [ReplaceOp(placement_id="a", course="CS 4780")], catalog, TERMS)
    assert swapped[0].course == "CS 4780"
