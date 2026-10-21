import json

import pytest

from app.planner.ops import OpError
from app.schemas.courses import Course

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


def propose(auth, summary, ops):
    from app import models
    from app.advisor.tools import ToolContext, call_tool
    from app.models import SessionLocal

    token = auth["Authorization"].split()[1]
    with SessionLocal() as db:
        student = db.query(models.Student).filter_by(token=token).one()
        ctx = ToolContext(db=db, student=student)
        result = call_tool(ctx, "propose_changes", {"summary": summary, "ops": ops, "changes": []})
        convo = models.Conversation(student_id=student.id)
        db.add(convo)
        db.flush()
        event = {"type": "proposal", "proposal": result.data}
        db.add(
            models.Message(conversation_id=convo.id, role="assistant", content=[], events=[event])
        )
        db.commit()
    return result.data["id"]


def test_proposal_outdated_after_plan_changes(client, auth):
    onboard(client, auth)
    proposal_id = propose(auth, "Add CS 3110", [{"op": "add", "term": "FA26", "course": "CS 3110"}])
    assert client.get(f"/api/proposals/{proposal_id}", headers=auth).json()["status"] == "pending"

    edit = {"ops": [{"op": "add", "term": "SP27", "course": "CS 3110"}]}
    assert client.post("/api/plan/ops", json=edit, headers=auth).status_code == 200

    proposal = client.get(f"/api/proposals/{proposal_id}", headers=auth).json()
    assert proposal["status"] == "outdated"
    history = client.get("/api/chat/latest", headers=auth).json()
    assert history["messages"][-1]["events"][0]["proposal"]["status"] == "outdated"

    res = client.post(f"/api/proposals/{proposal_id}/apply", headers=auth)
    assert res.status_code == 409
    assert "earlier version of your plan" in res.json()["detail"]
    plan = client.get("/api/plan", headers=auth).json()["plan"]
    assert [p["term"] for p in plan["placements"] if p["course"] == "CS 3110"] == ["SP27"]


def test_chat_history_shows_current_proposal_status(client, auth):
    onboard(client, auth)
    proposal_id = propose(auth, "Add CS 3110", [{"op": "add", "term": "FA26", "course": "CS 3110"}])
    client.post(f"/api/proposals/{proposal_id}/discard", headers=auth)

    history = client.get("/api/chat/latest", headers=auth).json()
    assert history["messages"][-1]["events"][0]["proposal"]["status"] == "discarded"
    res = client.post(f"/api/proposals/{proposal_id}/apply", headers=auth)
    assert res.status_code == 409


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


def test_not_interested_hides_candidate(client, auth):
    onboard(client, auth)
    url = "/api/slots/ls/candidates"
    params = {"term": "SP27", "limit": 10}

    def codes(res):
        return [c["course"]["code"] for c in res["candidates"]]

    before = client.get(url, params=params, headers=auth).json()
    assert "GOVT 1111" in codes(before) and before["hidden"] == []
    assert before["ordering"]

    fact = client.put("/api/courses/govt1111/not-interested", headers=auth).json()
    assert fact["dimension"] == "not_interested" and fact["value"] == "GOVT 1111"
    assert fact["status"] == "stated" and fact["text"].startswith("Not interested in GOVT 1111")
    again = client.put("/api/courses/GOVT 1111/not-interested", headers=auth).json()
    assert again["id"] == fact["id"]

    after = client.get(url, params=params, headers=auth).json()
    assert "GOVT 1111" not in codes(after)
    assert after["eligible_count"] == before["eligible_count"] - 1
    hidden = [(h["course"]["code"], h["fact_id"]) for h in after["hidden"]]
    assert hidden == [("GOVT 1111", fact["id"])]
    profile = client.get("/api/profile", headers=auth).json()
    assert any(f["id"] == fact["id"] for f in profile["facts"])

    undo = client.delete("/api/courses/GOVT 1111/not-interested", headers=auth)
    assert undo.status_code == 204
    restored = client.get(url, params=params, headers=auth).json()
    assert "GOVT 1111" in codes(restored) and restored["hidden"] == []

    # removing the fact from the profile page also brings the course back
    client.put("/api/courses/GOVT 1111/not-interested", headers=auth)
    fact_id = client.get(url, params=params, headers=auth).json()["hidden"][0]["fact_id"]
    client.delete(f"/api/profile/facts/{fact_id}", headers=auth)
    assert "GOVT 1111" in codes(client.get(url, params=params, headers=auth).json())

    assert client.put("/api/courses/XYZ 9999/not-interested", headers=auth).status_code == 404


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
    assert patch({"term_caps": {"FA26": 15}}) == 400  # current term
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
    assert "(Spring ’28: " in res.json()["detail"]
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


