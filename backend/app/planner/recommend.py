"""Rank the courses that could fill a slot by what the student told us.

`list_eligible` decides what's allowed; this only orders it. Every point a course gets
comes with a reason that names where it came from: something the student said (a
stated profile fact), something we guessed and haven't confirmed (an inferred fact), or
the plan itself. Courses nothing speaks for keep the official order (offered most often
first), so with an empty profile the list is exactly what it was before.

The function is pure (courses and facts in, an ordering out) so the advisor can ask
"how would the list change if the student said X?" before deciding whether a question
is worth asking.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.catalog.store import Catalog
from app.planner.audit import subjects_of
from app.planner.eligible import offering_order
from app.schemas.courses import AllOf, AnyOf, Course, CourseReq, PrereqExpr
from app.schemas.explore import RankingFactor, Reason
from app.schemas.plans import Placement
from app.schemas.profile import ProfileFact
from app.schemas.requirements import Program

# Onboarding's interest choices (web/src/features/onboarding/goals.ts) and the phrases
# that mark a course as being about them. Checked against the CS 4000+ titles: a title
# match is reliable, a description match is not (CS 4820's description mentions machine
# learning), so descriptions only count weakly and need two different phrases.
INTERESTS: dict[str, tuple[str, list[str]]] = {
    "ml": (
        "machine learning",
        [
            "machine learning",
            "deep learning",
            "neural network",
            "reinforcement learning",
            "learning theory",
            "statistical learning",
            "artificial intelligence",
            "computer vision",
            "natural language",
        ],
    ),
    "systems": (
        "systems",
        [
            "operating system",
            "distributed system",
            "distributed computing",
            "networks",
            "networking",
            "cloud",
            "database system",
            "computer architecture",
            "storage",
            "concurren",
        ],
    ),
    "theory": (
        "theory",
        [
            "algorithm",
            "complexity",
            "computability",
            "combinatori",
            "graph theory",
            "cryptograph",
            "logic",
            "approximation",
        ],
    ),
    "security": ("security", ["security", "cryptograph", "privacy", "secure", "attack"]),
    "hci": (
        "human-computer interaction",
        [
            "human-computer",
            "human computer",
            "user interface",
            "interaction design",
            "usability",
            "social computing",
            "user experience",
        ],
    ),
    "pl": (
        "programming languages",
        [
            "programming language",
            "compiler",
            "type system",
            "functional programming",
            "semantics",
            "program analysis",
            "verification",
        ],
    ),
    "graphics": (
        "graphics",
        [
            "graphics",
            "rendering",
            "animation",
            "geometric model",
            "computer vision",
            "virtual reality",
        ],
    ),
    "data": (
        "data science",
        [
            "data science",
            "data mining",
            "database",
            "information retrieval",
            "big data",
            "visualization",
            "data analysis",
            "statistics",
        ],
    ),
}

# how much a fact counts: a guess we haven't confirmed counts half
WEIGHT = {"stated": 1.0, "inferred": 0.5}

TITLE, DESCRIPTION, SUBJECT = 3.0, 1.0, 2.0
GRAD_LEVEL = 2.0
PROJECT = 1.0
BUILDS_ON = 1.5
LIGHT = 0.5

# master's-level courses, which undergraduates can take; 6000+ are PhD seminars
GRAD_LEVELS = range(5000, 6000)
# a grad-level course in another department isn't preparation for a CS grad program,
# and liberal studies or the external specialization shouldn't fill up with them
GRAD_SUBJECT = "CS"
BUILDS_ON_MIN = 3000  # an intro course in the plan says little about the student
LIGHT_MAX_CREDITS = 3
PROJECT_WORDS = ["practicum", "project", "software engineering", "applications"]


@dataclass
class Ranked:
    course: Course
    score: float = 0.0
    reasons: list[Reason] = field(default_factory=list)


@dataclass
class Ranking:
    courses: list[Ranked]
    factors: list[RankingFactor]

    @property
    def personalized(self) -> bool:
        return any(r.score > 0 for r in self.courses)


def rank(
    courses: list[Course],
    facts: list[ProfileFact],
    placements: list[Placement],
    catalog: Catalog,
    standard: set[str] = frozenset(),
) -> Ranking:
    """`courses` ordered by fit, best first, each with the reasons behind its score.
    Ties keep the official order. `standard` is the courses the degree names (see
    `standard_courses`): building on CS 3110 says nothing about a CS student, building
    on an elective they chose does."""
    used = [f for f in facts if f.status in WEIGHT]
    interests = [f for f in used if f.dimension == "interest"]
    grad = [f for f in used if _wants_grad_school(f)]
    industry = [f for f in used if f.dimension == "career_track" and f.value == "industry"]
    light = [f for f in used if f.dimension == "term_load" and f.value == "light"]
    in_plan = {
        code: p.course
        for p in placements
        if p.course
        and (c := catalog.get(p.course))
        and c.level >= BUILDS_ON_MIN
        and not catalog.equivalents(p.course) & standard
        for code in catalog.prereq_credit(p.course)
    }

    out = []
    for course in courses:
        r = Ranked(course)
        for f in interests:
            _interest(r, f, catalog)
        if grad and course.level in GRAD_LEVELS and GRAD_SUBJECT in subjects_of(course):
            f = _strongest(grad)
            r.score += GRAD_LEVEL * WEIGHT[f.status]
            r.reasons.append(_said(f, "A graduate-level course, good preparation for grad school"))
        if industry and _has(course.title, PROJECT_WORDS):
            f = _strongest(industry)
            r.score += PROJECT * WEIGHT[f.status]
            r.reasons.append(_said(f, "Hands-on project work, useful for an industry job"))
        built = sorted({in_plan[c] for c in _prereq_codes(course.prereqs) if c in in_plan})
        if built:
            r.score += BUILDS_ON
            names = " and ".join(built[:2])
            verb = "is" if len(built[:2]) == 1 else "are"
            r.reasons.append(
                Reason(text=f"Builds on {names}, which {verb} in your plan", basis="plan")
            )
        if light and course.credits <= LIGHT_MAX_CREDITS:
            f = _strongest(light)
            r.score += LIGHT * WEIGHT[f.status]
            r.reasons.append(
                _said(f, f"{course.credits} credits, which suits the lighter semesters you want")
            )
        out.append(r)

    out.sort(key=lambda r: (-r.score, offering_order(r.course)))
    return Ranking(out, _factors(out, interests, grad, industry, light))


def standard_courses(program: Program) -> set[str]:
    """Every course a requirement names by code (the core, the math, the practicum
    list): ones most students in the program take, so a course needing them isn't
    "building on" anything the student picked."""
    return {c for r in program.all_requirements() if r.kind == "courses" for c in r.courses}


# the external specialization takes three courses from one subject, so an area is
# judged by its best three: one matching course in a big department shouldn't outrank
# a department built around the interest
AREA_COURSES = 3


@dataclass
class AreaFit:
    score: float = 0.0
    reasons: list[Reason] = field(default_factory=list)
    # the area's courses that match an interest, in the order given; `count` is how many
    # could count toward the rule (cross-listing caps applied), for breaking ties
    matches: list[Course] = field(default_factory=list)
    count: int = 0


def rank_areas(
    areas: dict[str, list[Course]],
    facts: list[ProfileFact],
    catalog: Catalog,
    caps: dict[str, int] | None = None,
) -> dict[str, AreaFit]:
    """How well each subject a same-subject rule could come from fits the student's
    interests. Only titles count here (a description match is too weak to pick a
    department by). A free-text interest that names the subject ("linguistics" for
    LING) makes every course in it a match. `caps` is the rule's cross-listing limits
    ({CS: 1}): two ORIE courses cross-listed with CS are one usable match, not two."""
    interests = [f for f in facts if f.status in WEIGHT and f.dimension == "interest"]
    out: dict[str, AreaFit] = {}
    for subject, courses in areas.items():
        fit = AreaFit()
        name = catalog.subject_name(subject)
        matched: set[str] = set()
        for f in interests:
            phrase, words = INTERESTS.get(f.value, (f.value, [f.value]))
            weight = WEIGHT[f.status]
            if f.value not in INTERESTS and _has(name, words):
                hits = courses
                text = f"{name}, which you're interested in"
            else:
                hits = [c for c in courses if _has(c.title, words)]
                n = _usable(hits, caps or {})
                noun = "course" if n == 1 else "courses"
                text = f"{n} {noun} about {phrase}, which you're interested in"
            n = _usable(hits, caps or {})
            if not n:
                continue
            fit.score += TITLE * weight * min(n, AREA_COURSES)
            fit.reasons.append(_said(f, text))
            matched |= {c.code for c in hits}
        fit.matches = [c for c in courses if c.code in matched]
        fit.count = _usable(fit.matches, caps or {})
        out[subject] = fit
    return out


def _usable(courses: list[Course], caps: dict[str, int]) -> int:
    """How many of `courses` could count together under the rule's cross-listing caps."""
    capped = {s: sum(any(x.split()[0] == s for x in c.cross_listed) for c in courses) for s in caps}
    over = sum(max(0, n - caps[s]) for s, n in capped.items())
    return len(courses) - over


