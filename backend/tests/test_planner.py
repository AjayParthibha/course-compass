from app.catalog.prereq_parse import parse
from app.planner.audit import audit
from app.planner.ops import apply_ops
from app.planner.validate import validate
from app.requirements.loader import get_program
from app.schemas.courses import AllOf, AnyOf, CourseReq, Flag
from app.schemas.plans import MoveOp, Placement

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


def test_move_op(catalog):
    plan = [place("CS 4740", "FA26", pid="a")]
    moved = apply_ops(plan, [MoveOp(placement_id="a", term="SP27")], catalog)
    assert moved[0].term == "SP27" and plan[0].term == "FA26"
