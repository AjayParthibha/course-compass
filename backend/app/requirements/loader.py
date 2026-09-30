from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings
from app.schemas.requirements import Program, RequirementSet

# program id -> (label, college rule folder, major rule folder)
PROGRAMS = {
    "cs-eng": ("Computer Science B.S. (Engineering)", "engineering", "cs-major-eng"),
    "cs-as": ("Computer Science B.A. (Arts & Sciences)", "arts-sciences", "cs-major-as"),
}


def load_set(path: Path) -> RequirementSet:
    return RequirementSet.model_validate(yaml.safe_load(path.read_text()))


def catalog_year_for(entering_term: str) -> str:
    """FA24 -> 2024-25, SP25 -> 2024-25."""
    year = 2000 + int(entering_term[2:])
    start = year if entering_term.startswith("FA") else year - 1
    return f"{start}-{str(start + 1)[2:]}"


def load_program(program_id: str, catalog_year: str, rules_dir: Path | None = None) -> Program:
    if program_id not in PROGRAMS:
        raise KeyError(f"unknown program {program_id}")
    rules_dir = rules_dir or get_settings().data_dir / "requirements"
    label, college, major = PROGRAMS[program_id]
    sets = []
    for folder in (major, college):
        path = rules_dir / folder / f"{catalog_year}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"no {folder} rules for {catalog_year} ({path})")
        sets.append(load_set(path))
    return Program(
        id=program_id, label=label, college=college, catalog_year=catalog_year, sets=sets
    )


@lru_cache
def get_program(program_id: str, catalog_year: str) -> Program:
    return load_program(program_id, catalog_year)


def available_years(program_id: str) -> list[str]:
    _, college, major = PROGRAMS[program_id]
    rules = get_settings().data_dir / "requirements"
    years = {p.stem for p in (rules / major).glob("*.yaml")}
    return sorted(years & {p.stem for p in (rules / college).glob("*.yaml")})
