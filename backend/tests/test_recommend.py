"""The profile-aware ranking, on a small catalog where every order can be checked by
hand. Nothing here needs the database: facts are built directly."""

from datetime import datetime
from pathlib import Path

import pytest

from app.catalog.store import Catalog
from app.planner.eligible import list_eligible
from app.planner.recommend import rank, standard_courses
from app.requirements.loader import load_program
from app.schemas.courses import AllOf, Course, CourseReq
from app.schemas.plans import Placement
from app.schemas.profile import ProfileFact

SEP_12 = datetime(2026, 9, 12)


def course(code, title, credits=3, description="", prereqs=None, terms=6):
    subject, number = code.split()
    return Course(
        code=code,
        subject=subject,
        number=number,
        title=title,
        description=description,
        credits_min=credits,
        credits_max=credits,
        prereqs=prereqs,
        terms_offered=["FA22", "SP23", "FA23", "SP24", "FA24", "SP25"][:terms],
        typical_seasons=["FA", "SP"],
    )


def fact(dimension, value, status="stated", fid=1, when=SEP_12):
    return ProfileFact(
        id=fid,
        dimension=dimension,
        value=value,
        text=f"{dimension}: {value}",
        status=status,
        created_at=when,
        updated_at=when,
    )


# offered most often first when nothing else decides: DB, OS, ML, then the rest
DB = course("CS 4320", "Introduction to Database Systems", terms=6)
OS = course("CS 4410", "Operating Systems", terms=5)
ML = course("CS 4780", "Introduction to Machine Learning", credits=4, terms=4)
DL = course(
    "CS 4782",
    "Introduction to Deep Learning",
    credits=4,
    terms=3,
    prereqs=CourseReq(code="CS 3780"),
)
GRAD = course("CS 5414", "Distributed Computing Principles", terms=3)
ALGO = course(
    "CS 4820",
    "Introduction to Analysis of Algorithms",
    credits=4,
    terms=6,
    description="Uses of machine learning and artificial intelligence are discussed.",
)
ECON = course("ECON 3130", "Statistics and Probability", credits=4, terms=2)
CAT = Catalog(
    [
        DB,
        OS,
        ML,
        DL,
        GRAD,
        ALGO,
        ECON,
        course("CS 3780", "Introduction to Machine Learning", credits=4),
    ],
    subject_names={"CS": "Computer Science", "ECON": "Economics"},
)
COURSES = [DB, OS, ML, DL, GRAD]


def codes(ranking):
    return [r.course.code for r in ranking.courses]


def test_no_profile_keeps_the_official_order():
    ranking = rank(COURSES, [], [], CAT)
    assert codes(ranking) == ["CS 4320", "CS 4410", "CS 4780", "CS 4782", "CS 5414"]
    assert not ranking.personalized
    assert all(r.reasons == [] for r in ranking.courses)


def test_an_interest_moves_matching_titles_up_and_says_why():
    ranking = rank(COURSES, [fact("interest", "ml")], [], CAT)
    assert codes(ranking)[:2] == ["CS 4780", "CS 4782"]
    top = ranking.courses[0].reasons
    assert [r.text for r in top] == ["About machine learning, which you're interested in"]
    assert top[0].basis == "stated" and top[0].fact_id == 1 and top[0].date == "Sep 12"


def test_a_description_mention_counts_less_than_a_title():
    # CS 4820's description names machine learning twice over; CS 4780 is about it
    ranking = rank([ALGO, ML], [fact("interest", "ml")], [], CAT)
    assert codes(ranking) == ["CS 4780", "CS 4820"]
    weak = ranking.courses[1]
    assert weak.score < ranking.courses[0].score
    assert weak.reasons[0].text.startswith("Covers some machine learning")


def test_a_guess_counts_half_and_is_marked_as_one():
    stated = rank(COURSES, [fact("interest", "ml")], [], CAT).courses[0]
    guessed = rank(COURSES, [fact("interest", "ml", status="inferred")], [], CAT).courses[0]
    assert guessed.score == stated.score / 2
    assert guessed.reasons[0].basis == "inference" and guessed.reasons[0].date is None


@pytest.mark.parametrize("status", ["rejected", "superseded", "open", "conflict"])
def test_facts_the_student_hasnt_settled_are_ignored(status):
    ranking = rank(COURSES, [fact("interest", "ml", status=status)], [], CAT)
    assert codes(ranking) == codes(rank(COURSES, [], [], CAT))


