"""Parse pasted course history into rows the student confirms.

Regex first. Lines it can't read go to the model when there's an API key
(app/onboarding_model.py), and anything the model reads comes back for the student to
confirm.
"""

import re
import uuid

from app.catalog.store import Catalog, normalize_code
from app.schemas.onboarding import Issue, IssueOption, ParsedCourse

SEASON = r"(fall|spring|summer|winter|fa|sp|su|wi)"
# "FA25", "Fall '25", "Spring 2026", and Student Center's year-first "2025 Fall"
TERM = re.compile(rf"\b{SEASON}\s*'?(20\d{{2}}|\d{{2}})\b|\b(20\d{{2}})\s+{SEASON}\b", re.I)
# any case ("cs 2800"); only subjects the roster has count, so words aren't read as codes
COURSE = re.compile(r"\b([A-Za-z]{2,7})\s*(\d{3}[0-9xX])\b")
CREDITS = re.compile(r"\(?\s*(\d)\s*(?:cr|credits?)\s*\)?", re.I)
AP = re.compile(r"^\s*AP\s+(.+?)\s+(\d)\s*$", re.I)
SEASONS = {"fa": "Fall", "sp": "Spring", "su": "Summer", "wi": "Winter"}


def normalize_term(season: str, year: str) -> tuple[str, str | None]:
    """The plan term, and for a summer or winter session (plans have only fall and
    spring) a note saying where it went: summer with the spring before it, winter
    session (January) with the fall before it."""
    name = SEASONS[season.lower()[:2]]
    yy = int(year[-2:])
    if name == "Summer":
        return f"SP{yy:02d}", f"Taken in Summer 20{yy:02d}; counted with Spring 20{yy:02d}"
    if name == "Winter":
        return (
            f"FA{yy - 1:02d}",
            f"Taken in Winter 20{yy:02d}; counted with Fall 20{yy - 1:02d}",
        )
    return f"{name[:2].upper()}{yy:02d}", None


def parse_history(text: str, catalog: Catalog) -> tuple[list[ParsedCourse], list[str]]:
    """The courses read from pasted history, and the lines that look like they name a
    course but couldn't be read."""
    rows: list[ParsedCourse] = []
    unread: list[str] = []
    seen: dict[str, ParsedCourse] = {}
    subjects = {code.split()[0] for code in catalog.courses}
    term = None
    note = None

    for line in text.splitlines():
        if not line.strip():
            continue
        ap = AP.match(line)
        if ap:
            rows.append(
                ParsedCourse(
                    id=_id(),
                    raw=line.strip(),
                    term=None,
                    code=None,
                    title=f"AP {ap.group(1)}",
                    issue=Issue(
                        kind="ap_credit",
                        message=f"AP {ap.group(1)} (score {ap.group(2)}). How should it count?",
                        options=[
                            IssueOption(label="Keep for total credits only", value="credits"),
                            IssueOption(label="Leave it out", value="drop"),
                        ],
                    ),
                )
            )
            continue

        m = TERM.search(line)
        if m:
            season, year = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
            term, note = normalize_term(season, year)
        rest = line[: m.start()] + " " + line[m.end() :] if m else line

        found = len(rows)
        for cm in COURSE.finditer(rest):
            if cm.group(1).upper() not in subjects:
                # a capitalised code we don't know ("ECNO 1110") is worth asking about; a
                # lowercase word or a year next to a number isn't
                if cm.group(1).isupper() and not re.fullmatch(r"20\d\d", cm.group(2)):
                    rows.append(_row(f"{cm.group(1)} {cm.group(2)}", term, None, catalog, seen))
                continue
            raw = f"{cm.group(1).upper()} {cm.group(2)}"
            after = rest[cm.end() : cm.end() + 12]
            cr = CREDITS.match(after.strip())
            stated_credits = int(cr.group(1)) if cr else None
            row = _row(raw, term, stated_credits, catalog, seen)
            row.note = note
            rows.append(row)

        if re.search(r"\bFWS\b", rest, re.I):
            rows.append(
                ParsedCourse(
                    id=_id(),
                    raw="FWS",
                    term=term,
                    code=None,
                    title="First-year writing seminar",
                    issue=Issue(
                        kind="unknown_course",
                        message="Which writing seminar was it? Enter the course code.",
                        options=[IssueOption(label="Skip it", value="drop")],
                    ),
                )
            )
        # a number that could be a course, but nothing read: say so rather than drop it
        if len(rows) == found and not m and re.search(r"\b(?!20\d\d\b)\d{4}\b", rest):
            unread.append(line.strip())
    return rows, unread


def _row(raw: str, term, stated_credits, catalog: Catalog, seen: dict) -> ParsedCourse:
    row = ParsedCourse(id=_id(), raw=raw, term=term, code=None)
    if raw[-1] in "xX":
        prefix = normalize_code(raw[:-1])
        matches = sorted(c for c in catalog.courses if c.startswith(prefix))
        row.issue = Issue(
            kind="ambiguous_code",
            message=f"You wrote {raw}. Which course was it?",
            options=[
                IssueOption(label=f"{c} · {catalog.get(c).title}", value=c) for c in matches[:6]
            ],
        )
        return row

    course = catalog.get(raw)
    if course is None:
        row.issue = Issue(
            kind="unknown_course",
            message=f"We couldn't find {raw} in the roster.",
            options=[IssueOption(label="Skip it", value="drop")],
        )
        return row

    row.code, row.title, row.credits = course.code, course.title, course.credits
    if stated_credits and stated_credits != course.credits:
        row.issue = Issue(
            kind="credit_mismatch",
            message=f"You listed {stated_credits} credits. The roster has {course.credits}.",
            options=[
                IssueOption(label=f"Use {course.credits} credits", value=str(course.credits)),
                IssueOption(
                    label=f"My transcript says {stated_credits}", value=str(stated_credits)
                ),
            ],
        )
    elif course.code in seen:
        row.issue = Issue(
            kind="duplicate",
            message=f"{course.code} appears more than once.",
            options=[
                IssueOption(label="Keep both (repeated course)", value="keep"),
                IssueOption(label="Remove this one", value="drop"),
            ],
        )
    seen[course.code] = row
    return row


def _id() -> str:
    return uuid.uuid4().hex[:8]
