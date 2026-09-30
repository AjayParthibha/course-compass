"""Rough regex parser for the roster's free-text prerequisite strings.

Handles the common shapes ("CS 2110 or CS 2112", "A and B; or C"). Anything it
can't place becomes a Flag. Reviewed parses in data/prereqs/ override this.
"""

import re

from app.schemas.courses import AllOf, AnyOf, CourseReq, Flag, PrereqExpr

CODE = re.compile(r"\b([A-Z]{2,5})\s*(\d{4})\b")
BARE_NUMBER = re.compile(r"(?:\bor|\band|,|/)\s*(\d{4})\b")
LABEL = re.compile(
    r"^\s*(prerequisites?|corequisites?|prereq|coreq)\s*(or corequisite)?\s*:\s*", re.I
)
MEANINGFUL = re.compile(r"permission|standing|consent|enrollment|majors?|grade", re.I)


def extract_codes(text: str) -> list[str]:
    codes: list[str] = []
    last_subject = None
    pos = 0
    for m in CODE.finditer(text):
        # pick up bare numbers like "CS 2110 or 2112" between the previous code and this one
        if last_subject:
            for bare in BARE_NUMBER.finditer(text, pos, m.start()):
                codes.append(f"{last_subject} {bare.group(1)}")
        last_subject = m.group(1)
        codes.append(f"{m.group(1)} {m.group(2)}")
        pos = m.end()
    if last_subject:
        for bare in BARE_NUMBER.finditer(text, pos):
            codes.append(f"{last_subject} {bare.group(1)}")
    return list(dict.fromkeys(codes))


def _simplify(op: str, items: list[PrereqExpr]) -> PrereqExpr | None:
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    return AnyOf(items=items) if op == "any" else AllOf(items=items)


def _parse_clause(clause: str, concurrent: bool) -> PrereqExpr | None:
    codes = extract_codes(clause)
    if not codes:
        text = clause.strip(" .")
        return Flag(text=text) if text and MEANINGFUL.search(text) else None

    def reqs(chunk: str) -> list[PrereqExpr]:
        return [CourseReq(code=c, concurrent=concurrent) for c in extract_codes(chunk)]

    has_or = re.search(r"\bor\b", clause)
    has_and = re.search(r"\band\b|,", clause)
    if has_or and has_and:
        pieces = [p for p in re.split(r"\band\b|,", clause) if extract_codes(p)]
        return _simplify("all", [_simplify("any", reqs(p)) for p in pieces])
    return _simplify("any" if has_or else "all", reqs(clause))


def parse_text(text: str, concurrent: bool = False) -> PrereqExpr | None:
    text = LABEL.sub("", text or "").strip()
    if not text:
        return None
    parts = text.split(";")
    top = "any" if any(p.strip().lower().startswith("or ") for p in parts[1:]) else "all"
    parsed = []
    for part in parts:
        part = re.sub(r"^\s*or\s+", "", part, flags=re.I)
        expr = _parse_clause(part, concurrent)
        if expr is not None:
            parsed.append(expr)
    return _simplify(top, parsed)


def parse(prereq_text: str, coreq_text: str = "") -> PrereqExpr | None:
    exprs = [e for e in (parse_text(prereq_text), parse_text(coreq_text, True)) if e]
    return _simplify("all", exprs)
