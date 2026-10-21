"""The rule types added for the Engineering CS rules (checked against the CS checklist
for Fall 2024 matriculants and the 2026-27 catalog), on a small catalog where every
answer can be worked out by hand."""

from pathlib import Path

import pytest
import yaml

from app.catalog.overlaps import overlap_pairs
from app.catalog.store import Catalog
from app.planner.audit import audit, greedy_audit, matches
from app.planner.initial import seed_slots
from app.planner.validate import satisfied, validate
from app.requirements.loader import load_program, load_set
from app.schemas.courses import AllOf, AnyOf, Course, CourseReq
from app.schemas.plans import Placement
from app.schemas.requirements import (
    CourseFilter,
    Program,
    QualifyingPrereq,
    Requirement,
    RequirementGroup,
    RequirementSet,
)

DATA = Path(__file__).resolve().parents[2] / "data" / "requirements"
TERMS = ["FA25", "SP26", "FA26", "SP27"]


def course(code, credits=3, attributes=(), prereq_text="", cross=()):
    subject, number = code.split()
    return Course(
        code=code,
        subject=subject,
        number=number,
        title=code,
        credits_min=credits,
        credits_max=credits,
        attributes=list(attributes),
        prereq_text=prereq_text,
        cross_listed=list(cross),
        terms_offered=["FA24", "SP25"],
        typical_seasons=["FA", "SP"],
    )


def program(*reqs):
    rules = RequirementSet(
        id="t", label="t", catalog_year="2024-25", source_url="x", requirements=list(reqs)
    )
    return Program(id="t", label="t", college="t", catalog_year="2024-25", sets=[rules])


def place(code, term="FA25", credits=3, pid=None, status="completed"):
    return Placement(id=pid or code, term=term, course=code, credits=credits, status=status)


def statuses(plan, prog, cat):
    out = {}

    def walk(rs):
        for r in rs:
            out[r.id] = r
            walk(r.children)

    walk(audit(plan, prog, cat).requirements)
    return out


def test_the_real_rule_files_load():
    for path in DATA.glob("*/2024-25.yaml"):
        RequirementSet.model_validate(yaml.safe_load(path.read_text()))


def test_a_named_course_counts_once_wherever_it_does_most_good():
    # CS 3700 counts for the core or the 4000+ electives, not both
    cat = Catalog([course("CS 3700", 4), course("CS 4780", 4), course("CS 4820", 4)])
    core = Requirement(id="core", label="Core", kind="courses", courses=["CS 3700"])
    e4000 = Requirement(
        id="e4000",
        label="4000+",
        kind="filter",
        filter=CourseFilter(subjects=["CS"], min_level=4000, include=["CS 3700"]),
        count=2,
    )
    plan = [place("CS 3700"), place("CS 4780")]
    st = statuses(plan, program(core, e4000), cat)
    assert st["core"].status == "done" and st["e4000"].status == "missing"
    st = statuses(plan + [place("CS 4820")], program(core, e4000), cat)
    assert st["core"].status == "done" and st["e4000"].status == "done"
    assert "CS 3700" not in st["e4000"].filled


def test_rotc_counts_only_from_3000():
    cat = Catalog([course("AIRS 2010"), course("AIRS 3010")])
    f = CourseFilter(min_level=1100, min_level_for={"AIRS": 3000})
    rule = Requirement(id="r", label="r", kind="filter", filter=f)
    assert not matches(cat.get("AIRS 2010"), rule, cat)
    assert matches(cat.get("AIRS 3010"), rule, cat)


