"""The roster's forbidden overlaps: courses a student can't get credit for together.

The roster writes them several ways:

    "MATH 2210, MATH 2230, MATH 2310, MATH 2940"            only one of the list
    "... credit for only one course in the following group: A, B, C."
    "... will not receive credit for both A and B or C."    A with B, A with C
    "CHEM 1560 and CHEM 1561, CHEM 2090 and CHEM 2091"      lecture + lab bundles
    "MATH 3340 and MATH 3360, nor for both MATH 3340 and MATH 4340"

A conditional rule ("no credit for MATH 1710 if taken after ECON 3130") isn't an
overlap and is skipped.
"""

import re
from itertools import combinations, product

CODE = re.compile(r"\b([A-Z]{2,7})\s+(\d{4})\b")
CLAUSES = re.compile(r"\.\s+|\.\s*$|;|\bIn addition,?|\bnor for (?=both\b)", re.I)
TWO_SIDED = re.compile(r"\b(both|either)\b(.*)", re.I)


def _codes(text: str) -> list[str]:
    return [f"{s} {n}" for s, n in CODE.findall(text)]


def _clause_pairs(clause: str) -> set[tuple[str, str]]:
    if re.search(r"\bif taken\b", clause, re.I):
        return set()
    if m := TWO_SIDED.search(clause):
        rest = re.sub(r"^\s*(and|or)\b", "", m.group(2))
        joiner = r"\band\b" if m.group(1).lower() == "both" else r"\bor\b"
        sides = re.split(joiner, rest, maxsplit=1)
        if len(sides) == 2 and all(_codes(s) for s in sides):
            return set(product(_codes(sides[0]), _codes(sides[1])))
        return set(combinations(_codes(rest), 2))
    items = [c for c in (_codes(i) for i in clause.split(",")) if c]
    if len(items) == 1:
        # "MATH 3340 and MATH 3360": a pair written without "both"
        return set(combinations(items[0], 2))
    # each item is one course or a lecture and its lab; items exclude each other
    return {(a, b) for x, y in combinations(items, 2) for a in x for b in y}


def overlap_pairs(text: str) -> set[tuple[str, str]]:
    text = re.sub(r"^\s*Forbidden Overlap:\s*", "", text or "", flags=re.I)
    pairs: set[tuple[str, str]] = set()
    for clause in CLAUSES.split(text):
        pairs |= {(a, b) for a, b in _clause_pairs(clause) if a != b}
    return pairs
