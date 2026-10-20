"""Reading Cornell's unofficial transcript. The text below is made up, laid out like the
PDF's text layer (term headers, "SUBJ   NNNN TITLE EARNED GRADE" lines, test credits)."""

import base64

from app.catalog.store import Catalog
from app.planner.solver import check_plan
from app.planner.validate import validate
from app.schemas.courses import Course
from app.schemas.plans import Placement
from app.schemas.requirements import Program, Requirement, RequirementSet
from app.transcript import parse_transcript

TEXT = """UNOFFICIAL TRANSCRIPT
Student Name: Test Student Date printed: 1/1/2026
----- Beginning of Undergraduate  Record  -----
FALL 2024
Program:  Engineering
Course Description Earned Grade
CS   1110 INTRO COMPUTING: DESIGN & DEV 4.00 A
ENGRG   3400 EN STUDENT PROJECT TEAMS 2.00 A
 COURSE TOPIC(S): SOME TEAM
PHYS   1112 PHYSICS I: MECHANICS 4.00 W
Term GPA: 4.000 Term Totals: 6.00
SPRING 2025
Program:  Engineering
Course Description Earned Grade
CS   2110 OBJ-ORIENTED PROG & DATA STRUC 4.00 B+
ENGRG   3400 EN STUDENT PROJECT TEAMS 1.00 SX
FALL 2025
Program:  Engineering
Course Description Earned Grade
CS   2800 DISCRETE STRUCTURES 0.00
---- Test Credits Detailed ----
 Advanced Placement
Mathematics: Calculus BC
(5.00)
Transferred to Term 2024FA
MATH 1910 Calculus for Engineers 4.00   S
End of Career
"""


def course(code, credits=4):
    subject, number = code.split()
    return Course(
        code=code,
        subject=subject,
        number=number,
        title=code,
        credits_min=1,
        credits_max=credits,
        terms_offered=["FA24"],
        typical_seasons=["FA", "SP"],
    )


CAT = Catalog(
    [course(c) for c in ("CS 1110", "CS 2110", "CS 2800", "PHYS 1112", "MATH 1910")]
    + [course("ENGRG 3400", 3)]
)


def test_reads_terms_credits_and_exam_credit():
    r = parse_transcript(TEXT, CAT)
    assert (r.entering_term, r.program) == ("FA24", "cs-eng")
    got = [(c.term, c.code, c.credits) for c in r.courses]
    assert got == [
        ("FA24", "CS 1110", 4),
        ("FA24", "ENGRG 3400", 2),  # credits earned, not the roster's 3
        ("SP25", "CS 2110", 4),
        ("SP25", "ENGRG 3400", 1),  # a repeat each term, kept without a question
        ("FA25", "CS 2800", 4),  # in progress: no grade yet, the roster's credits
        ("FA24", "MATH 1910", 4),
    ]
    assert all(c.issue is None for c in r.courses)
    assert r.courses[-1].note == "Credit by exam: Mathematics: Calculus BC"
    # a withdrawal earned nothing, so it's listed as not counted
    assert r.skipped == ["PHYS 1112 (Fall 2024): grade W, no credit"]


def test_the_upload_rejects_files_that_arent_transcripts(client, auth):
    bad = base64.b64encode(b"not a pdf").decode()
    res = client.post("/api/onboarding/transcript", json={"pdf_base64": bad}, headers=auth)
    assert res.status_code == 400 and "PDF" in res.json()["detail"]
    res = client.post("/api/onboarding/transcript", json={"pdf_base64": "%%%"}, headers=auth)
    assert res.status_code == 400


def test_a_course_taken_twice_is_history_not_a_problem():
    def place(pid, term, status="completed"):
        return Placement(id=pid, term=term, course="ENGRG 3400", credits=2, status=status)

    plan = [place("a", "FA24"), place("b", "SP25")]
    dup = [v for v in validate(plan, ["FA24", "SP25", "FA25"], CAT) if v.kind == "duplicate"]
    assert len(dup) == 1 and not dup[0].blocking
    rules = RequirementSet(
        id="t",
        label="t",
        catalog_year="2024-25",
        source_url="x",
        requirements=[Requirement(id="r", label="r", kind="courses", courses=["CS 1110"])],
    )
    program = Program(id="t", label="t", college="t", catalog_year="2024-25", sets=[rules])
    assert check_plan(plan, ["FA24", "SP25", "FA25"], "FA25", CAT, program).feasible
    # planning a third copy is still a problem
    third = plan + [place("c", "FA25", "planned")]
    assert any(
        v.blocking for v in validate(third, ["FA24", "SP25", "FA25"], CAT) if v.kind == "duplicate"
    )
