"""The model fallback for pasted history lines the regex can't read: it can only pick
from roster courses whose number is on the line, and every pick waits for the student."""

import json

from app.catalog.store import Catalog
from app.onboarding import parse_history
from app.onboarding_model import read_unread
from app.schemas.courses import Course


def course(code, title, cross=()):
    subject, number = code.split()
    return Course(
        code=code,
        subject=subject,
        number=number,
        title=title,
        credits_min=4,
        credits_max=4,
        cross_listed=list(cross),
    )


CAT = Catalog(
    [
        course("CS 4780", "Introduction to Machine Learning", cross=["ECE 4780"]),
        course("ECE 4780", "Introduction to Machine Learning", cross=["CS 4780"]),
        course("ORIE 4780", "Network Flows"),
        course("CS 2800", "Discrete Structures"),
        course("MATH 2800", "Topics in Number Theory"),
        course("CS 2110", "Object-Oriented Programming"),
    ]
)

TEXT = """Fall 2025
CS 2110
machine learning w/ Weinberger 4780
discrete structures (2800)
Spring 2026
that hard proof class 9999
"""


def fake(picks, calls=None):
    """A model that returns `picks` ({line number: codes}) and records its prompts."""

    def ask(prompt):
        if calls is not None:
            calls.append(prompt)
        return json.dumps({"lines": [{"line": i, "codes": c} for i, c in picks.items()]})

    return ask


def test_the_parser_leaves_these_lines_unread():
    rows, unread = parse_history(TEXT, CAT)
    assert [r.code for r in rows] == ["CS 2110"]
    assert unread == [
        "machine learning w/ Weinberger 4780",
        "discrete structures (2800)",
        "that hard proof class 9999",
    ]


def test_the_model_only_sees_courses_with_the_lines_number():
    _, unread = parse_history(TEXT, CAT)
    calls = []
    read_unread(TEXT, unread, CAT, fake({}, calls))
    prompt = calls[0]
    # one entry per cross-listed course, and nothing for a number the roster lacks
    assert "- CS 4780: Introduction to Machine Learning" in prompt
    assert "ECE 4780" not in prompt and "- ORIE 4780: Network Flows" in prompt
    assert "- MATH 2800: Topics in Number Theory" in prompt
    assert "Line 2" not in prompt


def test_picks_come_back_as_rows_to_confirm_in_the_right_term():
    _, unread = parse_history(TEXT, CAT)
    rows, still = read_unread(
        TEXT, unread, CAT, fake({0: ["CS 4780"], 1: ["CS 2800", "MATH 2800"]})
    )
    assert [r.raw for r in rows] == unread[:2]
    ml, discrete = rows
    # nothing counts until the student picks: no code on the row yet
    assert ml.code is None and ml.issue.kind == "model_guess"
    assert ml.term == "FA25" and discrete.term == "FA25"
    assert ml.issue.message.startswith(
        "We think “machine learning w/ Weinberger 4780” includes CS 4780"
    )
    assert [o.value for o in discrete.issue.options] == ["CS 2800", "MATH 2800", "drop"]
    assert still == ["that hard proof class 9999"]


def test_codes_outside_the_candidates_are_dropped():
    _, unread = parse_history(TEXT, CAT)
    # CS 4782 isn't a candidate (wrong number) and CS 9999 isn't a course at all
    rows, still = read_unread(TEXT, unread, CAT, fake({0: ["CS 4782"], 2: ["CS 9999"]}))
    assert rows == [] and still == unread


def test_none_fit_keeps_the_line_unread():
    _, unread = parse_history(TEXT, CAT)
    rows, still = read_unread(TEXT, unread, CAT, fake({0: [], 1: ["CS 2800"]}))
    assert [r.raw for r in rows] == ["discrete structures (2800)"]
    assert still == ["machine learning w/ Weinberger 4780", "that hard proof class 9999"]


def test_a_broken_answer_leaves_everything_unread():
    _, unread = parse_history(TEXT, CAT)

    def broken(prompt):
        raise TimeoutError

    assert read_unread(TEXT, unread, CAT, broken) == ([], unread)
    assert read_unread(TEXT, unread, CAT, lambda p: "not json") == ([], unread)


def test_no_candidates_means_no_model_call():
    calls = []
    assert read_unread("x 9999", ["x 9999"], CAT, fake({}, calls)) == ([], ["x 9999"])
    assert calls == []


def test_at_most_three_picks_and_no_repeats():
    _, unread = parse_history(TEXT, CAT)
    rows, _ = read_unread(TEXT, unread, CAT, fake({1: ["CS 2800", "CS 2800", "MATH 2800"]}))
    assert [o.value for o in rows[0].issue.options] == ["CS 2800", "MATH 2800", "drop"]


def test_two_numbers_on_a_line_are_two_questions():
    cat = Catalog(
        [
            course("CS 4320", "Introduction to Database Systems"),
            course("COGST 4740", "Natural Language Processing", cross=["CS 4740"]),
            course("CS 4740", "Natural Language Processing", cross=["COGST 4740"]),
        ]
    )
    text = "Spring 2026\ndatabases 4320, nlp 4740"
    _, unread = parse_history(text, cat)
    calls = []
    rows, still = read_unread(text, unread, cat, fake({0: ["CS 4320"], 1: ["CS 4740"]}, calls))
    assert [r.issue.options[0].value for r in rows] == ["CS 4320", "CS 4740"]
    assert all(r.term == "SP26" for r in rows) and still == []
    # the CS listing of a cross-listed course, not whichever code sorts first
    assert "- CS 4740: Natural Language Processing" in calls[0] and "COGST" not in calls[0]