def test_technical_electives_need_a_qualifying_prerequisite():
    q = QualifyingPrereq(
        exempt_subjects=["CS"],
        courses=["MATH 1920"],
        subjects=["ENGRD"],
        text_any=["probability"],
        chain=True,
    )
    cat = Catalog(
        [
            course("CS 3300"),  # CS: qualifies on its own
            course("ECON 3200", prereq_text="MATH 1920."),  # a listed course
            course("MAE 3000", prereq_text="ENGRD 2020 or permission."),  # any ENGRD
            course("ILR 3000", prereq_text="An introductory course in probability."),  # wording
            course("ECON 3300", prereq_text="ECON 3200."),  # chain: ECON 3200 needs MATH 1920
            course("HIST 3000", prereq_text="None."),
            course(
                "GOV 3000", prereq_text="GOVT 1111. Recommended: MATH 1920."
            ),  # only recommended
        ]
    )
    rule = Requirement(
        id="tech",
        label="tech",
        kind="filter",
        filter=CourseFilter(min_level=3000, qualifying_prereq=q),
    )
    ok = {c.code for c in cat.courses.values() if matches(c, rule, cat)}
    assert ok == {"CS 3300", "ECON 3200", "MAE 3000", "ILR 3000", "ECON 3300"}


def test_at_most_one_technical_elective_below_3000():
    cat = Catalog([course("CS 2800"), course("CS 2110"), course("CS 3110")])
    tech = Requirement(
        id="tech",
        label="tech",
        kind="filter",
        filter=CourseFilter(subjects=["CS"], min_level=2000),
        count=2,
        max_below_level={3000: 1},
    )
    two_low = [place("CS 2800"), place("CS 2110")]
    assert statuses(two_low, program(tech), cat)["tech"].status == "missing"
    assert statuses(two_low + [place("CS 3110")], program(tech), cat)["tech"].status == "done"


def liberal_studies():
    return Requirement(
        id="ls",
        label="Liberal studies",
        kind="filter",
        filter=CourseFilter(
            attributes_any=["SSC-AS", "HA-AG", "ETM-AS", "CE-EN", "D-AG"], min_credits=3
        ),
        count=4,
        groups=[
            RequirementGroup(id="g2", label="history", attributes_any=["HA-AG"]),
            RequirementGroup(id="g3", label="ethics", attributes_any=["ETM-AS"]),
            RequirementGroup(id="g4", label="social science", attributes_any=["SSC-AS"]),
            RequirementGroup(
                id="g6", label="engineering comm", attributes_any=["CE-EN"], max_courses=1
            ),
            RequirementGroup(
                id="g7", label="race and equity", attributes_any=["D-AG"], min_credits=3
            ),
        ],
        min_groups=3,
        min_at_level={2000: 1},
    )


LS_CAT = Catalog(
    [
        course("ECON 1110", attributes=["SSC-AS"]),
        course("PSYCH 1101", attributes=["SSC-AS"]),
        course("HIST 2000", attributes=["HA-AG"]),
        course("AAS 2100", attributes=["D-AG", "SSC-AS"]),
        course("ENGRC 3500", attributes=["CE-EN"]),
        course("ENGRC 3350", attributes=["CE-EN"]),
        course("PHIL 1100", attributes=["ETM-AS"]),
    ]
)


def test_liberal_studies_needs_three_groups_and_race_and_equity():
    ls = liberal_studies()
    # four courses but only social science and history, and nothing from Group 7
    plan = [place("ECON 1110"), place("PSYCH 1101"), place("HIST 2000"), place("PHIL 1100")]
    assert statuses(plan, program(ls), LS_CAT)["ls"].status == "missing"
    # AAS 2100 carries both SSC-AS and D-AG: counted in Group 7 it supplies the 3 credits
    plan = [place("ECON 1110"), place("HIST 2000"), place("PHIL 1100"), place("AAS 2100")]
    assert statuses(plan, program(ls), LS_CAT)["ls"].status == "done"


def test_liberal_studies_caps_group_six_and_needs_upper_level():
    ls = liberal_studies()
    # two Group 6 courses: only one may count, so four courses aren't enough
    plan = [place("ENGRC 3500"), place("ENGRC 3350"), place("AAS 2100"), place("PHIL 1100")]
    assert statuses(plan, program(ls), LS_CAT)["ls"].status == "missing"
    # nothing at the 2000 level: the level rule fails
    low = ls.model_copy(update={"min_at_level": {2000: 1}, "groups": [], "min_groups": None})
    plan = [place("ECON 1110"), place("PSYCH 1101"), place("PHIL 1100")]
    assert (
        statuses(plan, program(low.model_copy(update={"count": 3})), LS_CAT)["ls"].status
        == "missing"
    )