def test_grad_school_prefers_graduate_courses():
    for f in (fact("grad_school", "yes"), fact("career_track", "grad_school")):
        ranking = rank(COURSES, [f], [], CAT)
        assert codes(ranking)[0] == "CS 5414"
        assert "grad school" in ranking.courses[0].reasons[0].text


def test_a_course_that_builds_on_the_plan_says_which_course():
    plan = [Placement(id="p", term="FA25", course="CS 3780", credits=4, status="completed")]
    ranking = rank(COURSES, [], plan, CAT)
    assert codes(ranking)[0] == "CS 4782"
    reason = ranking.courses[0].reasons[0]
    assert reason.text == "Builds on CS 3780, which is in your plan" and reason.basis == "plan"


def test_courses_the_degree_names_dont_count_as_building_on_them():
    # every CS student takes CS 3780 or 3700; an elective they picked says more
    plan = [Placement(id="p", term="FA25", course="CS 3780", credits=4, status="completed")]
    ranking = rank(COURSES, [], plan, CAT, standard={"CS 3700", "CS 3780"})
    assert not ranking.personalized


def test_phd_seminars_get_no_grad_school_boost():
    seminar = course("CS 6787", "Advanced Machine Learning Systems", terms=3)
    ranking = rank([seminar, GRAD], [fact("grad_school", "yes")], [], CAT)
    assert codes(ranking) == ["CS 5414", "CS 6787"]
    assert ranking.courses[1].reasons == []


def test_intro_courses_in_the_plan_dont_count_as_building_on_them():
    needs_intro = course("CS 4999", "Topics", prereqs=AllOf(items=[CourseReq(code="CS 2110")]))
    plan = [Placement(id="p", term="FA24", course="CS 2110", credits=4, status="completed")]
    cat = Catalog([needs_intro, course("CS 2110", "OOP and Data Structures", credits=4)])
    assert rank([needs_intro], [], plan, cat).courses[0].reasons == []


def test_free_text_interests_match_titles_and_subject_names():
    ranking = rank([DB, ECON], [fact("interest", "economics")], [], CAT)
    assert codes(ranking) == ["ECON 3130", "CS 4320"]
    assert ranking.courses[0].reasons[0].text == "An Economics course, which you're interested in"


def test_lighter_semesters_lean_toward_three_credit_courses():
    ranking = rank([ML, DB], [fact("term_load", "light")], [], CAT)
    assert codes(ranking) == ["CS 4320", "CS 4780"]


def test_signals_add_up():
    # interested in ML and building on CS 3780: deep learning beats intro ML
    plan = [Placement(id="p", term="FA25", course="CS 3780", credits=4, status="completed")]
    ranking = rank(COURSES, [fact("interest", "ml")], plan, CAT)
    assert codes(ranking)[:2] == ["CS 4782", "CS 4780"]
    assert [r.basis for r in ranking.courses[0].reasons] == ["stated", "plan"]


def test_factors_name_what_was_used_and_what_wasnt():
    ranking = rank(
        COURSES, [fact("interest", "ml"), fact("grad_school", "yes", "inferred")], [], CAT
    )
    factors = {f.label: f for f in ranking.factors}
    assert factors["Interests: machine learning"].strength == "strong"
    assert factors["Interests: machine learning"].basis == "You said · Sep 12"
    assert factors["Grad school"].strength == "weak"
    assert factors["Industry job"].strength == "not used"
    # no ratings go in, and the sidebar says so
    assert factors["Student reviews"].strength == "not used"


def test_the_real_roster_puts_ml_courses_first_for_an_ml_student():
    root = Path(__file__).resolve().parents[2] / "data"
    snapshot = sorted((root / "snapshots").iterdir())[-1]
    roster = Catalog.load(snapshot, root / "prereqs", root / "prereq_equivalents.yaml")
    program = load_program("cs-eng", "2024-25", root / "requirements")
    e4000 = next(r for r in program.all_requirements() if r.id == "e4000")
    history = ["CS 1110", "CS 2110", "CS 2800", "CS 3110", "MATH 1920", "MATH 2940"]
    plan = [Placement(id=c, term="FA25", course=c, credits=4, status="completed") for c in history]
    eligible = list_eligible(e4000, "SP27", plan, roster)
    ranking = rank(eligible, [fact("interest", "ml")], plan, roster, standard_courses(program))
    top = ranking.courses[:5]
    assert all(r.reasons and r.reasons[0].text.startswith("About machine learning") for r in top)
    # the core in the plan (CS 3110, CS 2800) isn't offered as a reason
    assert not any(r.basis == "plan" for c in ranking.courses for r in c.reasons)
