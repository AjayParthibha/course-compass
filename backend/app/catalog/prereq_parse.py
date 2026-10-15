"""Rough regex parser for the roster's free-text prerequisite strings.

Handles the common shapes ("CS 2110 or CS 2112", "A and B; or C", "A, B, or C",
"A and B, or C and D", "MATH 2210-MATH 2220", "probability (e.g. BTRY 3080,
MATH 4710)"). Sentences are separate requirements; one ending in "recommended" is
advice and one starting "Corequisite:" may be taken alongside. Anything it can't
place becomes a Flag. Reviewed parses in data/prereqs/ override this.
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
OXFORD_CLOSE = re.compile(r"\s*or\s+(@\d+@|[A-Z]{2,5}\s*\d{4})")
EQUIVALENT = re.compile(r"\s*or\s+(the\s+)?equivalents?\b")
ONE_OF = re.compile(r"\bsuch as\b|\bone of\b", re.I)
AND = re.compile(r"\band\b")
# "MATH 2210-MATH 2220": a two-course sequence, both needed
PAIR = re.compile(r"\b([A-Z]{2,5})\s*(\d{4})\s*[-–]\s*([A-Z]{2,5})\s*(\d{4})\b")
# a sentence ending in "... recommended" is advice, not a requirement
ADVICE = re.compile(r"[^.]*\brecommended\s*(\.|$)", re.I)
# a sentence that names corequisites mid-text ("... Corequisite: CS 4121.")
COREQ = re.compile(r"\s*(pre-?requisites?\s+or\s+)?co-?requisites?\b", re.I)
# "for Computer Science majors: ... Prerequisites for others: ..."
AUDIENCE = re.compile(r"\b(students?|majors|others|programmers|designers)\s*(:|-)", re.I)


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
    kind = AnyOf if op == "any" else AllOf
    flat: list[PrereqExpr] = []
    for e in items:
        flat += e.items if isinstance(e, kind) else [e]
    items = [e for i, e in enumerate(flat) if e not in flat[:i]]
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    return kind(items=items)


def _as_concurrent(expr: PrereqExpr) -> PrereqExpr:
    if isinstance(expr, CourseReq):
        return expr.model_copy(update={"concurrent": True})
    if isinstance(expr, AllOf | AnyOf):
        return expr.model_copy(update={"items": [_as_concurrent(e) for e in expr.items]})
    return expr


def _is_joint(text: str) -> bool:
    """Whether the text needs two courses together ("A and B", "A-B")."""
    return bool(PAIR.search(text)) or sum(bool(extract_codes(p)) for p in AND.split(text)) >= 2


def _mask_groups(clause: str, concurrent: bool) -> tuple[str, list[PrereqExpr]]:
    """Swap each parenthesised list of courses, and each "A-B" pair, for a placeholder.

    "(e.g. BTRY 3080, ECON 3130, MATH 4710)" names examples of one requirement, so
    it becomes a single any-of; when some of the examples are pairs ("MATH 2210-MATH
    2220, or MATH 1920 and MATH 2940") each example is parsed on its own. A group that
    is one "and" clause ("MATH 4330 and either MATH 3340 or MATH 4340") is parsed as
    one. "(or CS 2112)" just continues the list around it and is unwrapped. Other
    parentheses are dropped so their commas don't split clauses.
    """
    groups: list[PrereqExpr] = []

    def token(expr: PrereqExpr | None) -> str:
        if expr is None:
            return " "
        groups.append(expr)
        return f" @{len(groups) - 1}@ "

    def replace(m: re.Match) -> str:
        inner = m.group(1)
        if not extract_codes(inner) or re.search(r"recommended", inner, re.I):
            return " "
        if re.match(r"\s*or\b", inner, re.I):
            return f" {inner} "
        items = [re.sub(r"^\s*or\b", "", i) for i in inner.split(",")]
        joint = [i for i in items if AND.search(i) or PAIR.search(i)]
        if AND.search(inner) and len(joint) < 2 and not OXFORD_OR.search(inner):
            return token(_parse_clause(inner, concurrent))
        if joint:
            options = [_parse_clause(i, concurrent) for i in items]
            return token(_simplify("any", [e for e in options if e and not isinstance(e, Flag)]))
        reqs = [CourseReq(code=c, concurrent=concurrent) for c in extract_codes(inner)]
        return token(_simplify("any", reqs))

    def pair(m: re.Match) -> str:
        codes = [f"{m.group(1)} {m.group(2)}", f"{m.group(3)} {m.group(4)}"]
        return token(AllOf(items=[CourseReq(code=c, concurrent=concurrent) for c in codes]))

    return PAIR.sub(pair, GROUP.sub(replace, clause)), groups


def _parse_clause(clause: str, concurrent: bool) -> PrereqExpr | None:
    masked, groups = _mask_groups(clause, concurrent)
    masked = ADVICE.sub(" ", SLASH.sub(" or ", masked))

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
        text = ADVICE.sub(" ", clause).strip(" .")
        return Flag(text=clause.strip(" .")) if text and MEANINGFUL.search(text) else None
    # sentences are separate requirements, except "Majors: A. Others: B." (either one)
    parts: list[PrereqExpr] = []
    audiences: list[PrereqExpr] = []
    for sentence in re.split(r"\.\s+", masked):
        expr = _parse_sentence(sentence, reqs)
        if expr is None:
            continue
        if COREQ.match(sentence):
            expr = _as_concurrent(expr)
        (audiences if AUDIENCE.search(sentence) else parts).append(expr)
    if len(audiences) > 1:
        parts.append(_simplify("any", audiences))
    else:
        parts += audiences
    return _simplify("all", parts)


def _parse_sentence(text: str, reqs) -> PrereqExpr | None:
    # "A and B, or C and D": the alternatives are themselves lists of requirements
    options = re.split(r",\s*or\b", text)
    if sum(_is_joint(o) for o in options) >= 2:
        return _simplify("any", [e for o in options if (e := _parse_sentence(o, reqs))])
    # otherwise "and" always separates requirements
    parts: list[PrereqExpr] = []
    for piece in AND.split(text):
        parts += _parse_piece(piece, reqs)
    return _simplify("all", parts)


def _parse_piece(piece: str, reqs) -> list[PrereqExpr]:
    """Requirements in a piece without "and". Commas mean "and" ("CS 2800, MATH 2210
    or MATH 2940") except in an Oxford-comma list ("A, B, or C"), which is one of
    them and ends at its last ", or X". "one of"/"such as" makes the rest one of."""
    if m := ONE_OF.search(piece):
        rest = _simplify("any", reqs(piece[m.end() :]))
        return _parse_piece(piece[: m.start()], reqs) + ([rest] if rest else [])

    def separately(chunks: list[str]) -> list[PrereqExpr]:
        out: list[PrereqExpr] = []
        for chunk in chunks:
            if re.search(r"\bor\b", chunk):
                out += [e for e in [_simplify("any", reqs(chunk))] if e]
            else:
                out += reqs(chunk)
        return out

    chunks = piece.split(",")
    starts_or = [bool(re.match(r"\s*or\b", c)) for c in chunks]
    parts: list[PrereqExpr | list[PrereqExpr]] = []
    oxford: list[PrereqExpr] | None = None
    run: list[str] = []
    for i, chunk in enumerate(chunks):
        run.append(chunk)
        if not starts_or[i] or (i + 1 < len(chunks) and starts_or[i + 1]):
            continue
        # chunks that are alternatives themselves ("A or B, C or D, or equivalents")
        # make it a list of requirements, each with its own options
        nested = any(re.search(r"\bor\b", c) for c in run if not re.match(r"\s*or\b", c))
        if any(OXFORD_CLOSE.match(c) for c in run) or (not nested and EQUIVALENT.match(run[-1])):
            oxford = [r for c in run for r in reqs(c)]
            parts.append(oxford)
        elif oxford is not None and not nested:
            # "A, or B, C, or permission of instructor": still the same list
            oxford += [r for c in run for r in reqs(c)]
        else:
            parts += separately(run)
        run = []
    parts += separately(run)
    return [e for p in parts if (e := _simplify("any", p) if isinstance(p, list) else p)]


def parse_text(text: str, concurrent: bool = False) -> PrereqExpr | None:
    text = text or ""
    if (m := LABEL.match(text)) and re.search(r"co-?req", m.group(0), re.I):
        concurrent = True  # "Prerequisite or corequisite: ..." can be taken alongside
    text = expand_bare_numbers(LABEL.sub("", text).strip())
    text = re.sub(r"\band\s*/\s*or\b", "or", text)
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