def test_open_slots_can_stand_for_any_group():
    ls = liberal_studies()
    slot = Placement(id="s", term="SP27", slot="ls", slot_label="LS", credits=3, status="planned")
    plan = [place("ECON 1110"), place("HIST 2000"), place("PHIL 1100"), slot]
    assert statuses(plan, program(ls), LS_CAT)["ls"].status == "planned"


def test_distribution_needs_two_categories():
    cat = Catalog(
        [
            course("ENGRD 2700", 4),
            course("ENGRD 2720", 4),
            course("ENGRD 2020", 4),
            course("CS 2110", 4, cross=["ENGRD 2110"]),
            course("ENGRD 2110", 4, cross=["CS 2110"]),
        ]
    )
    dist = Requirement(
        id="dist",
        label="dist",
        kind="courses",
        courses=["ENGRD 2110", "ENGRD 2700", "ENGRD 2720", "ENGRD 2020"],
        count=2,
        groups=[
            RequirementGroup(id="computing", label="c", courses=["ENGRD 2110"]),
            RequirementGroup(id="probability", label="p", courses=["ENGRD 2700", "ENGRD 2720"]),
            RequirementGroup(id="mechanics", label="m", courses=["ENGRD 2020"]),
        ],
        min_groups=2,
    )
    same = [place("ENGRD 2700"), place("ENGRD 2720")]
    assert statuses(same, program(dist), cat)["dist"].status == "missing"
    # CS 2110 counts through its ENGRD 2110 cross-listing, in scientific computing
    assert (
        statuses([place("CS 2110"), place("ENGRD 2700")], program(dist), cat)["dist"].status
        == "done"
    )


def test_an_engineering_communication_option_cant_also_count_as_liberal_studies():
    cat = Catalog(
        [course("COMM 3020", attributes=["SSC-AS"]), course("ENGRC 3500", attributes=["CE-EN"])]
    )
    comm = Requirement(
        id="comm",
        label="comm",
        kind="courses",
        courses=["COMM 3020", "ENGRC 3500"],
        count=1,
        double_count=["ls"],
        double_count_except={"ls": ["COMM 3020"]},
    )
    ls = Requirement(
        id="ls",
        label="ls",
        kind="filter",
        filter=CourseFilter(attributes_any=["SSC-AS", "CE-EN"]),
        count=1,
        double_count=["comm"],
    )
    st = statuses([place("COMM 3020")], program(comm, ls), cat)
    assert [st["comm"].status, st["ls"].status].count("missing") == 1
    st = statuses([place("ENGRC 3500")], program(comm, ls), cat)
    assert st["comm"].status == "done" and st["ls"].status == "done"


def test_credit_total_counts_every_course_including_open_slots():
    cat = Catalog([course("CS 1110", 4), course("PE 1100", 1), course("MATH 1910", 4)])
    total = Requirement(
        id="total",
        label="10 credits",
        kind="total_credits",
        filter=CourseFilter(min_level=1100, exclude_subjects=["PE"]),
        credits=10,
    )
    plan = [place("CS 1110", credits=4), place("PE 1100", credits=1), place("MATH 1910", credits=4)]
    st = statuses(plan, program(total), cat)["total"]
    assert (st.status, st.credits, st.credits_needed) == ("missing", 8, 10)
    slot = Placement(
        id="s", term="SP27", slot="total", slot_label="Elective", credits=3, status="planned"
    )
    assert statuses(plan + [slot], program(total), cat)["total"].status == "planned"
    # the greedy fallback reports the same total
    greedy = {r.id: r for r in greedy_audit(plan, program(total), cat).requirements}
    assert greedy["total"].credits == 8


