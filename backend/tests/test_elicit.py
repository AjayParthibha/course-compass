"""Choosing whether to ask before recommending: a question is worth asking when its
likely answers lead to different top picks, and never when the student already
answered it or asked to leave it for later."""

from datetime import datetime

from app.catalog.store import Catalog
from app.planner.elicit import ASK_ABOVE, _disagreement, plan_question
from app.schemas.courses import Course
from app.schemas.profile import ProfileFact

WHEN = datetime(2026, 9, 12)


def course(code, title, terms=4):
    subject, number = code.split()
    return Course(
        code=code,
        subject=subject,
        number=number,
        title=title,
        credits_min=3,
        credits_max=3,
        terms_offered=["FA22", "SP23", "FA23", "SP24", "FA24", "SP25"][:terms],
        typical_seasons=["FA", "SP"],
    )


def fact(dimension, value, status="stated", fid=1):
    return ProfileFact(
        id=fid,
        dimension=dimension,
        value=value,
        text="",
        status=status,
        created_at=WHEN,
        updated_at=WHEN,
    )


# a CS elective slot whose courses split cleanly by interest area
CS = [
    course("CS 4780", "Machine Learning"),
    course("CS 4782", "Deep Learning"),
    course("CS 4789", "Reinforcement Learning"),
    course("CS 4410", "Operating Systems"),
    course("CS 4450", "Computer Networks"),
    course("CS 5412", "Cloud Computing"),
    course("CS 4830", "Cryptography"),
    course("CS 5430", "System Security"),
    course("CS 5435", "Security and Privacy"),
]
# liberal studies: many subjects, nothing to do with CS
LS = [
    course("PHIL 1100", "Introduction to Philosophy"),
    course("PHIL 2400", "Ethics"),
    course("PHIL 2410", "Logic and Argument"),
    course("HIST 1530", "American History"),
    course("HIST 2000", "World History"),
    course("HIST 2100", "Ancient Rome"),
    course("ENGL 2010", "The Novel"),
    course("ENGL 2020", "Poetry"),
]
CAT = Catalog(
    CS + LS,
    subject_names={
        "CS": "Computer Science",
        "PHIL": "Philosophy",
        "HIST": "History",
        "ENGL": "English",
    },
)


def test_an_empty_profile_on_a_cs_elective_asks_about_interests():
    plan = plan_question(CS, [], [], CAT)
    assert plan.ask is not None and plan.ask.dimension == "interest"
    by_label = {o.label: o for o in plan.ask.options}
    assert set(by_label["Machine learning"].picks) == {"CS 4780", "CS 4782", "CS 4789"}
    assert by_label["Security"].facts == [("interest", "security")]
    assert plan.ask.disagreement >= ASK_ABOVE
    # only areas the slot has courses in are offered: nothing here is about graphics
    # (cryptography counts as theory as well as security)
    assert set(by_label) == {"Machine learning", "Systems", "Security", "Theory"}


def test_a_stated_interest_that_decides_the_top_picks_isnt_asked_again():
    plan = plan_question(CS, [fact("interest", "ml")], [], CAT)
    assert all(q.dimension != "interest" for q in plan.considered)


def test_a_guess_or_a_conflict_can_still_be_asked_about():
    for status in ("inferred", "conflict"):
        plan = plan_question(CS, [fact("interest", "ml", status=status)], [], CAT)
        assert any(q.dimension == "interest" for q in plan.considered), status


def test_a_question_left_for_later_isnt_asked():
    plan = plan_question(CS, [fact("interest", "", status="open")], [], CAT)
    assert all(q.dimension != "interest" for q in plan.considered)


def test_liberal_studies_asks_about_subjects_even_with_a_cs_interest():
    # the proposal's example: an ML interest says nothing about a liberal studies course
    plan = plan_question(LS, [fact("interest", "ml")], [], CAT, slot_label="liberal studies")
    assert plan.ask is not None
    assert plan.ask.text == "What would you enjoy for your liberal studies?"
    labels = [o.label for o in plan.ask.options]
    assert set(labels) == {"Philosophy", "History", "English"}
    philosophy = next(o for o in plan.ask.options if o.label == "Philosophy")
    assert set(philosophy.picks) == {"PHIL 1100", "PHIL 2400", "PHIL 2410"}
    # career plans don't decide a liberal studies course, so that isn't considered
    assert [q.dimension for q in plan.considered] == ["interest"]


def test_three_or_fewer_courses_need_no_question():
    plan = plan_question(CS[:3], [], [], CAT)
    assert plan.ask is None and plan.considered == []
    assert plan_question([], [], [], CAT).ask is None


def test_answers_that_change_nothing_arent_worth_asking():
    # every course is about machine learning: any interest answer gives the same three
    same = [course(f"CS 47{i}0", "Machine Learning", terms=6 - i) for i in range(5)]
    cat = Catalog(same)
    plan = plan_question(same, [fact("grad_school", "yes")], [], cat)
    assert plan.ask is None and "wouldn't change" in plan.reason


def test_answered_career_plans_arent_asked_again():
    plan = plan_question(CS, [fact("career_track", "industry")], [], CAT)
    assert all(q.dimension != "career_track" for q in plan.considered)


def test_disagreement_runs_from_zero_to_one():
    assert _disagreement([["A", "B"], ["A", "B"]]) == 0
    assert _disagreement([["A", "B"], ["C", "D"]]) == 1
    assert _disagreement([["A", "B"], ["A", "C"]]) == 1 - 1 / 3
    assert _disagreement([["A"]]) == 0


def test_interests_go_first_when_both_questions_are_worth_asking():
    plan = plan_question(CS, [], [], CAT)
    worth = [q for q in plan.considered if q.worth_asking]
    assert {q.dimension for q in worth} == {"interest", "career_track"}
    assert plan.ask.dimension == "interest"


def test_a_field_the_student_named_settles_liberal_studies():
    plan = plan_question(LS, [fact("interest", "Philosophy")], [], CAT)
    assert plan.ask is None and "already decides" in plan.reason
