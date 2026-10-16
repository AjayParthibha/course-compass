"""The external specialization: three courses from one subject, at most one cross-listed
with CS, no independent study."""

from app.catalog.store import Catalog
from app.planner.audit import audit
from app.planner.eligible import courses_by_subject, listed_under
from app.planner.solver import check_plan
from app.schemas.courses import Course, CourseReq
from app.schemas.plans import Placement
from app.schemas.requirements import CourseFilter, Program, Requirement, RequirementSet

TERMS = ["FA25", "SP26", "FA26", "SP27", "FA27"]


def course(code, title="A course", cross=(), seasons=("FA", "SP"), prereqs=None):
    subject, number = code.split()
    return Course(
        code=code,
        subject=subject,
        number=number,
        title=title,
        credits_min=3,
        credits_max=3,
        cross_listed=list(cross),
        terms_offered=["FA25", "SP26"],
        typical_seasons=list(seasons),
        prereqs=prereqs,
    )


CATALOG = Catalog(
    [
        course("ORIE 3300", "Optimization I"),
        course("ORIE 3310", "Optimization II", prereqs=CourseReq(code="ORIE 3300")),
        course("ORIE 4580", "Simulation", seasons=("FA",)),
        course("ORIE 4741", "Big Messy Data", cross=["CS 4741"]),
        course("ORIE 4742", "Another CS listing", cross=["CS 4742"]),
        course("ORIE 4999", "Independent Study in ORIE"),
        course("CEE 4520", "Systems Analysis", cross=["ORIE 4520"]),
        course("ORIE 4520", "Systems Analysis", cross=["CEE 4520"]),
        course("ECON 3030", "Intermediate Micro"),
        course("ECON 3110", "Probability and Statistics"),
        course("CS 4741", "Big Messy Data", cross=["ORIE 4741"]),
    ]
)

EXT = Requirement(
    id="ext",
    label="External specialization",
    kind="filter",
    filter=CourseFilter(
        min_level=3000, exclude_subjects=["CS"], exclude_titles=["Independent Study"]
    ),
    count=3,
    same_subject=True,
    max_cross_listed={"CS": 1},
)
PROGRAM = Program(
    id="t",
    label="t",
    college="t",
    catalog_year="2024-25",
    sets=[
        RequirementSet(
            id="t", label="t", catalog_year="2024-25", source_url="x", requirements=[EXT]
        )
    ],
)


def place(code, term, status="planned"):
    return Placement(id=code, term=term, course=code, credits=3, status=status)


def status(plan):
    return audit(plan, PROGRAM, CATALOG).requirements[0]


def test_three_from_one_subject_count():
    plan = [
        place("ORIE 3300", "FA25", "completed"),
        place("ORIE 3310", "SP27"),
        place("ORIE 4580", "FA27"),
    ]
    assert status(plan).status == "planned"
    assert check_plan(plan, TERMS, "FA26", CATALOG, PROGRAM, requirements="require").feasible


def test_a_mix_of_subjects_does_not_count():
    plan = [
        place("ORIE 3300", "FA25", "completed"),
        place("ECON 3030", "SP27"),
        place("ECON 3110", "FA27"),
    ]
    st = status(plan)
    # the audit keeps the bigger group (ECON) and leaves ORIE out
    assert st.status == "missing" and st.filled == ["ECON 3030", "ECON 3110"]
    assert not check_plan(plan, TERMS, "FA26", CATALOG, PROGRAM, requirements="require").feasible


def test_only_one_course_cross_listed_with_cs_counts():
    plan = [
        place("ORIE 3300", "FA25", "completed"),
        place("ORIE 4741", "SP27"),
        place("ORIE 4742", "FA27"),
    ]
    assert status(plan).filled == ["ORIE 3300", "ORIE 4741"]
    assert not check_plan(plan, TERMS, "FA26", CATALOG, PROGRAM, requirements="require").feasible
    plan[2] = place("ORIE 4580", "FA27")
    assert status(plan).status == "planned"


def test_independent_study_is_left_out():
    plan = [
        place("ORIE 3300", "FA25", "completed"),
        place("ORIE 3310", "SP27"),
        place("ORIE 4999", "FA27"),
    ]
    assert status(plan).status == "missing"


def test_open_slots_fit_whichever_subject_is_chosen():
    slot = Placement(id="s", term="FA27", slot="ext", credits=3, status="planned")
    plan = [place("ORIE 3300", "FA25", "completed"), place("ORIE 3310", "SP27"), slot]
    assert check_plan(plan, TERMS, "FA26", CATALOG, PROGRAM, requirements="require").feasible


def test_areas_split_ready_from_blocked_with_reasons():
    plan = [place("ORIE 3300", "FA26", "in_progress")]
    areas = courses_by_subject(EXT, "SP27", plan, CATALOG)
    orie = areas["ORIE"]
    ready = [c.code for c in orie.ready]
    blocked = {c.code: why for c, why in orie.blocked}
    assert "ORIE 3310" in ready  # ORIE 3300 is done by spring
    assert blocked["ORIE 4580"] == "Not offered in spring"
    assert "ORIE 4999" not in ready and "ORIE 4999" not in blocked
    # a cross-listed course shows under the area's own code, once
    assert ready.count("ORIE 4520") == 1 and "CEE 4520" not in ready
    assert "CS" not in areas  # the rule excludes CS itself
    assert [c.code for c in areas["CEE"].ready] == ["CEE 4520"]

    fall = courses_by_subject(EXT, "SP27", [place("ORIE 3300", "SP27")], CATALOG)
    assert (
        dict((c.code, w) for c, w in fall["ORIE"].blocked)["ORIE 3310"] == "Needs ORIE 3300 first"
    )


def test_listed_under_prefers_the_subjects_own_code():
    assert listed_under(CATALOG.get("CEE 4520"), "ORIE", CATALOG).code == "ORIE 4520"
    assert listed_under(CATALOG.get("ORIE 3300"), "ORIE", CATALOG).code == "ORIE 3300"