def test_starter_plan_fills_requirements_then_credits():
    cat = Catalog([course("ECON 1110", attributes=["SSC-AS"])])
    ls = Requirement(
        id="ls",
        label="LS",
        kind="filter",
        filter=CourseFilter(attributes_any=["SSC-AS"]),
        count=2,
    )
    total = Requirement(
        id="total", label="12 credits", kind="total_credits", filter=CourseFilter(), credits=12
    )
    out = seed_slots([place("ECON 1110")], TERMS, "FA25", program(ls, total), cat)
    slots = [p for p in out if not p.course]
    assert sum(p.slot == "ls" for p in slots) == 1
    assert sum(p.credits for p in out) >= 12
    assert {p.slot_label for p in slots if p.slot == "total"} == {"Elective"}


# forbidden overlaps: "students will not receive credit for both" ------------------------


def test_overlap_text_in_each_roster_format():
    assert overlap_pairs("MATH 2210, MATH 2940") == {("MATH 2210", "MATH 2940")}
    group = (
        "Forbidden Overlap: due to an overlap in content, students will receive credit for "
        "only one course in the following group: ECON 3280, ECON 4280, ILRLE 3280."
    )
    assert len(overlap_pairs(group)) == 3
    both = "Forbidden Overlap: ... no credit for both HADM 4385 and HADM 4350 or HADM 6350."
    assert overlap_pairs(both) == {("HADM 4385", "HADM 4350"), ("HADM 4385", "HADM 6350")}
    # a lecture and its lab are one item; they don't exclude each other
    labs = overlap_pairs("CHEM 2080 and CHEM 2081, CHEM 2150")
    assert labs == {("CHEM 2080", "CHEM 2150"), ("CHEM 2081", "CHEM 2150")}
    assert overlap_pairs("MATH 3340 and MATH 3360, nor for both MATH 3340 and MATH 4340") == {
        ("MATH 3340", "MATH 3360"),
        ("MATH 3340", "MATH 4340"),
    }
    # a conditional rule isn't an overlap
    assert overlap_pairs(
        "AEM 2100, MATH 1710. In addition, no credit for MATH 1710 if taken after ECON 3130"
    ) == {("AEM 2100", "MATH 1710")}


def overlap_catalog():
    linear = "MATH 2210, MATH 2940"
    return Catalog(
        [
            course("MATH 2210", 4).model_copy(update={"forbidden_overlaps": linear}),
            course("MATH 2940", 4).model_copy(update={"forbidden_overlaps": linear}),
            course("MATH 1920", 4),
        ]
    )


def test_overlapping_courses_earn_credit_once():
    cat = overlap_catalog()
    assert cat.overlaps("MATH 2210") == {"MATH 2940"}
    math = Requirement(
        id="math", label="math", kind="filter", filter=CourseFilter(subjects=["MATH"]), count=2
    )
    total = Requirement(
        id="total", label="12 credits", kind="total_credits", filter=CourseFilter(), credits=12
    )
    plan = [place(c, credits=4) for c in ("MATH 2210", "MATH 2940", "MATH 1920")]
    st = statuses(plan, program(math, total), cat)
    assert st["math"].status == "done"  # MATH 1920 and one linear algebra course
    assert (st["total"].status, st["total"].credits) == ("missing", 8)
    st = statuses(plan[:2], program(math), cat)
    assert st["math"].status == "missing"  # the two overlap: only one counts
    greedy = {r.id: r for r in greedy_audit(plan, program(math, total), cat).requirements}
    assert greedy["total"].credits == 8 and greedy["math"].status == "done"


def test_the_plan_warns_about_overlapping_courses():
    cat = overlap_catalog()
    plan = [place("MATH 2210", credits=4), place("MATH 2940", "SP26", credits=4, status="planned")]
    found = [v for v in validate(plan, TERMS, cat) if v.kind == "no_credit"]
    assert len(found) == 1 and not found[0].blocking
    assert found[0].placement_ids == ["MATH 2210", "MATH 2940"]


