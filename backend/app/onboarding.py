"""Parse pasted course history into rows the student confirms.

Regex only for now. Track C adds an LLM fallback for text this can't read.
"""

import re
import uuid

from app.catalog.store import Catalog, normalize_code
from app.schemas.onboarding import Issue, IssueOption, ParsedCourse

TERM = re.compile(r"\b(FA|SP|Fall|Spring)\s*'?(\d{2}|\d{4})\b", re.I)
COURSE = re.compile(r"\b([A-Z]{2,5})\s*(\d{3}[0-9xX])\b")
CREDITS = re.compile(r"\(?\s*(\d)\s*(?:cr|credits?)\s*\)?", re.I)
AP = re.compile(r"^\s*AP\s+(.+?)\s+(\d)\s*$", re.I)


def normalize_term(season: str, year: str) -> str:
    s = "FA" if season.lower().startswith("f") else "SP"
    return f"{s}{year[-2:]}"


def parse_history(text: str, catalog: Catalog) -> list[ParsedCourse]:
    rows: list[ParsedCourse] = []
    seen: dict[str, ParsedCourse] = {}
    term = None

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
            term = normalize_term(m.group(1), m.group(2))
        rest = line[m.end() :] if m else line

        for cm in COURSE.finditer(rest):
            raw = f"{cm.group(1)} {cm.group(2)}"
            after = rest[cm.end() : cm.end() + 12]
            cr = CREDITS.match(after.strip())
            stated_credits = int(cr.group(1)) if cr else None
            rows.append(_row(raw, term, stated_credits, catalog, seen))

        if re.search(r"\bFWS\b", rest):
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
    return rows


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
