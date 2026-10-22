"""Which question, if any, is worth asking before recommending courses for a slot.

The proposal's "active preference elicitation": instead of a fixed questionnaire, try
each plausible answer to each question we could ask, rank the slot's courses as if the
student had given it (`recommend.rank`), and see how much the top picks move. A question
whose answers all lead to the same few courses isn't worth the student's time; one
whose answers lead to different courses is. Questions the student already answered, or
asked to leave for later, aren't asked again; a guess we never confirmed, or a fact
that newer information conflicts with, can be.

Pure: courses and facts in, a plan for the question out, so the advisor tool, the
eval and the tests all use the same logic.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import combinations

from app.catalog.store import Catalog
from app.planner.recommend import INTERESTS, rank
from app.schemas.courses import Course
from app.schemas.plans import Placement
from app.schemas.profile import ProfileFact

TOP = 3  # the picks a student sees first, and the ones a question has to move
# ask when two answers, on average, share less than half their top picks
ASK_ABOVE = 0.5
SUBJECT_OPTIONS = 6  # for a slot outside CS, the subjects with the most courses to offer
CS_SHARE = 0.5  # a slot is a CS one when most of its courses are CS
HYPOTHETICAL = -1  # the id of a fact we pretend the student gave

# answer -> the facts it would add: "grad school" is its own dimension in onboarding
CAREER = {
    "A job in industry": [("career_track", "industry")],
    "Grad school": [("grad_school", "yes")],
    "Not sure yet": [("career_track", "undecided")],
}


@dataclass
class Option:
    label: str  # what the student clicks
    facts: list[tuple[str, str]]  # (dimension, value) to save if they pick it
    picks: list[str] = field(default_factory=list)  # the top courses if they did


@dataclass
class Question:
    dimension: str
    text: str
    options: list[Option]
    # 0 when every answer gives the same top picks, 1 when no two share any
    disagreement: float

    @property
    def worth_asking(self) -> bool:
        return self.disagreement >= ASK_ABOVE


@dataclass
class Plan:
    ask: Question | None  # the question to ask, or None to recommend now
    reason: str  # why, in a sentence the advisor can pass on or keep to itself
    considered: list[Question] = field(default_factory=list)


def plan_question(
    courses: list[Course],
    facts: list[ProfileFact],
    placements: list[Placement],
    catalog: Catalog,
    standard: set[str] = frozenset(),
    slot_label: str = "this slot",
) -> Plan:
    """The most useful question for picking among `courses`, or why none is needed."""
    if not courses:
        return Plan(None, "No course fits this slot then, so there's nothing to choose.")
    if len(courses) <= TOP:
        n = "One course fits" if len(courses) == 1 else f"Only {len(courses)} courses fit"
        return Plan(None, f"{n}, so they can all be shown.")

    def picks(extra: list[tuple[str, str]]) -> tuple[list[str], bool]:
        """The top picks with this answer, and whether the answer moved any course
        (an interest the slot has nothing on is no use as an option)."""
        hypothetical = facts + [_fact(d, v) for d, v in extra]
        ranking = rank(courses, hypothetical, placements, catalog, standard)
        moved = any(x.fact_id == HYPOTHETICAL for r in ranking.courses for x in r.reasons)
        return [r.course.code for r in ranking.courses[:TOP]], moved

    candidates = []
    current = rank(courses, facts, placements, catalog, standard)
    if not _settled_interest(facts, current.courses[:TOP], _is_cs(courses)):
        candidates.append(_interest_question(courses, catalog, slot_label))
    if _is_cs(courses) and not _settled(facts, ("career_track", "grad_school")):
        candidates.append(
            Question(
                "career_track",
                "What are you planning to do after graduating?",
                [Option(label, facts) for label, facts in CAREER.items()],
                0.0,
            )
        )

    for q in candidates:
        kept = []
        for o in q.options:
            o.picks, moved = picks(o.facts)
            # interest answers the slot has nothing on aren't offered; career answers
            # are, since "not sure yet" is a real answer even when it changes nothing
            if moved or q.dimension != "interest":
                kept.append(o)
        q.options = kept
        q.disagreement = _disagreement([o.picks for o in q.options])
    if not candidates:
        return Plan(None, "Their profile already decides the top picks here.")
    candidates = [q for q in candidates if len(q.options) > 1]
    # within a tenth, interests go first: they're what the courses are about, while
    # plans after graduating only nudge the level (5000-level, project courses)
    best = max(
        candidates,
        key=lambda q: (round(q.disagreement, 1), q.dimension == "interest"),
        default=None,
    )
    if best is None or not best.worth_asking:
        return Plan(
            None,
            "Every likely answer leads to mostly the same top picks, so a question "
            "wouldn't change the recommendation.",
            candidates,
        )
    return Plan(
        best,
        "Different answers lead to different top picks, so ask before choosing.",
        candidates,
    )


def _interest_question(courses: list[Course], catalog: Catalog, slot_label: str) -> Question:
    """For a CS slot, onboarding's interest areas; for anything else, the subjects the
    slot has the most courses in (answering "Philosophy" saves an interest the ranking
    matches by subject name)."""
    if _is_cs(courses):
        options = [
            Option(phrase[:1].upper() + phrase[1:], [("interest", key)])
            for key, (phrase, _) in INTERESTS.items()
        ]
        return Question("interest", "Which area of CS do you most want to explore?", options, 0)
    subjects = Counter(c.subject for c in courses).most_common(SUBJECT_OPTIONS)
    options = [
        Option(catalog.subject_name(s), [("interest", catalog.subject_name(s))])
        for s, _ in subjects
    ]
    return Question("interest", f"What would you enjoy for your {slot_label}?", options, 0)


def _settled_interest(facts: list[ProfileFact], top, cs: bool) -> bool:
    """The student left interests for later, or what they said already decides every
    one of the top picks. Onboarding's interests are areas of CS, so they settle a CS
    slot but not liberal studies: an ML interest that happens to find "AI and policy"
    isn't what they'd want from a humanities course, which is the proposal's example
    of when to ask. Something they named themselves ("philosophy") settles either."""
    if any(f.dimension == "interest" and f.status == "open" for f in facts):
        return True
    said = {
        f.id
        for f in facts
        if f.dimension == "interest" and f.status == "stated" and (cs or f.value not in INTERESTS)
    }
    return bool(top) and all(any(r.fact_id in said for r in t.reasons) for t in top)


def _settled(facts: list[ProfileFact], dimensions: tuple[str, ...]) -> bool:
    """Answered or left for later. A guess or a conflicting fact can still be asked."""
    return any(f.dimension in dimensions and f.status in ("stated", "open") for f in facts)


def _is_cs(courses: list[Course]) -> bool:
    return sum(c.subject == "CS" for c in courses) > len(courses) * CS_SHARE


def _disagreement(picks: list[list[str]]) -> float:
    """Average over pairs of answers of how little their top picks overlap."""
    pairs = list(combinations([set(p) for p in picks], 2))
    if not pairs:
        return 0.0
    return sum(1 - len(a & b) / len(a | b) for a, b in pairs if a | b) / len(pairs)


def _fact(dimension: str, value: str) -> ProfileFact:
    when = datetime.now(UTC)
    return ProfileFact(
        id=HYPOTHETICAL,
        dimension=dimension,
        value=value,
        text="",
        status="stated",
        created_at=when,
        updated_at=when,
    )