def test_a_course_never_needs_itself():
    from app.catalog.store import _without

    expr = AnyOf(items=[AllOf(items=[CourseReq(code="ECON 1110")]), CourseReq(code="JAPAN 4421")])
    assert _without(expr, {"JAPAN 4421"}) == CourseReq(code="ECON 1110")
    assert _without(CourseReq(code="PMA 2300"), {"PMA 3300", "PMA 2300"}) is None


# the real roster ------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def roster():
    snapshot = sorted((ROOT / "snapshots").iterdir())[-1]
    return Catalog.load(snapshot, ROOT / "prereqs", ROOT / "prereq_equivalents.yaml")


def test_cs_4300_takes_info_2950_instead_of_the_math(roster):
    for code in ("CS 4300", "INFO 4300"):
        prereqs = roster.get(code).prereqs
        assert satisfied(prereqs, {"INFO 2950", "CS 2110"}, set())
        assert satisfied(prereqs, {"MATH 2940", "CS 2800", "CS 2110"}, set())
        assert not satisfied(prereqs, {"MATH 2940", "CS 2110"}, set())


def test_permission_doesnt_waive_cs_3700(roster):
    assert not satisfied(roster.get("CS 3700").prereqs, {"CS 2110"}, set())
    assert satisfied(roster.get("CS 3700").prereqs, {"CS 2110", "CS 2800"}, set())


def test_every_prerequisite_equivalent_is_backed_by_the_roster(roster):
    # a forbidden overlap (same material); MATH 1910's description names MATH 1110
    documented = {("MATH 1910", "MATH 1110")}
    for code, covers in roster.prereq_equivalents.items():
        for other in covers:
            assert other in roster.overlaps(code) or (code, other) in documented, (code, other)


def test_named_courses_count_on_their_list_before_an_elective():
    # CS 3110 and CS 3410 could make the elective whole, but the core names them; the
    # elective is the one an open slot can fill, so that's where the gap shows
    cat = Catalog([course("CS 3110", 4), course("CS 3410", 4), course("CS 4820", 4)])
    core = Requirement(
        id="core", label="Core", kind="courses", courses=["CS 3110", "CS 3410", "CS 4820"]
    )
    tech = Requirement(
        id="tech", label="Tech", kind="filter", filter=CourseFilter(subjects=["CS"]), count=2
    )
    plan = [place("CS 3110"), place("CS 3410")]
    st = statuses(plan, program(core, tech), cat)
    assert st["core"].filled == ["CS 3110", "CS 3410"] and st["tech"].filled == []
    out = seed_slots(plan, TERMS, "FA25", program(core, tech), cat)
    assert sorted(p.slot for p in out if not p.course) == ["core", "tech", "tech"]


def test_the_ba_takes_either_calculus_and_any_linear_algebra(roster):
    rules = load_program("cs-as", "2024-25", ROOT / "requirements")
    for history in (
        ["MATH 1110", "MATH 1120", "MATH 2210"],
        ["MATH 1910", "MATH 1920", "MATH 2940"],
        ["MATH 1110", "MATH 1920", "MATH 2310"],
    ):
        plan = [place(c, credits=4) for c in history]
        assert statuses(plan, rules, roster)["math"].status == "done", history
    plan = [place(c, credits=4) for c in ("MATH 1110", "MATH 1120")]
    assert statuses(plan, rules, roster)["math"].status != "done"


def test_the_ba_shares_the_engineering_cs_rules_except_math():
    def leaves(major):
        rules = load_set(ROOT / "requirements" / major / "2024-25.yaml")
        return {r.id: r for top in rules.requirements for r in top.walk()}

    eng, ba = leaves("cs-major-eng"), leaves("cs-major-as")
    for rid in ("core", "e4000", "practicum", "tech", "ext", "aae"):
        assert ba[rid].model_dump(exclude={"double_count", "notes"}) == eng[rid].model_dump(
            exclude={"double_count", "notes"}
        ), rid
    # nothing in the BA may name a rule that only Engineering has
    ids = set(ba)
    assert all(other in ids for r in ba.values() for other in r.double_count)


