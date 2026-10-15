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


def test_per_term_credit_caps(client, auth):
    onboard(client, auth)
    res = client.patch(
        "/api/plan/settings", json={"max_credits": 20, "term_caps": {"SP27": 15}}, headers=auth
    )
    assert res.status_code == 200
    assert res.json()["max_credits"] == 20 and res.json()["term_caps"] == {"SP27": 15}
    assert client.get("/api/auth/me", headers=auth).json()["term_caps"] == {"SP27": 15}

    add = [{"op": "add", "term": "SP27", "course": c} for c in ["CS 3110", "CS 4820", "CS 4740"]]
    state = client.post("/api/plan/ops", json={"ops": add, "dry_run": True}, headers=auth).json()
    high = [v["message"] for v in state["violations"] if v["kind"] == "credits_high"]
    assert high == ["Spring ’27 has 18 credits, over your 15-credit cap for that term"]

    client.patch("/api/plan/settings", json={"term_caps": {}}, headers=auth)
    state = client.post("/api/plan/ops", json={"ops": add, "dry_run": True}, headers=auth).json()
    assert not [v for v in state["violations"] if v["kind"] == "credits_high"]


def test_settings_validation(client, auth):
    onboard(client, auth)

    def patch(body):
        return client.patch("/api/plan/settings", json=body, headers=auth).status_code

    assert patch({"term_caps": {"FA24": 15}}) == 400  # already taken
    assert patch({"term_caps": {"SP27": 40}}) == 422
    assert patch({"max_credits": 6}) == 422
    assert patch({"graduation_term": "SP25"}) == 400
    assert patch({"graduation_term": "Spring 2028"}) == 422
    assert client.get("/api/auth/me", headers=auth).json()["max_credits"] == 18


def test_extend_graduation(client, auth):
    onboard(client, auth)
    before = client.get("/api/plan", headers=auth).json()["plan"]
    res = client.patch(
        "/api/plan/settings",
        json={"graduation_term": "SP29", "term_caps": {"FA28": 14}},
        headers=auth,
    )
    assert res.status_code == 200 and res.json()["graduation_term"] == "SP29"
    after = client.get("/api/plan", headers=auth).json()["plan"]
    assert after["terms"][-3:] == ["SP28", "FA28", "SP29"]
    assert after["placements"] == before["placements"]

    # shortening again is fine while the dropped terms are empty; their caps go too
    res = client.patch("/api/plan/settings", json={"graduation_term": "SP28"}, headers=auth)
    assert res.status_code == 200 and res.json()["term_caps"] == {}


def test_shorten_graduation_keeps_placements(client, auth):
    onboard(client, auth)
    res = client.patch("/api/plan/settings", json={"graduation_term": "FA27"}, headers=auth)
    assert res.status_code == 409
    assert "(Spring ’28: " in res.json()["detail"] and "4000+ electives" in res.json()["detail"]
    assert client.get("/api/auth/me", headers=auth).json()["graduation_term"] == "SP28"
    assert client.get("/api/plan", headers=auth).json()["plan"]["terms"][-1] == "SP28"


def test_lock_placement(client, auth):
    state = onboard(client, auth).json()
    slot = next(p for p in state["plan"]["placements"] if p["term"] == "SP27")
    lock = {"op": "lock", "placement_id": slot["id"], "locked": True}
    locked = client.post("/api/plan/ops", json={"ops": [lock]}, headers=auth).json()
    assert next(p for p in locked["plan"]["placements"] if p["id"] == slot["id"])["locked"]

    move = {"op": "move", "placement_id": slot["id"], "term": "FA27"}
    res = client.post("/api/plan/ops", json={"ops": [move]}, headers=auth)
    assert res.status_code == 400 and "Unlock it" in res.json()["detail"]

    unlock = lock | {"locked": False}
    moved = client.post("/api/plan/ops", json={"ops": [unlock, move]}, headers=auth).json()
    p = next(p for p in moved["plan"]["placements"] if p["id"] == slot["id"])
    assert p["term"] == "FA27" and not p["locked"]

    undone = client.post("/api/plan/undo", headers=auth).json()["plan"]["placements"]
    p = next(p for p in undone if p["id"] == slot["id"])
    assert p["term"] == "SP27" and p["locked"]