def _interest(r: Ranked, f: ProfileFact, catalog: Catalog) -> None:
    """Points for a course that's about something the student is interested in: one of
    onboarding's choices by its phrases, or free text ("economics") by the phrase itself
    and by subject name (ECON is "Economics")."""
    phrase, words = INTERESTS.get(f.value, (f.value, [f.value]))
    weight = WEIGHT[f.status]
    c = r.course
    if _has(c.title, words):
        r.score += TITLE * weight
        r.reasons.append(_said(f, f"About {phrase}, which you're interested in"))
    elif f.value not in INTERESTS and _has(catalog.subject_name(c.subject), words):
        r.score += SUBJECT * weight
        name = catalog.subject_name(c.subject)
        article = "An" if name[:1].lower() in "aeiou" else "A"
        r.reasons.append(_said(f, f"{article} {name} course, which you're interested in"))
    elif sum(_has(c.description, [w]) for w in words) >= min(2, len(words)):
        r.score += DESCRIPTION * weight
        r.reasons.append(_said(f, f"Covers some {phrase}, which you're interested in"))


def _wants_grad_school(f: ProfileFact) -> bool:
    return (f.dimension == "grad_school" and f.value == "yes") or (
        f.dimension == "career_track" and f.value == "grad_school"
    )


def _strongest(facts: list[ProfileFact]) -> ProfileFact:
    """A stated fact over a guess; the newest of those."""
    return max(facts, key=lambda f: (WEIGHT[f.status], _when(f)))


