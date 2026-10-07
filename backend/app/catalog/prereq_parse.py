"""Rough regex parser for the roster's free-text prerequisite strings.

Handles the common shapes ("CS 2110 or CS 2112", "A and B; or C", "A, B, or C",
"probability (e.g. BTRY 3080, MATH 4710)"). Anything it can't place becomes a
Flag. Reviewed parses in data/prereqs/ override this.
"""

import re

from app.schemas.courses import AllOf, AnyOf, CourseReq, Flag, PrereqExpr

CODE = re.compile(r"\b([A-Z]{2,5})\s*(\d{4})\b")
BARE_NUMBER = re.compile(r"(?:\bor|\band|,|/)\s*(\d{4})\b")
LABEL = re.compile(
    r"^\s*(prerequisites?|corequisites?|prereq|coreq)\s*(or corequisite)?\s*:\s*", re.I
)
MEANINGFUL = re.compile(r"permission|standing|consent|enrollment|majors?|grade", re.I)
# "Recommended prerequisite: X" and everything after it is advice, not a requirement
RECOMMENDED = re.compile(r"(strongly\s+)?recommended(\s+(pre|co)requisites?)?\s*:", re.I)
GROUP = re.compile(r"\(([^()]*)\)")
TOKEN = re.compile(r"@(\d+)@")
SLASH = re.compile(r"(?<=\d)\s*/\s*(?=[A-Z]{2,5}\s*\d{4}|\d{4})")
# "A, B, or C": an Oxford-comma list that ends in a course is a list of alternatives
OXFORD_OR = re.compile(r",\s*or\s+(@\d+@|[A-Z]{2,5}\s*\d{4})")
ONE_OF = re.compile(r"\bsuch as\b|\bone of\b", re.I)


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


def expand_bare_numbers(text: str) -> str:
    """Write "CS 2110 or 2112" as "CS 2110 or CS 2112" so splitting on "and" or a
    comma never strands a number without its subject."""
    out, pos = [], 0
    for m in BARE_NUMBER.finditer(text):
        prior = list(CODE.finditer(text, 0, m.start(1)))
        if prior:
            out.append(text[pos : m.start(1)] + f"{prior[-1].group(1)} ")
            pos = m.start(1)
    return "".join(out) + text[pos:]


def _simplify(op: str, items: list[PrereqExpr]) -> PrereqExpr | None:
    items = [e for i, e in enumerate(items) if e not in items[:i]]
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    return AnyOf(items=items) if op == "any" else AllOf(items=items)


def _mask_groups(clause: str, concurrent: bool) -> tuple[str, list[PrereqExpr]]:
    """Swap each parenthesised list of courses for a placeholder token.

    "(e.g. BTRY 3080, ECON 3130, MATH 4710)" names examples of one requirement, so
    it becomes a single any-of. "(or CS 2112)" just continues the list around it and
    is unwrapped. Other parentheses are dropped so their commas don't split clauses.
    """
    groups: list[PrereqExpr] = []

    def replace(m: re.Match) -> str:
        inner = m.group(1)
        if not extract_codes(inner) or re.search(r"recommended", inner, re.I):
            return " "
        if re.match(r"\s*or\b", inner, re.I):
            return f" {inner} "
        reqs = [CourseReq(code=c, concurrent=concurrent) for c in extract_codes(inner)]
        groups.append(_simplify("any", reqs))
        return f" @{len(groups) - 1}@ "

    return GROUP.sub(replace, clause), groups


def _parse_clause(clause: str, concurrent: bool) -> PrereqExpr | None:
    masked, groups = _mask_groups(clause, concurrent)
    masked = SLASH.sub(" or ", masked)

    def reqs(chunk: str) -> list[PrereqExpr]:
        out: list[PrereqExpr] = []
        pos = 0
        for m in TOKEN.finditer(chunk):
            out += [
                CourseReq(code=c, concurrent=concurrent)
                for c in extract_codes(chunk[pos : m.start()])
            ]
            out.append(groups[int(m.group(1))])
            pos = m.end()
        out += [CourseReq(code=c, concurrent=concurrent) for c in extract_codes(chunk[pos:])]
        return out

    if not reqs(masked):
        text = clause.strip(" .")
        return Flag(text=text) if text and MEANINGFUL.search(text) else None

    # "and" always separates requirements. Inside each piece, "or" makes the
    # piece a list of alternatives when it's an Oxford-comma or "such as" list;
    # otherwise commas still mean "and" ("CS 2800, MATH 2210 or MATH 2940").
    parts: list[PrereqExpr] = []
    for piece in re.split(r"\band\b", masked):
        if not re.search(r"\bor\b", piece):
            for chunk in piece.split(","):
                parts += reqs(chunk)
        elif OXFORD_OR.search(piece) or ONE_OF.search(piece):
            parts += [e for e in [_simplify("any", reqs(piece))] if e]
        else:
            parts += [e for e in (_simplify("any", reqs(c)) for c in piece.split(",")) if e]
    return _simplify("all", parts)


def parse_text(text: str, concurrent: bool = False) -> PrereqExpr | None:
    text = expand_bare_numbers(LABEL.sub("", text or "").strip())
    if m := RECOMMENDED.search(text):
        text = text[: m.start()].strip()
    if not text:
        return None
    # "A; B; or C" is (A and B) or C: a part starting with "or" opens a new alternative
    alternatives: list[list[PrereqExpr]] = [[]]
    for part in text.split(";"):
        if re.match(r"^\s*or\s+", part, re.I) and alternatives[-1]:
            alternatives.append([])
        part = re.sub(r"^\s*or\s+", "", part, flags=re.I)
        expr = _parse_clause(part, concurrent)
        if expr is not None:
            alternatives[-1].append(expr)
    return _simplify("any", [e for alt in alternatives if (e := _simplify("all", alt))])


def parse(prereq_text: str, coreq_text: str = "") -> PrereqExpr | None:
    exprs = [e for e in (parse_text(prereq_text), parse_text(coreq_text, True)) if e]
    return _simplify("all", exprs)
