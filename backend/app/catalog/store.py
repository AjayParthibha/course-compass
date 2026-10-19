import gzip
import json
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import TypeAdapter

from app.catalog.overlaps import overlap_pairs
from app.catalog.prereq_parse import parse
from app.config import get_settings
from app.schemas.courses import AllOf, AnyOf, Course, CourseReq, PrereqExpr

_expr = TypeAdapter(PrereqExpr)


def season(term: str) -> str:
    return term[:2]


class Catalog:
    def __init__(
        self,
        courses: list[Course],
        prereq_equivalents: dict[str, list[str]] | None = None,
        subject_names: dict[str, str] | None = None,
    ):
        self.courses = {c.code: c for c in courses}
        # course -> other courses whose prerequisites it also satisfies ("or equivalent")
        self.prereq_equivalents = prereq_equivalents or {}
        # ORIE -> Operations Research & Information Engineering
        self.subject_names = subject_names or {}
        # course -> courses the roster says a student can't also get credit for
        self._overlaps: dict[str, set[str]] = {}
        for c in courses:
            for a, b in overlap_pairs(c.forbidden_overlaps):
                self._overlaps.setdefault(a, set()).add(b)
                self._overlaps.setdefault(b, set()).add(a)

    def subject_name(self, subject: str) -> str:
        return self.subject_names.get(subject, subject)

    def get(self, code: str) -> Course | None:
        return self.courses.get(normalize_code(code))

    def __contains__(self, code: str) -> bool:
        return normalize_code(code) in self.courses

    def equivalents(self, code: str) -> set[str]:
        course = self.get(code)
        return {code, *course.cross_listed} if course else {code}

    def overlaps(self, code: str) -> set[str]:
        """Courses that earn no credit alongside this one (the roster's forbidden
        overlaps), with their cross-listings. Never the course itself: taking the same
        course twice is a duplicate, which `equivalents` already catches."""
        same = self.equivalents(code)
        out: set[str] = set()
        for c in same:
            for other in self._overlaps.get(c, ()):
                out |= self.equivalents(other)
        return out - same

    def prereq_credit(self, code: str) -> set[str]:
        """Every course code whose prerequisite this course satisfies: itself, its
        cross-listings and any listed equivalents. Only for prerequisite checks;
        degree requirements and duplicate detection use `equivalents`."""
        out = self.equivalents(code)
        for c in list(out):
            out |= set(self.prereq_equivalents.get(c, []))
        return out

    def offered_in(self, code: str, term: str) -> bool | None:
        """True/False from history, None if we have no data for the course."""
        course = self.get(code)
        if not course or not course.typical_seasons:
            return None
        return season(term) in course.typical_seasons

    def search(self, query: str, limit: int = 20) -> list[Course]:
        q = query.strip().lower()
        if not q:
            return []
        code_q = normalize_code(query)
        scored = []
        for c in self.courses.values():
            if c.code == code_q:
                score = 100
            elif c.code.lower().startswith(q):
                score = 50
            elif q in c.title.lower():
                score = 20
            elif q in c.description.lower():
                score = 5
            else:
                continue
            scored.append((score, c.code, c))
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [c for _, _, c in scored[:limit]]

    @classmethod
    def load(
        cls,
        snapshot_dir: Path,
        prereq_dir: Path | None = None,
        equivalents_file: Path | None = None,
    ) -> "Catalog":
        gz = snapshot_dir / "courses.json.gz"
        if gz.exists():
            with gzip.open(gz, "rt") as f:
                raw = json.load(f)
        else:
            raw = json.loads((snapshot_dir / "courses.json").read_text())
        reviewed = load_reviewed_prereqs(prereq_dir) if prereq_dir else {}
        courses = []
        for row in raw:
            seasons = sorted({season(t) for t in row.get("terms_offered", [])})
            course = Course(**row, typical_seasons=seasons)
            if course.code in reviewed:
                course.prereqs = reviewed[course.code]
                course.prereqs_reviewed = True
            else:
                course.prereqs = parse(course.prereq_text, course.coreq_text)
            courses.append(course)
        # roster text sometimes names the course itself or a cross-listing ("PUBPOL 3380;
        # ECON 1110-ECON 3120", PMA 3300 needing its cross-listing PMA 2300), which no
        # plan could satisfy; those parts are dropped
        for course in courses:
            same = {course.code, *course.cross_listed}
            course.prereqs = _without(course.prereqs, same)
        equivalents = {}
        if equivalents_file and equivalents_file.exists():
            equivalents = yaml.safe_load(equivalents_file.read_text()) or {}
        names_file = snapshot_dir / "subjects.json"
        names = json.loads(names_file.read_text()) if names_file.exists() else {}
        return cls(courses, equivalents, names)


def _without(expr: PrereqExpr | None, codes: set[str]) -> PrereqExpr | None:
    """The expression with requirements for `codes` taken out."""
    if isinstance(expr, CourseReq):
        return None if expr.code in codes else expr
    if isinstance(expr, AllOf | AnyOf):
        items = [e for e in (_without(i, codes) for i in expr.items) if e is not None]
        if len(items) <= 1:
            return items[0] if items else None
        return expr.model_copy(update={"items": items})
    return expr


def normalize_code(code: str) -> str:
    code = code.strip().upper()
    for i, ch in enumerate(code):
        if ch.isdigit():
            return f"{code[:i].strip()} {code[i:].strip()}"
    return code


def load_reviewed_prereqs(prereq_dir: Path) -> dict[str, PrereqExpr | None]:
    out = {}
    for path in sorted(prereq_dir.glob("*.yaml")):
        for code, entry in (yaml.safe_load(path.read_text()) or {}).items():
            if entry.get("reviewed"):
                parsed = entry.get("parsed")
                out[code] = _expr.validate_python(parsed) if parsed else None
    return out


def latest_snapshot(data_dir: Path) -> Path:
    snaps = sorted(p for p in (data_dir / "snapshots").iterdir() if p.is_dir())
    if not snaps:
        raise FileNotFoundError("no course snapshot found; run backend/scripts/ingest_roster.py")
    return snaps[-1]


@lru_cache
def get_catalog() -> Catalog:
    settings = get_settings()
    snap = settings.data_dir / "snapshots" / settings.snapshot if settings.snapshot else None
    return Catalog.load(
        snap or latest_snapshot(settings.data_dir),
        settings.data_dir / "prereqs",
        settings.data_dir / "prereq_equivalents.yaml",
    )
