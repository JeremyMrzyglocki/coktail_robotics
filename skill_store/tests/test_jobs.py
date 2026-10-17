"""The path from a plan to the robot: who may change it, when it is checked,
and how a runner claims it. These are the guards on physical arm motions."""
import json
import threading

import pytest
from fastapi.testclient import TestClient

from app import api, db
from app.models import CompiledPlan, MissingSkill, Step

AUTH = {"Authorization": "Bearer test-secret"}
JUICE = [("locate_object", "juice"), ("grasp_bottle", "juice"),
         ("move_to_station", "glass"), ("pour_into", "glass"),
         ("move_to_station", "table"), ("release_object", "table")]


@pytest.fixture
def client(seeded):
    db.execute("DELETE FROM plans WHERE status IN ('queued', 'running')")
    return TestClient(api.app)


def make_plan(steps=JUICE, valid=1, status="compiled", missing=()):
    plan = CompiledPlan(summary="juice", steps=[Step(skill_id=s, params={"target": t})
                                                for s, t in steps],
                        missing=list(missing))
    pid = db.execute("INSERT INTO plans (prompt, robot_model, plan_json, valid, status) "
                     "VALUES (?,?,?,?,?)", ("juice", "Spirit AI Moz1",
                                            plan.model_dump_json(), valid, status))
    return pid


def status(pid):
    return db.query("SELECT status, valid FROM plans WHERE id = ?", (pid,))[0]


def test_valid_plan_installs_and_is_claimed_once(client):
    pid = make_plan()
    assert client.post("/api/install", json={"plan_id": pid}).status_code == 200
    job = client.get("/api/jobs/next", headers=AUTH).json()["job"]
    assert job["plan_id"] == pid and status(pid)["status"] == "running"
    assert client.get("/api/jobs/next", headers=AUTH).json()["job"] is None


def test_install_ignores_a_stale_valid_flag(client):
    pid = make_plan(steps=[("pour_into", "glass"), ("release_object", "")], valid=1)
    r = client.post("/api/install", json={"plan_id": pid})
    assert r.status_code == 409 and status(pid)["valid"] == 0


def test_a_queued_plan_cannot_be_edited(client):
    pid = make_plan()
    client.post("/api/install", json={"plan_id": pid})
    r = client.post("/api/validate", json={"plan_id": pid, "steps": [
        {"skill_id": "pour_into", "params": {"target": "glass"}}]})
    assert r.status_code == 409
    saved = json.loads(db.query("SELECT plan_json FROM plans WHERE id = ?", (pid,))[0][0])
    assert len(saved["steps"]) == len(JUICE)


def test_a_finished_plan_can_be_edited_and_goes_back_to_compiled(client):
    pid = make_plan(status="done")
    r = client.post("/api/validate", json={"plan_id": pid, "steps": [
        {"skill_id": s, "params": {"target": t}} for s, t in JUICE]})
    assert r.status_code == 200 and status(pid)["status"] == "compiled"


def test_a_plan_broken_after_queueing_is_failed_not_dispatched(client):
    pid = make_plan(steps=[("pour_into", "glass")], status="queued")   # bypassed install
    assert client.get("/api/jobs/next", headers=AUTH).json()["job"] is None
    assert status(pid)["status"] == "failed"


def test_a_stale_running_plan_is_failed_not_rerun(client):
    pid = make_plan(status="running")
    db.execute("UPDATE plans SET claimed_at = datetime('now', '-2 hours') WHERE id = ?", (pid,))
    client.get("/api/jobs/next", headers=AUTH)
    assert status(pid)["status"] == "failed"


