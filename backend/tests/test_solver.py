import random

from app.catalog.store import Catalog
from app.planner.audit import audit, greedy_audit
from app.planner.solver import Options, PlanModel, build_units, check_plan
from app.planner.validate import validate
from app.requirements.loader import get_program
from app.schemas.courses import CourseReq
from app.schemas.plans import Placement
from app.schemas.requirements import CourseFilter, Program, Requirement, RequirementSet

TERMS = ["FA24", "SP25", "FA25", "SP26", "FA26", "SP27", "FA27", "SP28"]
NOW = "FA26"


def place(code, term, status=None, credits=4, pid=None):
    if status is None:
        i, now = TERMS.index(term), TERMS.index(NOW)
        status = "completed" if i < now else "in_progress" if i == now else "planned"
    return Placement(id=pid or code, term=term, course=code, credits=credits, status=status)


def blocked(plan, catalog, max_credits=18):
    return any(v.blocking for v in validate(plan, TERMS, catalog, max_credits))


def test_check_mode_agrees_with_validate_on_random_plans(catalog):
    """The model and the validator must agree on every plan, including broken ones."""
    program = get_program("cs-eng", "2024-25")
    codes = sorted(catalog.courses)
    rng = random.Random(7)
    disagreements = []
    for trial in range(300):
        plan = [
            place(code, rng.choice(TERMS), pid=f"{code}-{i}")
            for i, code in enumerate(rng.sample(codes, rng.randint(1, len(codes))))
        ]
        if rng.random() < 0.2:  # a duplicate now and then
            plan.append(place(plan[0].course, rng.choice(TERMS), pid="dup"))
        cap = rng.choice([8, 12, 18])
        model_ok = check_plan(plan, TERMS, NOW, catalog, program, max_credits=cap).feasible
        if model_ok == blocked(plan, catalog, cap):
            disagreements.append((trial, [(p.course, p.term) for p in plan], cap))
    assert not disagreements, disagreements[:3]


def test_check_mode_catches_each_blocking_rule(catalog):
    program = get_program("cs-eng", "2024-25")
    ok = [place("CS 1110", "FA24"), place("CS 2110", "SP25"), place("CS 2800", "SP25")]
    assert check_plan(ok, TERMS, NOW, catalog, program).feasible

    out_of_order = [place("CS 1110", "FA24"), place("CS 2110", "SP27"), place("CS 4780", "FA26")]
    assert not check_plan(out_of_order, TERMS, NOW, catalog, program).feasible

    heavy = [
        place(c, "SP27") for c in ["CS 1110", "MATH 1910", "ECON 1110", "GOVT 1111", "PSYCH 1101"]
    ]
    assert not check_plan(heavy, TERMS, NOW, catalog, program, max_credits=18).feasible
    assert check_plan(heavy, TERMS, NOW, catalog, program, max_credits=20).feasible
    capped = check_plan(heavy, TERMS, NOW, catalog, program, max_credits=20, term_caps={"SP27": 16})
    assert not capped.feasible

    twice = [place("CS 1110", "FA24"), place("CS 1110", "SP27", pid="again")]
    assert not check_plan(twice, TERMS, NOW, catalog, program).feasible


def test_corequisites_may_share_a_term(catalog):
    cs3110 = catalog.get("CS 3110").model_copy(
        update={"prereqs": CourseReq(code="CS 2800", concurrent=True)}
    )
    cs2800 = catalog.get("CS 2800").model_copy(update={"prereqs": None})
    swapped = {"CS 2800", "CS 3110"}
    local = Catalog(
        [c for c in catalog.courses.values() if c.code not in swapped] + [cs2800, cs3110]
    )
    program = get_program("cs-eng", "2024-25")
    together = [place("CS 2800", "SP27"), place("CS 3110", "SP27")]
    assert not blocked(together, local)
    assert check_plan(together, TERMS, NOW, local, program).feasible
    late = [place("CS 2800", "FA27"), place("CS 3110", "SP27")]
    assert blocked(late, local)
    assert not check_plan(late, TERMS, NOW, local, program).feasible


def test_free_mode_reorders_planned_courses_within_caps(catalog):
    program = get_program("cs-eng", "2024-25")
    plan = [
        place("CS 1110", "FA24"),
        place("CS 2800", "SP25"),
        place("CS 3110", "SP27"),  # needs CS 2110, planned after it
        place("CS 2110", "FA27"),
        place("CS 4820", "FA27"),  # needs CS 3110
    ]
    units = build_units(plan, catalog, program)
    model = PlanModel(units, TERMS, NOW, program, max_credits=4, options=Options(fixed=False))
    result = model.solve()
    assert result.feasible
    order = {code: TERMS.index(result.terms[code]) for code in ["CS 2110", "CS 3110", "CS 4820"]}
    assert order["CS 2110"] < order["CS 3110"] < order["CS 4820"]
    # a 4-credit cap means one course per term
    future = [result.terms[c] for c in ["CS 2110", "CS 3110", "CS 4820"]]
    assert len(set(future)) == 3


def test_exact_assignment_beats_the_greedy_audit(catalog):
    # listed first, the broader rule grabs ECON 1110 in the greedy audit and the
    # narrower one goes unmet; the exact assignment satisfies both
    broad = Requirement(
        id="social",
        label="Social",
        kind="filter",
        filter=CourseFilter(attributes_any=["SSC-AS", "SBA-AG"]),
        count=1,
    )
    narrow = Requirement(
        id="econ",
        label="Econ",
        kind="filter",
        filter=CourseFilter(attributes_any=["SSC-AS"]),
        count=1,
    )
    rules = RequirementSet(
        id="t", label="t", catalog_year="2024-25", source_url="x", requirements=[broad, narrow]
    )
    program = Program(id="t", label="t", college="t", catalog_year="2024-25", sets=[rules])
    psych = catalog.get("PSYCH 1101").model_copy(update={"attributes": ["SBA-AG"]})
    local = Catalog([c for c in catalog.courses.values() if c.code != "PSYCH 1101"] + [psych])
    plan = [place("ECON 1110", "FA25", credits=3), place("PSYCH 1101", "SP26", credits=3)]

    greedy = {r.id: r.status for r in greedy_audit(plan, program, local).requirements}
    assert greedy == {"social": "done", "econ": "missing"}
    # the app's audit is the exact one now
    assert {r.id: r.status for r in audit(plan, program, local).requirements} == {
        "social": "done",
        "econ": "done",
    }

    exact = check_plan(plan, TERMS, NOW, local, program, requirements="maximize")
    assert exact.satisfied >= {"social", "econ"}
    assert exact.assigned == {"econ": ["ECON 1110"], "social": ["PSYCH 1101"]}

    assert check_plan(plan, TERMS, NOW, local, program, requirements="require").feasible
    assert not check_plan(plan[:1], TERMS, NOW, local, program, requirements="require").feasible