def test_starter_slots_follow_prerequisites_and_level():
    def needs(code, before=None, credits=4):
        c = course(code, credits)
        return c.model_copy(update={"prereqs": CourseReq(code=before)}) if before else c

    cat = Catalog(
        [
            needs("CS 1110"),
            needs("CS 2110", "CS 1110"),
            needs("CS 3110", "CS 2110"),
            needs("CS 4820"),
        ]
    )
    core = Requirement(
        id="core", label="Core", kind="courses", courses=["CS 1110", "CS 2110", "CS 3110"]
    )
    e4000 = Requirement(
        id="e4000",
        label="4000+",
        kind="filter",
        filter=CourseFilter(subjects=["CS"], min_level=4000),
    )
    terms = ["FA25", "SP26", "FA26", "SP27", "FA27", "SP28"]
    out = seed_slots([], terms, "FA25", program(core, e4000), cat)
    # each core course a term after the one it needs; nothing goes in the current term
    assert sorted(terms.index(p.term) for p in out if p.slot == "core") == [1, 2, 3]
    # a 4000-level elective from the third year
    assert [p.term for p in out if p.slot == "e4000"][0] in ("FA27", "SP28")


def test_a_course_fills_the_specific_rule_before_a_catch_all():
    # ENGRI 1101 could be the intro-to-engineering course or any elective; with nothing
    # else to fill either, it goes to the rule only it can meet
    cat = Catalog([course("ENGRI 1101")])
    intro = Requirement(
        id="intro", label="ENGRI", kind="filter", filter=CourseFilter(subjects=["ENGRI"])
    )
    elective = Requirement(
        id="any", label="Elective", kind="filter", filter=CourseFilter(min_level=1100)
    )
    st = statuses([place("ENGRI 1101")], program(elective, intro), cat)
    assert st["intro"].status == "done" and st["any"].status == "missing"


# students who started before Fall 2024 ------------------------------------------------


def test_a_fall_2023_arts_student_gets_the_2023_24_rules(roster, monkeypatch):
    from app.config import get_settings
    from app.requirements.loader import load_program, rules_year_for

    monkeypatch.setattr(get_settings(), "data_dir", DATA.parent)  # the real rule files

    assert rules_year_for("cs-as", "FA23") == "2023-24"
    assert rules_year_for("cs-eng", "FA23") == "2023-24"
    # nothing before Fall 2023 is encoded
    assert rules_year_for("cs-eng", "FA22") is None
    program = load_program("cs-as", "2023-24", DATA)
    taken = [
        ("FA23", "CS 1110"), ("FA23", "MATH 1110"), ("FA23", "MATH 1120"), ("FA23", "MATH 2210"),
        ("SP24", "CS 2110"), ("SP24", "CS 2800"), ("FA24", "CS 3110"), ("SP25", "CS 3780"),
        ("SP25", "CS 4820"), ("SP25", "STSCI 3080"), ("FA25", "CS 3410"), ("FA25", "CS 3700"),
        ("FA25", "CS 4410"), ("FA25", "CS 4320"), ("SP26", "CS 4787"), ("SP26", "ASTRO 2211"),
    ]  # fmt: skip
    plan = [place(c, t, credits=roster.get(c).credits) for t, c in taken]
    st = {r.id: r for r in audit(plan, program, roster).requirements}
    # five-course core with no CS 3700/3780 slot, so this core is complete
    assert st["core"].status == "done"
    # STSCI 3080 is BTRY 3080's cross-listing: the probability course
    assert st["probability"].status == "done"
    # with three technical electives (STSCI 3080, CS 4787, ASTRO 2211), CS 3700 and CS
    # 3780 fill the CS electives with CS 4320, as on the department's checklist
    assert st["e4000"].status == "done" and st["tech"].status == "done"
    assert st["math"].status == "done"


