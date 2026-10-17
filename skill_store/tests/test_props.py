"""Prop sizes: the plan decides how big things are, the designer only their
shape. No model is called; structured_call is stubbed."""
import pytest
from fastapi.testclient import TestClient

from app import api, db
from app import props as propgen
from app.compiler import _act_schema, _to_plan
from app.models import CompiledPlan, MissingSkill, PlanObject, Step


def step(skill_id, target="", hand="right"):
    return Step(skill_id=skill_id, params={"target": target} if target else {},
                planned_hand=hand)


def gap(proposed_id, after, pre=("holding", "positioned"), post=("attached",), hand="right"):
    return MissingSkill(proposed_id=proposed_id, name=proposed_id, description="",
                        preconditions=list(pre), postconditions=list(post),
                        insert_after=after, hand=hand)


def toy_car_plan(wheel_cm=30.0, car_cm=15.0):
    """The stored plan for "attach the wheels to the toy car", one wheel."""
    steps = [step("locate_object", "wheel1"), step("grasp_object", "wheel1"),
             step("move_to_station", "toy car"),
             step("move_to_station", "table"), step("release_object", "table")]
    return CompiledPlan(summary="", steps=steps,
                        missing=[gap("press_to_surface", 2)],
                        objects=[PlanObject(name="wheel1", kind="item", size_cm=wheel_cm),
                                 PlanObject(name="toy car", kind="item", size_cm=car_cm),
                                 PlanObject(name="table", kind="fixed", size_cm=120)])


# A designer answer whose own size is wrong on purpose: a 30 cm disc on an axle.
WHEEL = {"parts": [
    {"shape": "cylinder", "size": [0.15, 0.15, 0.05], "pos": [0, 0.15, 0],
     "rot": [1.5708, 0, 0], "shade": 0.3},
    {"shape": "cylinder", "size": [0.03, 0.03, 0.08], "pos": [0, 0.15, 0],
     "rot": [1.5708, 0, 0], "shade": 0.7}],
    "hold": {"mode": "side", "y": 0.15}, "fixed": False, "height_m": 0.3}


@pytest.fixture
def designer(seeded, monkeypatch):
    """Stub the model; record what it was asked."""
    db.execute("DELETE FROM props")
    asked = []

    def stub(system, user, schema, name, *a, **k):
        asked.append(user)
        return WHEEL
    monkeypatch.setattr(propgen, "structured_call", stub)
    yield asked
    db.execute("DELETE FROM props")


def test_numbered_names_share_a_base():
    assert [propgen.base_name(n) for n in ("wheel1", "Wheel 4", "box_2", "cup#3", "7up", "toy car")] \
        == ["wheel", "wheel", "box", "cup", "7up", "toy car"]


def test_an_attached_wheel_ends_up_smaller_than_the_toy_car(catalog):
    plan = toy_car_plan(wheel_cm=30, car_cm=15)
    assert ("wheel1", "toy car") in propgen.placements(plan, catalog)
    sizes = propgen.fit_sizes(plan, catalog)
    assert sizes["wheel1"] < sizes["toy car"] == 15
    assert sizes["table"] == 120


def test_sizes_the_plan_got_right_are_left_alone(catalog):
    assert propgen.fit_sizes(toy_car_plan(wheel_cm=3, car_cm=15), catalog)["wheel1"] == 3


def test_a_thing_set_down_in_another_is_smaller_and_chains_settle(catalog):
    # The plant goes into the pot, the pot into the crate: both shrink in turn.
    steps = [step("grasp_object", "plant"), step("move_to_station", "pot"),
             step("release_object", "pot"),
             step("grasp_object", "pot", "left"), step("move_to_station", "crate", "left"),
             step("release_object", "crate", "left")]
    plan = CompiledPlan(summary="", steps=steps, objects=[
        PlanObject(name="plant", kind="item", size_cm=40),
        PlanObject(name="pot", kind="item", size_cm=30),
        PlanObject(name="crate", kind="item", size_cm=20)])
    s = propgen.fit_sizes(plan, catalog)
    assert s["plant"] < s["pot"] < s["crate"] == 20


def test_a_pour_is_not_a_placement(catalog):
    # The bottle is carried over the glass and tipped, never let go there.
    steps = [step("grasp_bottle", "juice"), step("move_to_station", "glass"),
             step("pour_into", "glass"), step("move_to_station", "table"),
             step("release_object", "table")]
    plan = CompiledPlan(summary="", steps=steps, objects=[
        PlanObject(name="juice", kind="bottle", size_cm=25),
        PlanObject(name="glass", kind="glass", size_cm=12)])
    assert ("juice", "glass") not in propgen.placements(plan, catalog)
    assert propgen.fit_sizes(plan, catalog)["juice"] == 25


