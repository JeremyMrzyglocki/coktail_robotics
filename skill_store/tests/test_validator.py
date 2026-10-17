"""The simulator's rules. These are the checks that stand between a language
model's plan and a robot arm, so each rule gets a test."""
from app.models import MissingSkill, Step
from app.validator import assign_hands, hand_episodes, is_blocking, validate

JUICE_KINDS = {"juice": "bottle", "glass": "glass", "table": "fixed"}


def s(skill_id, target=None, **kw):
    return Step(skill_id=skill_id, params={"target": target} if target else {}, **kw)


def juice_plan():
    return [s("locate_object", "juice"), s("grasp_bottle", "juice"),
            s("move_to_station", "glass"), s("pour_into", "glass"),
            s("move_to_station", "table"), s("release_object", "table")]


def blocking(issues):
    return [i.kind for i in issues if is_blocking(i)]


def test_juice_plan_is_valid(catalog):
    issues, _ = validate(juice_plan(), catalog, kinds=JUICE_KINDS)
    assert blocking(issues) == []
    assert not any(i.kind == "loose_end" for i in issues)


def test_pour_before_grasp_is_blocked(catalog):
    plan = [s("locate_object", "juice"), s("pour_into", "glass")]
    issues, _ = validate(plan, catalog, kinds=JUICE_KINDS)
    assert "unmet_precondition" in blocking(issues)


def test_empty_plan_is_blocked(catalog):
    assert blocking(validate([], catalog)[0]) == ["empty_plan"]


def test_unknown_skill_is_blocked(catalog):
    assert "unknown_skill" in blocking(validate([s("teleport")], catalog)[0])


def test_bottle_grasp_on_an_item_is_rejected(catalog):
    plan = [s("locate_object", "paint bucket"), s("grasp_bottle", "paint bucket")]
    issues, _ = validate(plan, catalog, kinds={"paint bucket": "item"})
    wrong = [i for i in issues if i.kind == "wrong_object"]
    assert wrong and "grasp_object" in wrong[0].detail


def test_item_grasp_on_an_item_is_fine(catalog):
    plan = [s("locate_object", "paint bucket"), s("grasp_object", "paint bucket")]
    issues, _ = validate(plan, catalog, kinds={"paint bucket": "item"})
    assert not any(i.kind == "wrong_object" for i in issues)


def test_object_kind_unknown_skips_the_check(catalog):
    plan = [s("locate_object", "mystery"), s("grasp_bottle", "mystery")]
    assert not any(i.kind == "wrong_object" for i in validate(plan, catalog)[0])


def test_ending_with_a_held_bottle_is_a_loose_end_not_a_block(catalog):
    plan = juice_plan()[:4]
    issues, _ = validate(plan, catalog, kinds=JUICE_KINDS)
    assert blocking(issues) == []
    assert any(i.kind == "loose_end" for i in issues)


def test_pouring_from_an_empty_glass_is_rejected(catalog):
    kinds = {"glass": "glass", "shaker": "shaker", "table": "fixed"}
    plan = [s("locate_object", "glass"), s("grasp_glass", "glass"),
            s("move_to_station", "shaker"), s("pour_into", "shaker")]
    assert "wrong_flow" in blocking(validate(plan, catalog, kinds=kinds)[0])


def test_a_whole_episode_shares_one_hand(catalog):
    hands = assign_hands(juice_plan(), catalog)
    assert len(set(hands)) == 1
    assert hand_episodes(juice_plan(), catalog) == [[0, 1, 2, 3, 4, 5]]


def test_override_moves_the_whole_episode(catalog):
    hands = assign_hands(juice_plan(), catalog, {2: "right"})
    assert set(hands) == {"right"}


def test_holding_one_thing_while_fetching_another_uses_both_hands(catalog):
    kinds = {"shaker": "shaker", "white rum": "bottle"}
    plan = [s("locate_object", "shaker"), s("grasp_shaker", "shaker"),
            s("locate_object", "white rum"), s("grasp_bottle", "white rum")]
    hands = assign_hands(plan, catalog)
    assert hands[0] == hands[1] and hands[2] == hands[3] and hands[0] != hands[2]
    assert "unmet_precondition" not in blocking(validate(plan, catalog, kinds=kinds)[0])


