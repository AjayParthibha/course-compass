"""Read pasted history lines the regex couldn't, with the model, for the student to confirm.

The roster bounds the model: for each unread line ("machine learning w/ Weinberger
4780") it only sees the real courses whose number is on the line (CS 4780, ECE 4780...)
and picks among them, or says none fit. A code it returns that isn't one of those is
dropped, and every pick comes back as a row the student confirms ("We think this is
CS 4780. Is that right?"), never as a matched course. Lines it can't place stay unread.

Only runs with an OpenAI key, like the advisor; without one, onboarding is regex only.
`ask` is the model call (prompt in, JSON text out), passed in so tests need no network.
"""

import json
import re
from collections.abc import Callable

from app.catalog.store import Catalog
from app.onboarding import TERM, _id, normalize_term
from app.schemas.onboarding import Issue, IssueOption, ParsedCourse

NUMBER = re.compile(r"\b(?!20\d\d\b)(\d{4})\b")
MAX_LINES = 20  # one paste's worth; more than this isn't a few stray lines
MAX_CANDIDATES = 15  # per number, so the prompt stays small
MAX_PICKS = 3

PROMPT = """A Cornell student pasted their course history. These lines couldn't be read \
automatically. Each entry below is one course number on one line. For each entry, choose \
the course that number most likely is, only from its candidates (real Cornell courses \
with that number), best first, at most three. If none of the candidates fits what the \
line says, return an empty list for it. Don't guess beyond the candidates.

{lines}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "codes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["line", "codes"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lines"],
    "additionalProperties": False,
}


def read_unread(
    text: str, unread: list[str], catalog: Catalog, ask: Callable[[str], str]
) -> tuple[list[ParsedCourse], list[str]]:
    """Rows for the unread lines the model could place, each waiting for the student to
    confirm, and the lines still unread. A line naming two numbers ("databases 4320, nlp
    4740") is two questions and can give two rows. Any failure leaves every line unread."""
    lines = unread[:MAX_LINES]
    # one question per number on a line: (line index, number) -> its candidates
    asks = {
        (i, n): cands
        for i, line in enumerate(lines)
        for n in dict.fromkeys(NUMBER.findall(line))
        if (cands := _candidates(n, catalog))
    }
    if not asks:
        return [], unread
    keys = list(asks)
    listing = "\n\n".join(
        f"Line {k}: {lines[i]} (the course numbered {n})\nCandidates:\n"
        + "\n".join(f"- {c.code}: {c.title}" for c in asks[(i, n)])
        for k, (i, n) in enumerate(keys)
    )
    try:
        answer = json.loads(ask(PROMPT.format(lines=listing)))
        picks = {int(x["line"]): [str(c) for c in x["codes"]] for x in answer["lines"]}
    except Exception:  # a model or network problem shouldn't break onboarding
        return [], unread

    terms = _terms(text)
    rows: list[ParsedCourse] = []
    placed: set[int] = set()
    for k, (i, n) in enumerate(keys):
        allowed = {c.code: c for c in asks[(i, n)]}
        chosen = list(dict.fromkeys(c for c in picks.get(k, []) if c in allowed))[:MAX_PICKS]
        if not chosen:
            continue
        placed.add(i)
        line = lines[i]
        term, note = terms.get(line, (None, None))
        first = allowed[chosen[0]]
        rows.append(
            ParsedCourse(
                id=_id(),
                raw=line,
                term=term,
                code=None,  # nothing counts until the student confirms
                note=note,
                issue=Issue(
                    kind="model_guess",
                    message=f"We think “{line}” includes {first.code}, {first.title}. "
                    "Is that right?",
                    options=[
                        IssueOption(label=f"{c} · {allowed[c].title}", value=c) for c in chosen
                    ]
                    + [IssueOption(label="Skip it", value="drop")],
                ),
            )
        )
    still = [line for i, line in enumerate(lines) if i not in placed]
    return rows, still + unread[MAX_LINES:]


def _candidates(number: str, catalog: Catalog):
    """Roster courses with this number, one per cross-listed group, shown under its CS
    code when it has one (CS 4740, not COGST 4740: these are CS students)."""
    out, seen = [], set()
    for course in sorted(catalog.courses.values(), key=lambda c: (c.subject != "CS", c.code)):
        if course.number == number and course.code not in seen:
            out.append(course)
            seen |= catalog.equivalents(course.code)
    return sorted(out, key=lambda c: c.code)[:MAX_CANDIDATES]


def _terms(text: str) -> dict[str, tuple[str | None, str | None]]:
    """The term each line falls under, tracked the way parse_history does: a term on a
    line applies to it and to the lines after it."""
    term = note = None
    out = {}
    for line in text.splitlines():
        m = TERM.search(line)
        if m:
            season, year = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
            term, note = normalize_term(season, year)
        out.setdefault(line.strip(), (term, note))
    return out


def openai_ask(api_key: str, model: str) -> Callable[[str], str]:
    """The real model call: one structured response, a short timeout."""
    import openai

    client = openai.OpenAI(api_key=api_key, timeout=20)

    def ask(prompt: str) -> str:
        res = client.responses.create(
            model=model,
            input=prompt,
            text={
                "format": {"type": "json_schema", "name": "picks", "schema": SCHEMA, "strict": True}
            },
        )
        return res.output_text

    return ask