def test_copies_of_one_thing_may_stack_at_the_same_size(catalog):
    steps = [step("grasp_object", "box2"), step("move_to_station", "box1"),
             step("release_object", "box1")]
    plan = CompiledPlan(summary="", steps=steps, objects=[
        PlanObject(name="box1", kind="item", size_cm=10),
        PlanObject(name="box2", kind="item", size_cm=10)])
    assert propgen.fit_sizes(plan, catalog) == {"box1": 10, "box2": 10}


def test_old_plans_without_sizes_are_unchanged(catalog):
    plan = toy_car_plan(wheel_cm=None, car_cm=None)
    assert propgen.fit_sizes(plan, catalog) == {"wheel1": None, "toy car": None, "table": 120}


def test_scaling_keeps_proportions_and_the_grip():
    spec = propgen._sanitise(WHEEL)
    assert propgen.largest_dimension(spec) == pytest.approx(0.3, abs=1e-3)
    out = propgen.scaled(spec, 3)
    assert propgen.largest_dimension(out) == pytest.approx(0.03, abs=1e-3)
    disc, axle = out["parts"]
    assert disc["size"][0] / disc["size"][2] == pytest.approx(3, rel=0.01)
    assert axle["size"][0] == propgen.MIN_SIZE                   # bounds still hold
    assert out["hold"]["y"] == pytest.approx(0.015, abs=1e-4)
    assert out["height_m"] == pytest.approx(0.03, abs=1e-3)       # from the geometry


def test_very_big_things_still_fit_the_scene_in_order():
    small, wheel, car = (propgen.display_m(cm) for cm in (20, 60, 400))
    assert small == pytest.approx(0.2)
    assert small < wheel < car <= propgen.MAX_SIZE


def test_four_wheels_share_one_design_scaled_to_the_plan(designer):
    names = ["wheel1", "wheel2", "wheel3", "wheel4", "toy car"]
    sizes = {"wheel1": 3, "wheel2": 3, "wheel3": 3.2, "wheel4": 3, "toy car": 15}
    out = propgen.specs_for(names, sizes)
    assert len(designer) == 2                                  # wheel, toy car
    assert any("Object: wheel," in u for u in designer)
    assert out["wheel1"] == out["wheel2"] == out["wheel4"]
    wheel = propgen.largest_dimension(out["wheel1"])
    assert wheel == pytest.approx(0.03, abs=1e-3)
    assert wheel < propgen.largest_dimension(out["toy car"]) == pytest.approx(0.15, abs=1e-3)

    propgen.specs_for(names, sizes)
    assert len(designer) == 2                                  # all cached now


def test_a_car_wheel_is_not_a_toy_wheel(designer):
    propgen.specs_for(["wheel1"], {"wheel1": 3})
    propgen.specs_for(["wheel"], {"wheel": 60})
    assert len(designer) == 2
    propgen.specs_for(["wheel"])                               # no size: its own entry
    assert len(designer) == 3


def test_the_props_endpoint_takes_sizes_in_name_order(designer):
    client = TestClient(api.app)
    r = client.get("/api/props", params={"names": "Wheel1,toy car,plant", "sizes": "3,15,"})
    props = r.json()["props"]
    assert set(props) == {"wheel1", "toy car", "plant"}
    assert propgen.largest_dimension(props["wheel1"]) == pytest.approx(0.03, abs=1e-3)
    assert propgen.largest_dimension(props["toy car"]) == pytest.approx(0.15, abs=1e-3)
    assert propgen.largest_dimension(props["plant"]) == pytest.approx(0.3, abs=1e-3)


def test_the_plan_response_carries_fitted_sizes(seeded):
    plan = toy_car_plan(wheel_cm=30, car_cm=15)
    pid = db.execute("INSERT INTO plans (prompt, robot_model, plan_json, valid) VALUES (?,?,?,?)",
                     ("attach the wheels to the toy car", "Spirit AI Moz1",
                      plan.model_dump_json(), 0))
    try:
        body = TestClient(api.app).get(f"/api/plans/{pid}").json()
        sizes = {o["name"]: o["size_cm"] for o in body["objects"]}
        assert sizes["wheel1"] < sizes["toy car"] == 15
    finally:
        db.execute("DELETE FROM plans WHERE id = ?", (pid,))


def test_the_planner_sizes_every_object():
    item = _act_schema()["properties"]["objects"]["items"]
    assert "size_cm" in item["required"]
    script = {"objects": [{"name": "wheel1", "kind": "item", "size_cm": 3},
                          {"name": "toy car", "kind": "item", "size_cm": "big"}],
              "goal": "", "phases": []}
    plan = _to_plan({"summary": "", "sequence": []}, script)
    assert [o.size_cm for o in plan.objects] == [3, None]
