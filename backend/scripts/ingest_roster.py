"""Pull course data from the Cornell Class Roster API and build a snapshot.

    uv run python backend/scripts/ingest_roster.py fetch FA22 SP23 ... FA26
    uv run python backend/scripts/ingest_roster.py build --out data/snapshots/2026-10-05

`fetch` caches raw API responses under data/raw/ (the API asks for at most one
request per second, so a full roster takes a few minutes). `build` turns the
cached responses into a single courses.json.gz. `subjects` saves each subject's
full name (ORIE -> Operations Research and Engineering) next to a snapshot:

    uv run python backend/scripts/ingest_roster.py subjects --out data/snapshots/2026-10-05
"""

import argparse
import gzip
import json
import time
from datetime import date
from pathlib import Path

import httpx

API = "https://classes.cornell.edu/api/2.0"
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
TERM_ORDER = {"WI": 0, "SP": 1, "SU": 2, "FA": 3}


def term_key(slug: str) -> tuple[int, int]:
    return int(slug[2:]), TERM_ORDER[slug[:2]]


def get(client: httpx.Client, path: str, **params) -> dict:
    for attempt in range(3):
        try:
            resp = client.get(f"{API}/{path}", params=params, timeout=30)
            time.sleep(1)
            if resp.status_code == 404:  # the API 404s for subjects with no classes
                return {}
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            if attempt == 2:
                raise
            time.sleep(5)
    raise RuntimeError("unreachable")


def fetch(rosters: list[str]) -> None:
    with httpx.Client() as client:
        for roster in rosters:
            out = RAW / roster
            out.mkdir(parents=True, exist_ok=True)
            subjects = get(client, "config/subjects.json", roster=roster)["data"]["subjects"]
            print(f"{roster}: {len(subjects)} subjects")
            for subj in subjects:
                path = out / f"{subj['value']}.json"
                if path.exists():
                    continue
                data = get(client, "search/classes.json", roster=roster, subject=subj["value"])
                path.write_text(json.dumps(data.get("data") or {"classes": []}))


def instructors(cls: dict) -> list[str]:
    names = set()
    for group in cls.get("enrollGroups", []):
        for section in group.get("classSections", []):
            for mtg in section.get("meetings", []):
                for ins in mtg.get("instructors", []):
                    names.add(f"{ins['firstName']} {ins['lastName']}")
    return sorted(names)


def build(out_dir: Path) -> None:
    rosters = sorted((p.name for p in RAW.iterdir() if p.is_dir()), key=term_key)
    courses: dict[str, dict] = {}

    for roster in rosters:
        for path in sorted((RAW / roster).glob("*.json")):
            for cls in json.loads(path.read_text()).get("classes", []):
                code = f"{cls['subject']} {cls['catalogNbr']}"
                group = (cls.get("enrollGroups") or [{}])[0]
                course = courses.setdefault(code, {"code": code, "terms_offered": []})
                if roster not in course["terms_offered"]:
                    course["terms_offered"].append(roster)
                # later rosters overwrite earlier ones, so the newest catalog text wins
                course.update(
                    subject=cls["subject"],
                    number=cls["catalogNbr"],
                    title=cls.get("titleLong") or cls.get("titleShort") or code,
                    description=cls.get("description") or "",
                    credits_min=group.get("unitsMinimum"),
                    credits_max=group.get("unitsMaximum"),
                    prereq_text=cls.get("catalogPrereq") or cls.get("catalogPrereqCoreq") or "",
                    coreq_text=cls.get("catalogCoreq") or "",
                    attributes=sorted({a["crseAttrValue"] for a in cls.get("crseAttrs") or []}),
                    when_offered=cls.get("catalogWhenOffered") or "",
                    forbidden_overlaps=cls.get("catalogForbiddenOverlaps") or "",
                    cross_listed=sorted(
                        f"{c['subject']} {c['catalogNbr']}"
                        for c in group.get("simpleCombinations") or []
                    ),
                    instructors=instructors(cls),
                    last_roster=roster,
                )

    out_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(courses.values(), key=lambda c: (c["subject"], c["number"]))
    with gzip.open(out_dir / "courses.json.gz", "wt") as f:
        json.dump(ordered, f)
    meta = {"rosters": rosters, "built": date.today().isoformat(), "count": len(ordered)}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {len(ordered)} courses to {out_dir}")


def subjects(out_dir: Path) -> None:
    """Subject names from every roster the snapshot was built from; the newest name wins."""
    rosters = json.loads((out_dir / "meta.json").read_text())["rosters"]
    names: dict[str, str] = {}
    with httpx.Client() as client:
        for roster in sorted(rosters, key=term_key):
            for subj in get(client, "config/subjects.json", roster=roster)["data"]["subjects"]:
                names[subj["value"]] = subj.get("descrformal") or subj.get("descr") or subj["value"]
    (out_dir / "subjects.json").write_text(json.dumps(dict(sorted(names.items())), indent=1))
    print(f"wrote {len(names)} subject names to {out_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("rosters", nargs="+")
    b = sub.add_parser("build")
    b.add_argument(
        "--out", type=Path, default=ROOT / "data" / "snapshots" / date.today().isoformat()
    )
    s = sub.add_parser("subjects")
    s.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.cmd == "fetch":
        fetch(args.rosters)
    elif args.cmd == "subjects":
        subjects(args.out)
    else:
        build(args.out)