def _when(f: ProfileFact) -> datetime:
    return f.last_confirmed_at or f.updated_at


def _said(f: ProfileFact, text: str) -> Reason:
    if f.status == "stated":
        return Reason(text=text, basis="stated", fact_id=f.id, date=_date(_when(f)))
    return Reason(text=text, basis="inference", fact_id=f.id)


def _date(d: datetime) -> str:
    return f"{d:%b} {d.day}"  # "Sep 12", as the cards show it


def _has(text: str, words: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(w), text, re.I) for w in words)


def _prereq_codes(expr: PrereqExpr | None) -> set[str]:
    if isinstance(expr, CourseReq):
        return {expr.code}
    if isinstance(expr, AllOf | AnyOf):
        return {code for item in expr.items for code in _prereq_codes(item)}
    return set()


def _factors(out: list[Ranked], interests, grad, industry, light) -> list[RankingFactor]:
    """What shaped the order, for the sidebar: each signal, how much it counted, and
    where it came from. Reviews are listed as unused rather than left out, so the
    student can see no ratings went into it."""

    def factor(label: str, facts: list[ProfileFact], strong: str) -> RankingFactor:
        if not facts:
            return RankingFactor(label=label, strength="not used", basis="Not in your profile")
        f = _strongest(facts)
        if f.status == "stated":
            return RankingFactor(
                label=label, strength=strong, basis=f"You said · {_date(_when(f))}"
            )
        return RankingFactor(label=label, strength="weak", basis="My guess · not confirmed")

    names = ", ".join(INTERESTS.get(f.value, (f.value,))[0] for f in interests)
    built = any(r.basis == "plan" for c in out for r in c.reasons)
    return [
        factor(f"Interests: {names}" if names else "Interests", interests, "strong"),
        factor("Grad school", grad, "medium"),
        factor("Industry job", industry, "medium"),
        RankingFactor(
            label="Courses already in your plan",
            strength="medium" if built else "not used",
            basis="Your plan" if built else "Nothing here builds on them",
        ),
        factor("Lighter semesters", light, "weak"),
        RankingFactor(label="Student reviews", strength="not used", basis="No review data yet"),
    ]
