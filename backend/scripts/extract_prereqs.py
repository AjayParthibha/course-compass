"""Write prerequisite review files for the courses we plan with.

    uv run python backend/scripts/extract_prereqs.py CS MATH ORIE ENGRD
    uv run python backend/scripts/extract_prereqs.py CS --llm   # re-parse with an LLM

Each subject gets data/prereqs/<SUBJ>.yaml mapping course code to the roster
text and a parsed expression. Someone reads each entry, fixes `parsed` if it's
wrong, and sets `reviewed: true`. Reviewed entries are never overwritten.
"""

import argparse

import yaml
from pydantic import BaseModel

from app.catalog.prereq_parse import parse
from app.catalog.store import get_catalog
from app.config import get_settings
from app.schemas.courses import PrereqExpr

PROMPT = """Convert this Cornell course's prerequisite text into a boolean expression.

Use "course" for a specific course (set concurrent=true only for corequisites that may be \
taken the same term), "all"/"any" for and/or, and "flag" for anything we can't check \
automatically (instructor permission, class standing, grade minimums, "or equivalent"). \
Return expr = null if there are no prerequisites.

Prerequisites: {prereq}
Corequisites: {coreq}"""


class Parsed(BaseModel):
    expr: PrereqExpr | None


def llm_parse(client, model: str, prereq: str, coreq: str) -> PrereqExpr | None:
    response = client.responses.parse(
        model=model,
        input=PROMPT.format(prereq=prereq, coreq=coreq or "none"),
        text_format=Parsed,
    )
    return response.output_parsed.expr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("subjects", nargs="+")
    parser.add_argument("--llm", action="store_true", help="parse with an LLM instead of regex")
    parser.add_argument("--model", default=get_settings().advisor_model)
    args = parser.parse_args()

    client = None
    if args.llm:
        import openai

        client = openai.OpenAI(api_key=get_settings().openai_api_key)

    out_dir = get_settings().data_dir / "prereqs"
    out_dir.mkdir(exist_ok=True)
    catalog = get_catalog()

    for subject in args.subjects:
        path = out_dir / f"{subject.upper()}.yaml"
        existing = yaml.safe_load(path.read_text()) if path.exists() else {}
        entries = existing or {}
        for course in sorted(catalog.courses.values(), key=lambda c: c.code):
            if course.subject != subject.upper() or entries.get(course.code, {}).get("reviewed"):
                continue
            if not (course.prereq_text or course.coreq_text):
                continue
            expr = parse(course.prereq_text, course.coreq_text)
            if client:
                try:
                    expr = llm_parse(client, args.model, course.prereq_text, course.coreq_text)
                except Exception as e:  # keep the regex parse and move on
                    print(f"{course.code}: LLM parse failed ({e})")
            entries[course.code] = {
                "text": course.prereq_text,
                "coreq_text": course.coreq_text or None,
                "parsed": expr.model_dump(exclude_defaults=False) if expr else None,
                "reviewed": False,
            }
        path.write_text(yaml.safe_dump(entries, sort_keys=True, width=100))
        print(f"{path.name}: {len(entries)} courses")


if __name__ == "__main__":
    main()
