"""Read Cornell's unofficial transcript (the PDF from Student Center) into rows the
student confirms, like pasted history. Only course codes, terms and credits are kept:
the file, grades and personal details are never stored.

The text layer looks like:

    FALL 2023
    Program:  Arts and Sciences
    CS   1110 INTRO COMPUTING: DESIGN & DEV 4.00 A
     COURSE TOPIC(S): ...
    ...
    ---- Test Credits Detailed ----
    Mathematics: Calculus BC
    (5.00)
    Transferred to Term 2023FA
    MATH 1110 Calculus I 4.00   S
"""

import io
import re
import uuid

from pypdf import PdfReader

from app.catalog.store import Catalog
from app.onboarding import normalize_term
from app.schemas.onboarding import Issue, IssueOption, ParsedCourse, TranscriptResult

TERM = re.compile(r"^\s*(FALL|SPRING|SUMMER|WINTER)\s+(20\d{2})\s*$")
COURSE = re.compile(
    r"^\s*([A-Z]{2,7})\s+(\d{4})\s+(.*?)\s+(\d+\.\d{2})(?:\s+([A-Z][A-Z+\-]*))?\s*$"
)
PROGRAM = re.compile(r"^\s*Program:\s*(.+?)\s*$")
TEST_SECTION = re.compile(r"-+\s*Test Credits", re.I)
TEST_TERM = re.compile(r"Transferred to Term\s+(20\d{2})(FA|SP|SU|WI)", re.I)
SCORE = re.compile(r"^\s*\(\d+\.\d{2}\)\s*$")
# no credit: withdrawn, failed, unsatisfactory, incomplete, no grade
NO_CREDIT = {"W", "F", "U", "UX", "INC", "NG"}
PROGRAMS = {"Arts and Sciences": "cs-as", "Engineering": "cs-eng"}
SEASON_NAMES = {"FA": "fall", "SP": "spring", "SU": "summer", "WI": "winter"}


class TranscriptError(ValueError):
    pass


def transcript_text(pdf: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:  # pypdf raises several kinds for broken files
        raise TranscriptError("That file couldn't be opened as a PDF.") from e
    if "TRANSCRIPT" not in text.upper() or not any(TERM.match(x) for x in text.splitlines()):
        raise TranscriptError(
            "That doesn't look like a Cornell unofficial transcript. Download it from "
            "Student Center, or paste your courses instead."
        )
    return text


def parse_transcript(text: str, catalog: Catalog) -> TranscriptResult:
    rows: list[ParsedCourse] = []
    skipped: list[str] = []
    unread: list[str] = []
    term = note = entering = program = test_name = None
    in_tests = False
    lines = text.splitlines()

    for i, line in enumerate(lines):
        if TEST_SECTION.search(line):
            in_tests, term, note = True, None, None
            continue
        if not in_tests and (m := TERM.match(line)):
            term, note = normalize_term(m.group(1), m.group(2))
            entering = entering or term
            continue
        if not in_tests and (m := PROGRAM.match(line)):
            program = PROGRAMS.get(m.group(1), program)
            continue
        if in_tests:
            if SCORE.match(line) and i > 0:
                test_name = lines[i - 1].strip()
                continue
            if m := TEST_TERM.search(line):
                season = SEASON_NAMES[m.group(2).upper()]
                term, _ = normalize_term(season, m.group(1))
                note = f"Credit by exam: {test_name}" if test_name else "Credit by exam"
                continue
        m = COURSE.match(line)
        if not m:
            continue
        subject, number, _title, earned, grade = m.groups()
        code = f"{subject} {number}"
        if term is None:
            unread.append(line.strip())
            continue
        if grade in NO_CREDIT:
            skipped.append(f"{code} ({_term_name(term)}): grade {grade}, no credit")
            continue
        rows.append(_row(code, term, float(earned), note, catalog))

    return TranscriptResult(
        courses=rows, unread=unread, skipped=skipped, entering_term=entering, program=program
    )


def _row(code: str, term: str, earned: float, note: str | None, catalog: Catalog) -> ParsedCourse:
    course = catalog.get(code)
    row = ParsedCourse(id=uuid.uuid4().hex[:8], raw=code, term=term, code=None, note=note)
    if course is None:
        row.issue = Issue(
            kind="unknown_course",
            message=f"{code} isn't in the roster we have. Pick the course it is, or skip it.",
            options=[IssueOption(label="Skip it", value="drop")],
        )
        return row
    row.code, row.title = course.code, course.title
    # credits earned are what the transcript says (variable-credit courses differ from the
    # roster); a course in progress shows 0.00 earned, so it takes the roster's
    row.credits = int(earned + 0.5) if earned > 0 else course.credits
    return row


def _term_name(term: str) -> str:
    return f"{'Fall' if term.startswith('FA') else 'Spring'} 20{term[2:]}"