def ops(client, auth, *edits):
    res = client.post("/api/plan/ops", json={"ops": list(edits)}, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def terms_by_id(state):
    return {p["id"]: p["term"] for p in state["plan"]["placements"]}


def test_undo_walks_back_through_history(client, auth):
    start = onboard(client, auth).json()
    a, b = [p for p in start["plan"]["placements"] if p["term"] == "SP27"][:2]
    ops(client, auth, {"op": "move", "placement_id": a["id"], "term": "FA27"})
    ops(client, auth, {"op": "move", "placement_id": b["id"], "term": "SP28"})

    once = client.post("/api/plan/undo", headers=auth).json()
    assert terms_by_id(once)[a["id"]] == "FA27" and terms_by_id(once)[b["id"]] == "SP27"
    twice = client.post("/api/plan/undo", headers=auth).json()
    assert terms_by_id(twice) == terms_by_id(start)
    # nothing left to undo
    again = client.post("/api/plan/undo", headers=auth).json()
    assert terms_by_id(again) == terms_by_id(start)
    assert again["plan"]["version"] == twice["plan"]["version"]

    # an edit after undoing starts a new branch of history
    ops(client, auth, {"op": "move", "placement_id": b["id"], "term": "FA27"})
    back = client.post("/api/plan/undo", headers=auth).json()
    assert terms_by_id(back) == terms_by_id(start)


def empty_spring_28(client, auth):
    state = onboard(client, auth).json()
    sp28 = [p for p in state["plan"]["placements"] if p["term"] == "SP28"]
    return ops(
        client, auth, *[{"op": "move", "placement_id": p["id"], "term": "FA27"} for p in sp28]
    )


def set_graduation(client, auth, term):
    return client.patch("/api/plan/settings", json={"graduation_term": term}, headers=auth)


def test_graduation_change_is_a_new_version(client, auth):
    before = empty_spring_28(client, auth)["plan"]
    proposal_id = propose(auth, "Add CS 4780", [{"op": "add", "term": "FA27", "course": "CS 4780"}])

    assert set_graduation(client, auth, "FA27").status_code == 200
    after = client.get("/api/plan", headers=auth).json()["plan"]
    assert after["version"] == before["version"] + 1
    assert after["placements"] == before["placements"]
    assert client.get(f"/api/proposals/{proposal_id}", headers=auth).json()["status"] == "outdated"
    assert client.post(f"/api/proposals/{proposal_id}/apply", headers=auth).status_code == 409


def test_undo_refuses_versions_outside_the_plan_terms(client, auth):
    empty_spring_28(client, auth)
    assert set_graduation(client, auth, "FA27").status_code == 200

    # undo skips the graduation change and would bring back Spring ’28 placements
    res = client.post("/api/plan/undo", headers=auth)
    assert res.status_code == 409 and "Spring ’28" in res.json()["detail"]
    state = client.get("/api/plan", headers=auth).json()
    assert all(p["term"] in state["plan"]["terms"] for p in state["plan"]["placements"])

    slot = next(p for p in state["plan"]["placements"] if p["slot"] and not p["course"])
    url = f"/api/slots/{slot['slot']}/candidates"
    assert client.get(url, params={"term": "FA27"}, headers=auth).status_code == 200

    # with Spring ’28 back in the plan, the undo goes through
    assert set_graduation(client, auth, "SP28").status_code == 200
    res = client.post("/api/plan/undo", headers=auth)
    assert res.status_code == 200
    assert any(p["term"] == "SP28" for p in res.json()["plan"]["placements"])


def test_ops_outside_plan_terms_are_rejected(client, auth):
    onboard(client, auth)
    add = {"op": "add", "term": "SP29", "course": "CS 3110"}
    res = client.post("/api/plan/ops", json={"ops": [add]}, headers=auth)
    assert res.status_code == 400 and "Spring ’29 isn't in your plan" in res.json()["detail"]


def test_preview_of_outdated_proposal_is_409(client, auth):
    onboard(client, auth)
    proposal_id = propose(auth, "Add CS 3110", [{"op": "add", "term": "FA26", "course": "CS 3110"}])
    assert client.post(f"/api/proposals/{proposal_id}/preview", headers=auth).status_code == 200
    ops(client, auth, {"op": "add", "term": "SP27", "course": "CS 4820"})
    res = client.post(f"/api/proposals/{proposal_id}/preview", headers=auth)
    assert res.status_code == 409 and "earlier version of your plan" in res.json()["detail"]
    assert client.post(f"/api/proposals/{proposal_id}/apply", headers=auth).status_code == 409


def test_advisor_cannot_lock_or_touch_locked(client, auth):
    import pydantic

    from app.advisor.tools import REGISTRY

    state = onboard(client, auth).json()
    ops_schema = json.dumps(REGISTRY["propose_changes"].schema()["parameters"]["properties"]["ops"])
    assert '"remove"' in ops_schema and '"lock"' not in ops_schema
    slot = next(p for p in state["plan"]["placements"] if p["term"] == "SP27")
    with pytest.raises(pydantic.ValidationError):
        propose(auth, "Unlock", [{"op": "lock", "placement_id": slot["id"], "locked": False}])

    ops(client, auth, {"op": "lock", "placement_id": slot["id"]})
    with pytest.raises(OpError, match="locked in Spring ’27 by the student"):
        propose(auth, "Drop it", [{"op": "remove", "placement_id": slot["id"]}])


def test_not_interested_covers_cross_listings(client, auth, catalog, monkeypatch):
    monkeypatch.setattr(catalog.get("GOVT 1111"), "cross_listed", ["PSYCH 1101"])
    monkeypatch.setattr(catalog.get("PSYCH 1101"), "cross_listed", ["GOVT 1111"])
    onboard(client, auth)
    url, params = "/api/slots/ls/candidates", {"term": "SP27", "limit": 10}

    fact = client.put("/api/courses/PSYCH 1101/not-interested", headers=auth).json()
    hidden = client.get(url, params=params, headers=auth).json()["hidden"]
    assert [(h["course"]["code"], h["fact_id"]) for h in hidden] == [("GOVT 1111", fact["id"])]
    # marking the code the slot shows doesn't add a second fact
    again = client.put("/api/courses/GOVT 1111/not-interested", headers=auth).json()
    assert again["id"] == fact["id"]
    facts = client.get("/api/profile", headers=auth).json()["facts"]
    assert [f["id"] for f in facts if f["dimension"] == "not_interested"] == [fact["id"]]

    # "show again" on the shown code removes the fact saved under the other one
    assert client.delete("/api/courses/GOVT 1111/not-interested", headers=auth).status_code == 204
    assert client.get(url, params=params, headers=auth).json()["hidden"] == []


def test_student_update_only_takes_known_fields(client, auth):
    onboard(client, auth)

    def patch(body):
        return client.patch("/api/profile/student", json=body, headers=auth)

    # stale clients that still send plan settings here get told so
    assert patch({"graduation_term": "SP29"}).status_code == 422
    assert patch({"max_credits": 12}).status_code == 422
    assert patch({"entering_term": "FA28"}).status_code == 422
    assert patch({"memory_enabled": False}).json()["memory_enabled"] is False
    me = client.get("/api/auth/me", headers=auth).json()
    assert (me["entering_term"], me["graduation_term"], me["max_credits"]) == ("FA24", "SP28", 18)
    assert client.get("/api/plan", headers=auth).status_code == 200


def test_onboarding_again_prunes_term_caps(client, auth):
    onboard(client, auth)
    caps = {"SP28": 15, "FA28": 14, "SP29": 14}
    res = client.patch(
        "/api/plan/settings", json={"graduation_term": "SP29", "term_caps": caps}, headers=auth
    )
    assert res.status_code == 200
    onboard(client, auth)  # graduates SP28 again
    me = client.get("/api/auth/me", headers=auth).json()
    assert me["graduation_term"] == "SP28" and me["term_caps"] == {"SP28": 15}


def test_onboarding_rejects_backwards_terms(client, auth):
    body = {"program": "cs-eng", "entering_term": "FA24", "graduation_term": "SP24", "courses": []}
    res = client.post("/api/onboarding/confirm", json=body, headers=auth)
    assert res.status_code == 400


def test_placements_list_what_they_count_as(client, auth, catalog, monkeypatch):
    from app import models
    from app.models import SessionLocal

    monkeypatch.setattr(catalog.get("CS 4780"), "cross_listed", ["ORIE 4741"])
    monkeypatch.setitem(catalog.prereq_equivalents, "CS 1110", ["CS 1112"])
    state = onboard(client, auth).json()
    by_course = {p["course"]: p for p in state["plan"]["placements"] if p["course"]}
    assert by_course["CS 1110"]["counts_as"] == ["CS 1112"]
    assert by_course["CS 2110"]["counts_as"] == []
    assert all(p["counts_as"] == [] for p in state["plan"]["placements"] if not p["course"])

    add = {"op": "add", "term": "SP27", "course": "CS 4780"}
    dry = client.post("/api/plan/ops", json={"ops": [add], "dry_run": True}, headers=auth).json()
    assert next(p for p in dry["plan"]["placements"] if p["course"] == "CS 4780")["counts_as"] == [
        "ORIE 4741"
    ]

    # computed for responses only, not saved with the plan
    with SessionLocal() as db:
        row = db.query(models.PlanVersion).order_by(models.PlanVersion.id.desc()).first()
        assert all("counts_as" not in p for p in row.placements)


def test_undo_steps_past_a_settings_version_in_the_middle(client, auth):
    start = onboard(client, auth).json()
    a, b = [p for p in start["plan"]["placements"] if p["term"] == "SP27"][:2]
    ops(client, auth, {"op": "move", "placement_id": a["id"], "term": "FA27"})
    assert set_graduation(client, auth, "SP29").status_code == 200
    ops(client, auth, {"op": "move", "placement_id": b["id"], "term": "SP28"})

    once = client.post("/api/plan/undo", headers=auth).json()
    assert terms_by_id(once)[b["id"]] == "SP27" and terms_by_id(once)[a["id"]] == "FA27"
    # the next undo reaches the edit before the graduation change instead of doing nothing
    twice = client.post("/api/plan/undo", headers=auth).json()
    assert terms_by_id(twice) == terms_by_id(start)


def test_onboarding_again_starts_a_fresh_history(client, auth):
    start = onboard(client, auth).json()
    a = next(p for p in start["plan"]["placements"] if p["term"] == "SP27")
    ops(client, auth, {"op": "move", "placement_id": a["id"], "term": "FA27"})
    again = onboard(client, auth).json()
    undone = client.post("/api/plan/undo", headers=auth).json()
    assert terms_by_id(undone) == terms_by_id(again)


def test_memory_setting_rejects_null(client, auth):
    onboard(client, auth)
    res = client.patch("/api/profile/student", json={"memory_enabled": None}, headers=auth)
    assert res.status_code == 422


def test_repair_makes_a_proposal_or_names_the_conflict(client, auth):
    onboard(client, auth)
    state = client.get("/api/plan", headers=auth).json()
    plan = state["plan"]
    future = plan["terms"][plan["terms"].index(plan["current_term"]) + 1 :]
    load = {t: sum(p["credits"] for p in plan["placements"] if p["term"] == t) for t in future}
    heavy = max(future, key=load.get)

    body = {"summary": "Lighter term", "request": {"term_caps": {heavy: load[heavy] - 3}}}
    res = client.post("/api/plan/repair", json=body, headers=auth).json()
    result, proposal = res["result"], res["proposal"]
    assert result["status"] == "solved" and result["blocking"] == 0 and result["optimal"]
    assert result["moved"] >= 1 and proposal is not None
    assert not [v for v in proposal["violations"] if v["blocking"]]
    assert any("No smaller change" in c for c in proposal["checks"])
    assert proposal["changes"] and all(c["reason"] for c in proposal["changes"])
    assert proposal["solver"]["optimal"] and proposal["solver"]["moved"] == result["moved"]
    applied = client.post(f"/api/proposals/{proposal['id']}/apply", headers=auth).json()
    after = sum(p["credits"] for p in applied["plan"]["placements"] if p["term"] == heavy)
    assert after <= load[heavy] - 3

    nothing = {"request": {"term_caps": {t: 0 for t in future}}}
    res = client.post("/api/plan/repair", json=nothing, headers=auth).json()
    assert res["result"]["status"] == "infeasible" and res["proposal"] is None
    assert any("(your request)" in c for c in res["result"]["conflicts"])

    bad = client.post("/api/plan/repair", json={"request": {"keep": ["nope"]}}, headers=auth)
    assert bad.status_code == 422 and "nope" in bad.json()["detail"]


def test_repair_tool_reports_back(client, auth):
    from app import models, services
    from app.advisor.tools import ToolContext, call_tool
    from app.models import SessionLocal

    onboard(client, auth)
    token = auth["Authorization"].split()[1]
    with SessionLocal() as db:
        student = db.query(models.Student).filter_by(token=token).one()
        ctx = ToolContext(db=db, student=student)
        ok = call_tool(ctx, "repair_plan", {"summary": "Check", "request": {}})
        assert ok.summary == "nothing needs to change"
        assert ok.data["status"] == "solved" and ok.data["changes"] == []
        bad = call_tool(ctx, "repair_plan", {"summary": "x", "request": {"remove": ["nope"]}})
        assert bad.summary.startswith("request rejected")

        # a draft the planner flagged is withdrawn once repair_plan takes over
        state = services.plan_state(db, student)
        future = [t for t in state.plan.terms if t > state.plan.current_term][:1]
        draft = call_tool(
            ctx,
            "propose_changes",
            {
                "summary": "Overload",
                "ops": [
                    {"op": "add", "term": future[0], "course": c}
                    for c in ("CS 4780", "CS 4740", "CS 4820", "PSYCH 1101", "GOVT 1111")
                ],
                "changes": [],
            },
        )
        assert draft.summary.startswith("proposal has")
        ctx.events.clear()  # the advisor loop empties events after every tool call
        ok = call_tool(ctx, "repair_plan", {"summary": "Check", "request": {}})
        assert ok.data["withdrew_earlier_drafts"] == [draft.data["id"]]
        row = services.get_proposal(db, student, draft.data["id"])
        assert row.status == "discarded"


def test_advisor_approval_relaxes_the_one_subject_rule(client, auth):
    onboard(client, auth)
    term = "FA26"
    before = client.get(f"/api/slots/ext/candidates?term={term}", headers=auth).json()
    assert before["same_subject"] and before["approval"]["approved"] is False

    res = client.put("/api/profile/approvals/ext", json={"approved": True}, headers=auth)
    assert res.status_code == 200 and res.json()["approvals"] == ["ext"]
    after = client.get(f"/api/slots/ext/candidates?term={term}", headers=auth).json()
    assert not after["same_subject"] and after["approval"]["approved"] is True

    res = client.put("/api/profile/approvals/ext", json={"approved": False}, headers=auth)
    assert res.json()["approvals"] == []
    # only rules that allow an approval can record one
    res = client.put("/api/profile/approvals/core", json={"approved": True}, headers=auth)
    assert res.status_code == 404


def confirm_plan(client, auth, entering, graduating, courses=()):
    return client.post(
        "/api/onboarding/confirm",
        json={
            "program": "cs-eng",
            "entering_term": entering,
            "graduation_term": graduating,
            "courses": list(courses),
        },
        headers=auth,
    )


def test_onboarding_options_run_through_next_term(client, auth):
    res = client.get("/api/onboarding/options", headers=auth).json()
    assert res["current_term"] == "FA26"
    # rules start at 2024-25; a student starting next term can onboard too
    assert res["entering_terms"][0] == "FA24" and res["entering_terms"][-1] == "SP27"
    assert res["rule_years"]["cs-eng"] == ["2024-25"]


def test_a_student_who_hasnt_started_gets_an_all_planned_plan(client, auth):
    res = confirm_plan(client, auth, "SP27", "FA30")
    assert res.status_code == 200
    state = res.json()
    placements = state["plan"]["placements"]
    assert placements and all(p["status"] == "planned" for p in placements)
    assert {p["term"] for p in placements} <= set(state["plan"]["terms"])
    # later entrants are checked against the newest rules we have
    assert client.get("/api/auth/me", headers=auth).json()["catalog_year"] == "2024-25"


def test_a_first_semester_students_courses_are_in_progress(client, auth):
    res = confirm_plan(client, auth, "FA26", "SP30", [{"term": None, "code": "CS 1110"}])
    assert res.status_code == 200
    cs = next(p for p in res.json()["plan"]["placements"] if p["course"] == "CS 1110")
    assert (cs["term"], cs["status"]) == ("FA26", "in_progress")


def test_students_who_started_before_the_rules_are_turned_away(client, auth):
    res = confirm_plan(client, auth, "FA23", "SP27")
    assert res.status_code == 400 and "Fall 2024 or later" in res.json()["detail"]


def test_candidates_are_ranked_by_the_profile(client, auth):
    onboard(client, auth)
    url = "/api/slots/e4000/candidates"
    params = {"term": "FA27", "limit": 10}

    def get():
        return client.get(url, params=params, headers=auth).json()

    def codes(res):
        return [c["course"]["code"] for c in res["candidates"]]

    # nothing in the profile: offered most often first, no reasons, no factors, so the
    # page says it isn't a personal recommendation
    before = get()
    assert codes(before) == ["CS 4740", "CS 4780"]
    assert all(c["reasons"] == [] for c in before["candidates"])
    assert before["factors"] == [] and before["ordering"].startswith("Sorted by")

    fact = client.post(
        "/api/profile/facts",
        json={"dimension": "interest", "value": "ml", "text": "Interested in machine learning"},
        headers=auth,
    ).json()
    after = get()
    assert codes(after) == ["CS 4780", "CS 4740"]
    top = after["candidates"][0]
    assert top["rank"] == 1
    assert top["reasons"][0]["text"] == "About machine learning, which you're interested in"
    assert top["reasons"][0]["basis"] == "stated" and top["reasons"][0]["fact_id"] == fact["id"]
    factors = {f["label"]: f["strength"] for f in after["factors"]}
    assert factors["Interests: machine learning"] == "strong"
    assert factors["Student reviews"] == "not used"
    assert after["ordering"].startswith("Ranked by what you’ve told us")

    # the student says that's wrong: the list goes back to the official order
    client.patch(f"/api/profile/facts/{fact['id']}", json={"status": "rejected"}, headers=auth)
    assert codes(get()) == ["CS 4740", "CS 4780"] and get()["factors"] == []


def test_ranking_leaves_hidden_courses_hidden(client, auth):
    onboard(client, auth)
    client.post(
        "/api/profile/facts",
        json={"dimension": "interest", "value": "ml", "text": "Interested in machine learning"},
        headers=auth,
    )
    client.put("/api/courses/CS 4780/not-interested", headers=auth)
    res = client.get("/api/slots/e4000/candidates", params={"term": "FA27"}, headers=auth).json()
    assert [c["course"]["code"] for c in res["candidates"]] == ["CS 4740"]
    assert [h["course"]["code"] for h in res["hidden"]] == ["CS 4780"]


def test_specialization_areas_follow_interests(client, auth, catalog, monkeypatch):
    def add(code, title):
        subject, number = code.split()
        monkeypatch.setitem(
            catalog.courses,
            code,
            Course(
                code=code,
                subject=subject,
                number=number,
                title=title,
                credits_min=3,
                credits_max=3,
                terms_offered=["FA25", "SP26", "FA26"],
                typical_seasons=["FA", "SP"],
            ),
        )

    for code, title in [
        ("ECON 3010", "Econometrics"),
        ("ECON 3030", "Intermediate Microeconomics"),
        ("ECON 3110", "Probability Models"),
        ("ORIE 4740", "Statistical Learning"),
        ("ORIE 4741", "Machine Learning with Big Messy Data"),
    ]:
        add(code, title)
    monkeypatch.setitem(catalog.subject_names, "ECON", "Economics")
    onboard(client, auth)

    def areas():
        res = client.get("/api/slots/ext/areas", params={"term": "SP27"}, headers=auth).json()
        return [(a["subject"], [r["text"] for r in a["reasons"]]) for a in res["areas"]]

    # nothing said: more courses ready to take first
    assert areas() == [("ECON", []), ("ORIE", [])]
    ml = client.post(
        "/api/profile/facts",
        json={"dimension": "interest", "value": "ml", "text": "Interested in machine learning"},
        headers=auth,
    ).json()
    assert areas() == [
        ("ORIE", ["2 courses about machine learning, which you're interested in"]),
        ("ECON", []),
    ]
    client.patch(f"/api/profile/facts/{ml['id']}", json={"status": "rejected"}, headers=auth)
    client.post(
        "/api/profile/facts",
        json={"dimension": "interest", "value": "economics", "text": "Interested in economics"},
        headers=auth,
    )
    assert areas()[0] == ("ECON", ["Economics, which you're interested in"])


def test_past_chats_are_listed_newest_first(client, auth):
    from app import models
    from app.models import SessionLocal, now

    onboard(client, auth)
    me = client.get("/api/auth/me", headers=auth).json()
    with SessionLocal() as db:
        for question in ["Make Fall ’27 lighter", "What's left before I graduate?"]:
            convo = models.Conversation(student_id=me["id"])
            db.add(convo)
            db.flush()
            db.add(
                models.Message(
                    conversation_id=convo.id,
                    role="user",
                    content=[{"role": "user", "content": question}],
                    events=[{"type": "text", "delta": question}],
                    created_at=now(),
                )
            )
        db.add(models.Conversation(student_id=me["id"]))  # never used: left out
        db.commit()
    chats = client.get("/api/chat", headers=auth).json()
    titles = [c["title"] for c in chats]
    assert titles == ["What's left before I graduate?", "Make Fall ’27 lighter"]
    assert all(c["questions"] == 1 for c in chats)
