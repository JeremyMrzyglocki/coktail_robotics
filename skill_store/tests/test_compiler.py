"""The compiler's bookkeeping around the model call -- no model is called."""
from app.compiler import COMPILER_VERSION, GAP, _duplicate_gaps, _to_plan, cache_key
from app.models import CompiledPlan, MissingSkill, Step


def item(skill_id, target="", **gap):
    base = {"skill_id": skill_id, "target": target, "rationale": "why",
            "proposed_id": "", "name": "", "description": "", "preconditions": [],
            "postconditions": [], "dataset_id": "none", "hand": "left"}
    base.update(gap)
    return base


SCRIPT = {"objects": [{"name": "brush", "kind": "item"}], "goal": "done", "phases": []}


def test_gaps_land_after_the_step_before_them():
    raw = {"summary": "s", "combo_name": "c", "sequence": [
        item(GAP, proposed_id="warm_up"),
        item("locate_object", "brush"), item("grasp_object", "brush"),
        item(GAP, proposed_id="dip_into", dataset_id="epic-kitchens-100"),
        item(GAP, proposed_id="press_to_surface"),
        item("release_object")]}
    plan = _to_plan(raw, SCRIPT)
    assert [st.skill_id for st in plan.steps] == ["locate_object", "grasp_object",
                                                  "release_object"]
    assert [(m.proposed_id, m.insert_after) for m in plan.missing] == [
        ("warm_up", -1), ("dip_into", 1), ("press_to_surface", 1)]
    assert plan.steps[0].params == {"target": "brush"}
    assert plan.steps[2].params == {}
    assert plan.kinds() == {"brush": "item"}


def test_unknown_dataset_ids_are_dropped():
    raw = {"summary": "", "combo_name": "", "sequence": [
        item(GAP, proposed_id="x", dataset_id="spirit-pickplace")]}   # private
    assert _to_plan(raw, SCRIPT).missing[0].dataset_id == ""


def test_cache_key_covers_everything_the_answer_depends_on(catalog):
    a = cache_key("Pour Juice ", "Moz1", catalog)
    assert a == cache_key("pour   juice", "Moz1", catalog)
    assert a != cache_key("pour juice", "G1", catalog)
    assert a != cache_key("pour juice", "Moz1", catalog, structure="wholebody")
    edited = {k: dict(v) for k, v in catalog.items()}
    edited["pour_into"]["preconditions"] = ["holding"]
    assert a != cache_key("pour juice", "Moz1", edited)
    assert COMPILER_VERSION  # part of the key; bumping it retires old cache rows


def test_a_model_that_keeps_pouring_backwards_is_not_retried_forever(catalog, monkeypatch):
    from app import compiler
    script = {"objects": [{"name": "glass", "kind": "glass"}, {"name": "juice", "kind": "bottle"},
                          {"name": "table", "kind": "fixed"}], "goal": "", "phases": []}
    wrong = {"summary": "", "combo_name": "", "sequence": [
        item("locate_object", "glass"), item("grasp_glass", "glass"),
        item("move_to_station", "juice"), item("pour_into", "juice"),
        item("move_to_station", "table"), item("release_object", "table")]}
    calls = []

    def stub(*a, **k):
        calls.append(1)
        if len(calls) > 10:
            raise AssertionError("repair loop did not stop")
        return wrong
    monkeypatch.setattr(compiler, "structured_call", stub)
    plan = _to_plan(wrong, script)
    compiler._repair(plan, script, catalog, "dualarm", "sys", "user", {}, budget=2)
    assert len(calls) <= 3        # the budget, plus one extra round for the pour


def test_data_files_are_cached_until_they_change(monkeypatch):
    from app import catalog as cat
    on_disk = cat.object_kinds()
    mtime = cat._FILES["object_kinds.json"][0]
    monkeypatch.setitem(cat._FILES, "object_kinds.json", (mtime, {"cached": "x"}))
    assert cat.object_kinds() == {"cached": "x"}          # same file: no re-read
    monkeypatch.setitem(cat._FILES, "object_kinds.json", (mtime - 1, {"cached": "x"}))
    assert cat.object_kinds() == on_disk                  # file changed: re-read


def test_a_gap_that_restates_a_catalog_skill_is_caught(catalog):
    g = catalog["grasp_object"]
    plan = CompiledPlan(summary="", steps=[Step(skill_id="locate_object")], missing=[
        MissingSkill(proposed_id="grasp_item", name="", description="",
                     preconditions=g["preconditions"], postconditions=g["postconditions"]),
        MissingSkill(proposed_id="dip_into", name="", description="",
                     preconditions=["holding"], postconditions=["tool_loaded"])])
    assert _duplicate_gaps(plan, catalog) == [("grasp_item", "grasp_object")]