def gap(pid, after, pre=(), post=()):
    return MissingSkill(proposed_id=pid, name=pid, description="", insert_after=after,
                        preconditions=list(pre), postconditions=list(post))


def test_gap_effects_are_seen_by_later_steps(catalog):
    # A missing "take the thing out" leaves the hand holding it; the move after
    # it must not fail for lack of `holding`.
    plan = [s("move_to_station", "table"), s("release_object", "table")]
    gaps = [gap("take_out", -1, pre=["hand_empty"], post=["holding"])]
    issues, _ = validate(plan, catalog, gaps=gaps)
    assert "unmet_precondition" not in blocking(issues)


def test_gap_past_the_end_does_not_crash(catalog):
    gaps = [gap("wave", 99, post=["waved"])]
    issues, state = validate(juice_plan(), catalog, kinds=JUICE_KINDS, gaps=gaps)
    assert "waved" in state


def test_dropping_into_a_shaker_without_naming_it_fills_the_shaker(catalog):
    kinds = {"ice": "item", "shaker": "shaker", "glass": "glass", "table": "fixed"}
    plan = [s("locate_object", "ice"), s("grasp_object", "ice"),
            s("move_to_station", "shaker"), s("release_object"),        # no target
            s("locate_object", "shaker"), s("grasp_shaker", "shaker"),
            s("move_to_station", "glass"), s("pour_into", "glass")]
    assert "wrong_flow" not in blocking(validate(plan, catalog, kinds=kinds)[0])


def test_a_camera_check_waits_for_the_work_it_checks(catalog):
    from app.validator import dependency_graph
    plan = [s("locate_object", "cloth"), s("grasp_cloth", "cloth"), s("wipe_surface", "table"),
            s("move_to_station", "table"), s("release_object", "table"),
            s("verify_surface_clean", "table")]
    graph = dependency_graph(plan, catalog)
    assert graph[-1]["layer"] > graph[-2]["layer"]


SMOOTHIE_KINDS = {"banana": "item", "milk": "bottle", "blender": "item", "glass": "glass",
                  "table": "fixed"}


def smoothie_start():
    return [s("locate_object", "banana"), s("grasp_object", "banana"),
            s("move_to_station", "blender"), s("release_object"),
            s("locate_object", "milk"), s("grasp_bottle", "milk"),
            s("move_to_station", "blender"), s("pour_into", "blender"),
            s("move_to_station", "table"), s("release_object")]


def test_backwards_pour_names_what_to_pour_from(catalog):
    plan = smoothie_start() + [s("locate_object", "glass"), s("grasp_glass", "glass"),
                               s("move_to_station", "blender"), s("pour_into", "glass")]
    flow = [i for i in validate(plan, catalog, kinds=SMOOTHIE_KINDS)[0] if i.kind == "wrong_flow"]
    assert flow and "blender" in flow[0].detail.split("What holds something now:")[1]


def test_picking_something_up_and_putting_it_back_unused_is_flagged(catalog):
    plan = smoothie_start() + [s("locate_object", "blender"), s("grasp_object", "blender"),
                               s("move_to_station", "table"), s("release_object"),
                               s("run_blender")]
    kinds = [i.kind for i in validate(plan, catalog, kinds=SMOOTHIE_KINDS)[0]]
    assert "pointless_move" in kinds


def test_a_used_or_relocated_object_is_not_a_pointless_move(catalog):
    for plan in (juice_plan(), smoothie_start()):
        kinds = SMOOTHIE_KINDS | JUICE_KINDS
        assert "pointless_move" not in [i.kind for i in validate(plan, catalog, kinds=kinds)[0]]


def test_an_unmet_step_before_a_grasp_does_not_crash_the_ledgers(catalog):
    plan = [s("pour_into", "glass"), s("locate_object", "juice"), s("grasp_bottle", "juice")]
    assert "unmet_precondition" in blocking(validate(plan, catalog, kinds=JUICE_KINDS)[0])
