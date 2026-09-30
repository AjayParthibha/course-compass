import gzip
import json
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import TypeAdapter

from app.catalog.prereq_parse import parse
from app.config import get_settings
from app.schemas.courses import Course, PrereqExpr

_expr = TypeAdapter(PrereqExpr)


def season(term: str) -> str:
    return term[:2]


class Catalog:
    def __init__(self, courses: list[Course]):
        self.courses = {c.code: c for c in courses}

    def get(self, code: str) -> Course | None:
        return self.courses.get(normalize_code(code))

    def __contains__(self, code: str) -> bool:
        return normalize_code(code) in self.courses

    def equivalents(self, code: str) -> set[str]:
        course = self.get(code)
        return {code, *course.cross_listed} if course else {code}

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
    def load(cls, snapshot_dir: Path, prereq_dir: Path | None = None) -> "Catalog":
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
        return cls(courses)


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
    return Catalog.load(snap or latest_snapshot(settings.data_dir), settings.data_dir / "prereqs")