def test_rule_files_reject_unknown_keys():
    import pytest
    from pydantic import ValidationError

    # "label: MATH 1110, 1120" in an inline YAML map splits into a stray key
    bad = {
        "id": "m",
        "label": "MATH 1110",
        "kind": "courses",
        "courses": ["MATH 1110"],
        "1120": None,
    }
    with pytest.raises(ValidationError):
        Requirement.model_validate(bad)


def test_engineering_liberal_studies_before_fall_2024_has_no_group_7_minimum():
    import yaml

    rules = yaml.safe_load((DATA / "engineering" / "2023-24.yaml").read_text())
    ls = Requirement.model_validate(next(r for r in rules["requirements"] if r["id"] == "ls"))
    cat = Catalog(
        [
            course("HIST 2000", attributes=["HA-AG"]),
            course("PHIL 2100", attributes=["ETM-AS"]),
            course("ECON 1110", attributes=["SSC-AS"]),
            course("PSYCH 1101", attributes=["SSC-AS"]),
            course("ENGL 2000", attributes=["ALC-AS"]),
            # Social Difference sits in Group 1 under this policy, not a group of its own
            course("AAS 1100", attributes=["SCD-AS"]),
        ]
    )
    plan = [
        place(c)
        for c in ("HIST 2000", "PHIL 2100", "ECON 1110", "PSYCH 1101", "ENGL 2000", "AAS 1100")
    ]
    # six courses from four groups, two at 2000+, and nothing from Group 7: enough here,
    # though Fall 2024 entrants also need 3 credits of race and equity
    assert statuses(plan, program(ls), cat)["ls"].status == "done"


# one course in two categories (the A&S distribution) ----------------------------------

AS_CAT = Catalog(
    [
        course("HIST 2500", attributes=["ALC-AS", "HST-AS"]),
        course("PHIL 2400", attributes=["ALC-AS", "HST-AS", "ETM-AS"]),
        course("ECON 1110", attributes=["SSC-AS"]),
        course("PHIL 1100", attributes=["ETM-AS"]),
    ]
)


def distribution(categories, count, per=2):
    return Requirement(
        id="dist",
        label="Distribution",
        kind="filter",
        filter=CourseFilter(attributes_any=[f"{c}-AS" for c in categories]),
        count=count,
        groups=[
            RequirementGroup(id=c.lower(), label=c, attributes_any=[f"{c}-AS"]) for c in categories
        ],
        min_groups=len(categories),
        groups_per_course=per,
    )


def test_a_course_can_cover_two_categories():
    # HIST 2500 is both ALC and HST, so two courses cover three categories
    plan = [place("HIST 2500"), place("ECON 1110")]
    assert (
        statuses(plan, program(distribution(["ALC", "HST", "SSC"], 2)), AS_CAT)["dist"].status
        == "done"
    )
    # with one category per course (the Engineering rule) the same plan falls short
    rule = distribution(["ALC", "HST", "SSC"], 2, per=1)
    assert statuses(plan, program(rule), AS_CAT)["dist"].status == "missing"


def test_a_course_covers_at_most_two_categories():
    # PHIL 2400 carries ALC, HST and ETM but may only count for two of them
    rule = distribution(["ALC", "HST", "ETM", "SSC"], 2)
    plan = [place("PHIL 2400"), place("ECON 1110")]
    assert statuses(plan, program(rule), AS_CAT)["dist"].status == "missing"
    # a third course that brings the missing category completes it
    rule = distribution(["ALC", "HST", "ETM", "SSC"], 3)
    plan = [place("PHIL 2400"), place("ECON 1110"), place("PHIL 1100")]
    assert statuses(plan, program(rule), AS_CAT)["dist"].status == "done"


def test_an_open_slot_can_cover_two_categories():
    rule = distribution(["ALC", "HST", "SSC", "ETM"], 2)
    slot = Placement(id="s", term="SP27", slot="dist", slot_label="D", credits=3, status="planned")
    plan = [place("HIST 2500"), slot]
    assert statuses(plan, program(rule), AS_CAT)["dist"].status == "planned"