def test_two_pollers_never_get_the_same_plan(client):
    for _ in range(20):
        db.execute("DELETE FROM plans WHERE status IN ('queued', 'running')")
        make_plan(status="queued")
        got = []
        threads = [threading.Thread(target=lambda: got.append(api.next_job()["job"]))
                   for _ in range(3)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert sum(1 for j in got if j) == 1


def test_complete_only_applies_to_a_running_plan(client):
    pid = make_plan(status="compiled")
    r = client.post("/api/plans/complete", headers=AUTH, json={"plan_id": pid, "status": "done"})
    assert r.json()["applied"] is False and status(pid)["status"] == "compiled"


def test_robot_endpoints_need_the_token(client):
    assert client.get("/api/jobs/next").status_code == 401
    assert client.get("/api/jobs/next", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_validate_uses_the_gap_positions_the_page_sends(client):
    pid = make_plan(steps=[("locate_object", "brush"), ("grasp_object", "brush")],
                    missing=[MissingSkill(proposed_id="dip_into", name="Dip", description="",
                                          insert_after=1, preconditions=["holding"],
                                          postconditions=["tool_loaded"])])
    moved = MissingSkill(proposed_id="dip_into", name="Dip", description="", insert_after=0,
                         preconditions=["holding"], postconditions=["tool_loaded"])
    client.post("/api/validate", json={"plan_id": pid, "missing": [moved.model_dump()],
                                       "steps": [{"skill_id": "locate_object",
                                                  "params": {"target": "brush"}},
                                                 {"skill_id": "grasp_object",
                                                  "params": {"target": "brush"}}]})
    saved = json.loads(db.query("SELECT plan_json FROM plans WHERE id = ?", (pid,))[0][0])
    assert saved["missing"][0]["insert_after"] == 0


def test_blank_prompt_never_reaches_the_model(client):
    assert client.post("/api/compile", json={"prompt": "  "}).status_code == 422


def test_compose_refuses_a_chain_with_gaps(client):
    pid = make_plan(missing=[MissingSkill(proposed_id="open_lid", name="", description="",
                                          insert_after=1)])
    assert client.post("/api/compose", json={"plan_id": pid}).status_code == 409


def test_a_composite_runs_as_its_parts(client):
    pid = make_plan()
    combo = client.post("/api/compose", json={"plan_id": pid, "name": "Test Juice"}).json()["skill"]
    assert "hand_empty" in combo["preconditions"]
    assert combo["composed_steps"][0] == {"skill_id": "locate_object",
                                          "params": {"target": "juice"}, "rationale": ""}
    try:
        outer = make_plan(steps=[(combo["id"], "")])
        assert client.post("/api/install", json={"plan_id": outer}).status_code == 200
        job = client.get("/api/jobs/next", headers=AUTH).json()["job"]
        assert [s["skill_id"] for s in job["steps"]] == [s for s, _ in JUICE]
        assert job["steps"][1]["params"] == {"target": "juice"}
    finally:
        db.execute("DELETE FROM skills WHERE id = ?", (combo["id"],))


def test_two_composites_in_a_row_are_valid_and_installable(client):
    combo = client.post("/api/compose", json={"plan_id": make_plan(),
                                              "name": "Twice Juice"}).json()["skill"]
    try:
        assert "glass_placed" not in combo["deletes"]
        r = client.post("/api/validate", json={"steps": [{"skill_id": combo["id"]}] * 2})
        assert r.json()["valid"] and r.json()["installable"]
    finally:
        db.execute("DELETE FROM skills WHERE id = ?", (combo["id"],))


def test_one_corrupt_queued_plan_does_not_jam_the_queue(client):
    bad = db.execute("INSERT INTO plans (prompt, robot_model, plan_json, valid, status) "
                     "VALUES ('x', 'm', '{\"summary\": \"x\"}', 1, 'queued')")
    good = make_plan(status="queued")
    job = client.get("/api/jobs/next", headers=AUTH).json()["job"]
    assert job["plan_id"] == good and status(bad)["status"] == "failed"


def test_a_queued_plan_can_be_cancelled_but_a_running_one_cannot(client):
    pid = make_plan(status="queued")
    assert client.post(f"/api/plans/{pid}/cancel").status_code == 200
    assert status(pid)["status"] == "compiled"
    running = make_plan(status="running")
    assert client.post(f"/api/plans/{running}/cancel").status_code == 409


def test_reading_status_fails_a_plan_whose_runner_died(client):
    pid = make_plan(status="running")
    db.execute("UPDATE plans SET claimed_at = datetime('now', '-2 hours') WHERE id = ?", (pid,))
    assert client.get(f"/api/plans/{pid}/status").json()["status"] == "failed"
