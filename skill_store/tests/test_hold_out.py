"""Holding a thing out to the customer: "prepare me a tea, I'll pour the water
myself" ends with the cup still in one hand. The plan declares that, and the
simulator must not call it a loose end -- nor any other thing left in hand."""
from app.compiler import _act_schema, _to_plan
from app.models import CompiledPlan, Step
from app.validator import is_blocking, validate

KINDS = {"tea cup": "glass", "tea bag": "item", "table": "fixed"}


def s(skill_id, target=None, hand=None):
    return Step(skill_id=skill_id, params={"target": target} if target else {},
                planned_hand=hand)


def tea_plan():
    """Left hand picks up the cup and keeps it; right drops the bag in."""
    return [s("locate_object", "tea cup", "left"), s("grasp_glass", "tea cup", "left"),
            s("locate_object", "tea bag", "right"), s("grasp_object", "tea bag", "right"),
            s("move_to_station", "tea cup", "right"), s("release_object", None, "right")]


def loose(issues):
    return [i for i in issues if i.kind == "loose_end"]


def test_a_cup_held_out_on_purpose_is_not_a_loose_end(catalog):
    issues, _ = validate(tea_plan(), catalog, kinds=KINDS, keep=["tea cup"])
    assert not loose(issues)
    assert not any(is_blocking(i) for i in issues)


def test_without_the_declaration_it_still_is(catalog):
    issues, _ = validate(tea_plan(), catalog, kinds=KINDS)
    assert len(loose(issues)) == 1


def test_only_the_declared_thing_may_stay_in_hand(catalog):
    issues, _ = validate(tea_plan(), catalog, kinds=KINDS, keep=["tea bag"])
    assert len(loose(issues)) == 1


def test_the_planner_declares_what_it_keeps_holding():
    assert "end_holding" in _act_schema()["required"]
    script = {"objects": [{"name": "tea cup", "kind": "glass", "size_cm": 9},
                          {"name": "tea bag", "kind": "item", "size_cm": 6}],
              "goal": "", "phases": [], "end_holding": ["tea cup", "kettle"]}
    plan = _to_plan({"summary": "", "sequence": []}, script)
    assert plan.end_holding == ["tea cup"]           # only things the plan has
    assert CompiledPlan.model_validate_json(plan.model_dump_json()).end_holding == ["tea cup"]


def test_old_plans_load_without_it():
    assert CompiledPlan.model_validate_json('{"summary": "", "steps": []}').end_holding == []
