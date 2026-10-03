HISTORY = """FA24 CS 1110 / MATH 1910
SP25 CS 2110, CS 2800
FA25 ECON 1110 (4cr)
"""


def onboard(client, auth):
    parsed = client.post(
        "/api/onboarding/parse",
        json={"text": HISTORY, "program": "cs-eng", "entering_term": "FA24"},
        headers=auth,
    ).json()
    courses = [
        {"term": c["term"], "code": c["code"], "credits": c["credits"]}
        for c in parsed["courses"]
        if c["code"]
    ]
    return client.post(
        "/api/onboarding/confirm",
        json={
            "program": "cs-eng",
            "entering_term": "FA24",
            "graduation_term": "SP28",
            "courses": courses,
        },
        headers=auth,
    )


def test_requires_login(client):
    assert client.get("/api/plan").status_code == 401


def test_parse_flags_credit_mismatch(client, auth):
    res = client.post(
        "/api/onboarding/parse",
        json={"text": HISTORY, "program": "cs-eng", "entering_term": "FA24"},
        headers=auth,
    ).json()
    econ = next(c for c in res["courses"] if c["code"] == "ECON 1110")
    assert econ["issue"]["kind"] == "credit_mismatch"
    assert res["catalog_year"] == "2024-25"


def test_onboard_and_edit(client, auth):
    res = onboard(client, auth)
    assert res.status_code == 200
    state = res.json()
    assert state["plan"]["terms"][0] == "FA24" and state["plan"]["terms"][-1] == "SP28"
    statuses = {p["status"] for p in state["plan"]["placements"] if p["course"]}
    assert statuses == {"completed"}
    assert any(p["slot"] for p in state["plan"]["placements"])

    add = {"ops": [{"op": "add", "term": "FA26", "course": "CS 3110"}]}
    dry = client.post("/api/plan/ops", json=add | {"dry_run": True}, headers=auth).json()
    assert any(p["course"] == "CS 3110" for p in dry["plan"]["placements"])
    assert client.get("/api/plan", headers=auth).json()["plan"]["version"] == 1

    saved = client.post("/api/plan/ops", json=add, headers=auth).json()
    assert saved["plan"]["version"] == 2
    undone = client.post("/api/plan/undo", headers=auth).json()
    assert not any(p["course"] == "CS 3110" for p in undone["plan"]["placements"])


def test_proposal_flow(client, auth):
    from app import models
    from app.advisor.tools import ToolContext, call_tool
    from app.models import SessionLocal

    onboard(client, auth)
    token = auth["Authorization"].split()[1]
    with SessionLocal() as db:
        student = db.query(models.Student).filter_by(token=token).one()
        ctx = ToolContext(db=db, student=student)
        result = call_tool(
            ctx,
            "propose_changes",
            {
                "summary": "Add CS 3110 this fall",
                "ops": [{"op": "add", "term": "FA26", "course": "CS 3110"}],
                "changes": [{"course": "CS 3110", "to_term": "FA26", "reason": "next core course"}],
            },
        )
    proposal_id = result.data["id"]
    assert result.summary == "proposal ready"

    applied = client.post(f"/api/proposals/{proposal_id}/apply", headers=auth).json()
    assert any(p["course"] == "CS 3110" for p in applied["plan"]["placements"])
    again = client.post(f"/api/proposals/{proposal_id}/apply", headers=auth)
    assert again.status_code == 409


def test_profile_facts(client, auth):
    fact = client.post(
        "/api/profile/facts",
        json={"dimension": "career_track", "value": "ml", "text": "Wants an ML job"},
        headers=auth,
    ).json()
    assert fact["status"] == "stated"
    facts = client.get("/api/profile", headers=auth).json()["facts"]
    assert [f["text"] for f in facts] == ["Wants an ML job"]


def test_chat_without_key_reports_error(client, auth):
    with client.stream("POST", "/api/chat", json={"message": "hi"}, headers=auth) as res:
        body = "".join(res.iter_text())
    assert '"type":"error"' in body and '"type":"done"' in body