def test_groups_per_course_must_be_positive():
    with pytest.raises(ValueError):
        distribution(["ALC"], 1, per=0)


def test_only_two_courses_may_cover_two_categories():
    # three two-category courses would cover six categories, but only two may double up
    cat = Catalog(
        [
            course("A 2000", attributes=["ALC-AS", "HST-AS"]),
            course("B 2000", attributes=["ETM-AS", "SSC-AS"]),
            course("C 2000", attributes=["SCD-AS", "GLC-AS"]),
        ]
    )
    categories = ["ALC", "HST", "ETM", "SSC", "SCD", "GLC"]
    rule = distribution(categories, 3).model_copy(update={"max_multi_group_courses": 2})
    plan = [place("A 2000"), place("B 2000"), place("C 2000")]
    assert statuses(plan, program(rule), cat)["dist"].status == "missing"
    # without the limit the same three courses are enough
    assert statuses(plan, program(distribution(categories, 3)), cat)["dist"].status == "done"
    # with two doubled up, a fourth course for the last category completes it
    cat = Catalog(
        [
            *(cat.get(c) for c in ("A 2000", "B 2000")),
            course("C 2000", attributes=["SCD-AS"]),
            course("D 2000", attributes=["GLC-AS"]),
        ]
    )
    rule = distribution(categories, 4).model_copy(update={"max_multi_group_courses": 2})
    plan = [place(c) for c in ("A 2000", "B 2000", "C 2000", "D 2000")]
    assert statuses(plan, program(rule), cat)["dist"].status == "done"


AS_HISTORY = {
    # the CS major's own courses: CS 1110, CS 2800 and MATH 1110 are SMR-AS
    "FA24": ["CS 1110", "MATH 1110", "PHYS 1112"],
    "SP25": ["CS 2110", "MATH 1120", "ECON 1110"],
    "FA25": ["CS 2800", "MATH 2210", "PSYCH 1101"],
}


def _as_plan(roster, history):
    rules = load_program("cs-as", "2024-25", ROOT / "requirements")
    plan = [
        place(code, term=term, credits=roster.get(code).credits)
        for term, codes in history.items()
        for code in codes
    ]
    return statuses(plan, rules, roster)


def test_the_ba_college_rules_read_the_roster(roster):
    st = _as_plan(roster, AS_HISTORY)
    # SMR, PHS and SSC are covered, seven categories are not
    assert st["as-distribution"].status == "missing"
    filled = st["as-distribution"].filled
    assert filled and all(any(a.endswith("-AS") for a in roster.get(c).attributes) for c in filled)
    # nothing for the language yet: only the student's word for the sequence
    assert st["as-language"].status == "flagged"
    assert st["as-language-flopi"].status == "missing"
    assert st["as-total-credits"].status == "missing"
    assert st["as-pe"].status == "flagged"


def test_an_intermediate_language_course_meets_the_language_rule(roster):
    st = _as_plan(roster, {**AS_HISTORY, "SP26": ["SPAN 2090"]})
    assert st["as-language"].status == "done"
    # Elementary Spanish is FL-AG but not FLOPI-AS, so it doesn't count
    st = _as_plan(roster, {**AS_HISTORY, "SP26": ["SPAN 1210"]})
    assert st["as-language-flopi"].status == "missing"


def test_major_courses_count_toward_distribution_too(roster):
    st = _as_plan(roster, AS_HISTORY)
    assert "CS 2800" in st["as-distribution"].filled
    assert "CS 2800" in st["core-2800"].filled


def test_both_ba_years_share_the_college_rules():
    def rules(year):
        data = yaml.safe_load(
            (ROOT / "requirements" / "arts-sciences" / f"{year}.yaml").read_text()
        )
        return data["requirements"]

    assert rules("2023-24") == rules("2024-25")
