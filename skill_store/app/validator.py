"""STRIPS-lite plan validation.

The language model proposes; this module decides. It catches the two failures a
planner actually makes: naming a skill that does not exist, and ordering steps so
a precondition is unmet (pouring before grasping). Nothing reaches the robot
without passing through here.
"""
from __future__ import annotations

import itertools

from typing import Any

from .models import Step, ValidationIssue

# Predicates that belong to ONE hand rather than to the world. Scoping these per
# hand is what lets two sub-chains stop sharing state and run at the same time.
#
# object_located is hand-scoped on purpose: locating is a policy rollout that moves
# the arm (wrist camera over the table), and its result is consumed by that same
# arm's grasp. As a world fact it chained every locate to the previous locate and
# floated off on a branch of its own, detached from the grasp it exists for.
# holding / positioned are what move_to_station and release_object reason about,
# whatever the held thing is.
HAND_SCOPED: set[str] = {
    "hand_empty", "bottle_grasped", "glass_grasped", "shaker_grasped",
    "scoop_grasped", "cloth_grasped", "object_grasped",
    "object_located", "holding", "positioned",
}

HANDS = ("left", "right")

# World state the robot starts a plan in. hand_empty holds for both hands.
WORLD_INITIAL: set[str] = {"coaster_ready", "glass_placed"}
INITIAL_STATE: set[str] = WORLD_INITIAL | {"hand_empty"}


def scoped(pred: str, hand: str | None) -> str:
    """bottle_grasped + 'left' -> 'bottle_grasped@left'. World facts are unscoped."""
    if pred in HAND_SCOPED and hand:
        return f"{pred}@{hand}"
    return pred


def initial_scoped() -> set[str]:
    state = set(WORLD_INITIAL)
    for hand in HANDS:
        state.add(f"hand_empty@{hand}")
    return state


def hands_required(skill: dict[str, Any]) -> int:
    """How many hands this skill occupies. 0 = hand-agnostic (pure perception)."""
    explicit = skill.get("hands")
    if explicit:
        return int(explicit)
    touches = set(skill.get("preconditions", [])) | set(skill.get("postconditions", [])) \
        | set(skill.get("deletes", []))
    return 1 if touches & HAND_SCOPED else 0


def _gap_skill(gap: Any) -> dict[str, Any]:
    """A gap as the simulator sees it: the conditions it declares. A gap that
    leaves the hand empty has let go of whatever it held; one that leaves it
    holding something it was not holding before has picked it up, like a grasp,
    and used up the located object. A gap that only needs an empty hand (open a
    bag) leaves it empty."""
    pre, post = list(gap.preconditions), list(gap.postconditions)
    picks_up = any(p == "holding" or p.endswith("_grasped") for p in post) \
        and "holding" not in pre
    if "hand_empty" in post:
        deletes = sorted(HAND_SCOPED - {"hand_empty"})
    elif picks_up:
        deletes = ["hand_empty", "object_located"]
    else:
        deletes = []
    return {"preconditions": pre, "postconditions": post, "deletes": deletes}


def _sequence(steps: list[Step], catalog: dict[str, Any], gaps: list[Any] | None
              ) -> list[tuple[str, int, dict[str, Any], str | None]]:
    """Steps and gaps in plan order, as (what, index, skill, planned hand)."""
    after: dict[int, list[int]] = {}
    for j, g in enumerate(gaps or []):
        after.setdefault(max(-1, min(g.insert_after, len(steps) - 1)), []).append(j)

    def gap(j: int) -> tuple[str, int, dict[str, Any], str | None]:
        return ("gap", j, _gap_skill(gaps[j]), getattr(gaps[j], "hand", None))

    seq = [gap(j) for j in after.get(-1, [])]
    for i, step in enumerate(steps):
        seq.append(("step", i, catalog.get(step.skill_id, {}),
                    getattr(step, "planned_hand", None)))
        seq += [gap(j) for j in after.get(i, [])]
    return seq


def _episode_runs(steps: list[Step], catalog: dict[str, Any],
                  gaps: list[Any] | None = None
                  ) -> tuple[list[list[int]], set[tuple[int, int]], dict[int, int],
                             dict[int, str]]:
    """Episodes, plus the pairs of episodes that are open at the same time.

    Two hands means up to two episodes can be open at once: holding the shaker in
    one hand while the other fetches the rum. A step joins the open episode whose
    hand carries what it needs (the grasp joins its locate, the pour joins its
    grasp). A step that needs an empty hand while every open episode is busy
    starts a new one, which overlaps the busy one and so must go on the other
    hand.

    Gaps take part with the conditions they declare -- a missing "take a slice
    out of the bag" leaves that hand holding the slice -- so the steps around
    them land on the right hand.

    A planned hand (from the compiler) overrides that inference: the step joins
    the open episode on its hand, or starts one there. That is what lets one
    hand hold the bag while the other reaches in -- the facts alone cannot say
    which hand reaches. Returns (episodes as step indices, overlapping episode
    pairs, gap index -> episode, episode -> planned hand).
    """
    episodes: list[list[int]] = []
    held: dict[int, set[str]] = {}          # open episode -> hand facts it carries
    recent: list[int] = []                  # open episodes, least recent first
    overlaps: set[tuple[int, int]] = set()
    gap_ep: dict[int, int] = {}
    lane: dict[int, str] = {}               # episode -> planned hand

    def start(planned: str | None) -> int:
        ep = len(episodes)
        episodes.append([])
        held[ep] = set()
        overlaps.update((min(o, ep), max(o, ep)) for o in recent)
        recent.append(ep)
        if planned:
            lane[ep] = planned
        return ep

    for what, i, skill, planned in _sequence(steps, catalog, gaps):
        if hands_required(skill) == 0:
            continue
        needs = set(skill.get("preconditions", [])) & HAND_SCOPED - {"hand_empty"}
        wants_empty = "hand_empty" in skill.get("preconditions", [])
        carrying = [e for e in recent if needs & held[e]]

        if planned in HANDS:
            same = [e for e in recent if lane.get(e) == planned]
            # An unplanned episode carrying what this step needs is adopted.
            free = [e for e in carrying if e not in lane]
            # Hand facts sit on one arm. If the planned hand carries none of what
            # this step needs and another episode carries all of it, the label is
            # wrong (locate on the right, grasp on the left): the facts win.
            whole = [e for e in carrying if needs <= held[e]]
            if needs and whole and not (same and needs & held[same[-1]]):
                ep = whole[-1]
                lane.setdefault(ep, planned)
            elif same:
                ep = same[-1]
            elif free:
                ep = free[-1]
                lane[ep] = planned
            elif len(recent) < len(HANDS):
                ep = start(planned)
            else:
                ep = recent[-1]             # both hands busy; validation says so
        elif carrying:
            ep = max(carrying, key=lambda e: (len(needs & held[e]), recent.index(e)))
        elif recent and not (wants_empty and len(recent) < len(HANDS)):
            ep = recent[-1]                 # nothing fits; stay on the busiest hand
        else:
            ep = start(None)
        if what == "step":
            episodes[ep].append(i)
        else:
            gap_ep[i] = ep
        recent.remove(ep)
        recent.append(ep)

        held[ep] -= set(skill.get("deletes", []))
        held[ep] |= set(skill.get("postconditions", [])) & HAND_SCOPED - {"hand_empty"}
        if not held[ep]:
            # Nothing left on the hand: this episode is finished.
            recent.remove(ep)
            del held[ep]

    return episodes, overlaps, gap_ep, lane


def hand_episodes(steps: list[Step], catalog: dict[str, Any],
                  gaps: list[Any] | None = None) -> list[list[int]]:
    """Group steps that must share a hand.

    An episode runs from the first step that leaves something on a hand (a located
    object, a grasp) to the step that frees it again. Everything in between is the
    same hand doing the same job, so switching any one of them switches all of
    them -- you cannot locate with the left wrist camera, grasp with the left hand
    and pour with the right.
    """
    return [ep for ep in _episode_runs(steps, catalog, gaps)[0] if ep]


def _choose_hands(episodes: list[list[int]], overlaps: set[tuple[int, int]],
                  overrides: dict[int, str],
                  lane: dict[int, str] | None = None) -> dict[int, str]:
    """A person's override first, then the compiler's planned hand, then whatever
    hand an overlapping episode left free."""
    lane = lane or {}
    chosen: dict[int, str] = {}
    for e, ep in enumerate(episodes):
        pick = next((overrides[i] for i in ep if i in overrides), None)
        if pick:
            chosen[e] = pick
    for e in range(len(episodes)):
        if e in chosen:
            continue
        taken = {chosen[o] for pair in overlaps if e in pair
                 for o in pair if o != e and o in chosen}
        if lane.get(e) and lane[e] not in taken:
            chosen[e] = lane[e]
        else:
            chosen[e] = next((h for h in HANDS if h not in taken), lane.get(e, "left"))
    return chosen


def gap_hands(steps: list[Step], catalog: dict[str, Any],
              overrides: dict[int, str] | None = None,
              gaps: list[Any] | None = None) -> list[str | None]:
    """The hand each gap would be done with, aligned to `gaps`."""
    episodes, overlaps, gap_ep, lane = _episode_runs(steps, catalog, gaps)
    chosen = _choose_hands(episodes, overlaps, overrides or {}, lane)
    return [chosen.get(gap_ep[j]) if j in gap_ep else None
            for j in range(len(gaps or []))]


def assign_hands(steps: list[Step], catalog: dict[str, Any],
                 overrides: dict[int, str] | None = None,
                 gaps: list[Any] | None = None) -> list[str | None]:
    """Give every step a hand, honouring overrides and keeping episodes together.

    Episodes open at the same time go on opposite hands. An override decides its
    own episode; an episode without one takes the hand its overlapping partner
    left free, or the left hand.
    """
    overrides = overrides or {}
    episodes, overlaps, _, lane = _episode_runs(steps, catalog, gaps)
    chosen = _choose_hands(episodes, overlaps, overrides, lane)

    hands: list[str | None] = [None] * len(steps)
    for e, ep in enumerate(episodes):
        for i in ep:
            hands[i] = chosen[e]
    # A step outside any episode but still needing a hand gets its override or left.
    for i, step in enumerate(steps):
        if hands[i] is None and hands_required(catalog.get(step.skill_id, {})) > 0:
            hands[i] = overrides.get(i, "left")
    return hands

# Places wide enough for both arms at once. Anything else (a glass, a shaker, a
# blender jar) fits one held object over it at a time.
SHARED_PLACES: set[str] = {"table", "the table", "counter", "bar", "bar mat",
                           "work surface", "workspace", "tray", "shelf"}

STRUCTURE_RANK = {"dualarm": 0, "wholebody_without_base": 1, "wholebody": 2}

def wrong_object(skill: dict[str, Any], step: Step, kinds: dict[str, str],
                 catalog: dict[str, Any]) -> str | None:
    """Why this skill cannot act on this step's target, or None if it can.

    Both sides are declared data: the skill's `acts_on` comes from the catalog,
    the object's kind from the compiler's object list. Nothing here knows what a
    bucket is.
    """
    allowed = skill.get("acts_on") or []
    target = str(step.params.get("target", ""))
    kind = kinds.get(target)
    if not allowed or not kind or kind in allowed:
        return None
    def a(word: str) -> str:
        return ("an " if word[:1] in "aeiou" else "a ") + word

    fits = sorted(sid for sid, s in catalog.items()
                  if kind in (s.get("acts_on") or []) and s.get("category") != "composite")
    instead = f" Skills that handle {a(kind)}: {', '.join(fits)}." if fits else \
        f" No catalog skill handles {a(kind)}; list it as missing."
    return (f"{skill['name']} handles {' or '.join(a(k) for k in allowed)}, but "
            f"'{target}' is {a(kind)}.{instead}")


def validate(
    steps: list[Step],
    catalog: dict[str, Any],
    robot_structure: str = "dualarm",
    hands: list[str | None] | None = None,
    kinds: dict[str, str] | None = None,
    gaps: list[Any] | None = None,
) -> tuple[list[ValidationIssue], set[str]]:
    """Simulate the plan, per hand. Returns (issues, final world state).

    `kinds` maps target names to object kinds, for the acts_on check. `gaps` are
    the plan's missing skills: they are simulated in place with the effects they
    declare (their preconditions are not checked -- they are proposals), so a
    step after a gap sees what the gap would leave behind, and a tool held
    through a run of gaps is still in hand when the plan ends.
    """
    issues: list[ValidationIssue] = []
    state = initial_scoped()
    kinds = kinds or {}
    gaps = gaps or []
    gaps_after: dict[int, list[int]] = {}
    for j, g in enumerate(gaps):
        at = max(-1, min(g.insert_after, len(steps) - 1))
        gaps_after.setdefault(at, []).append(j)

    if not steps:
        issues.append(ValidationIssue(
            step_index=None, kind="empty_plan",
            detail="The planner returned no executable steps.",
        ))
        return issues, state

    if hands is None:
        hands = assign_hands(steps, catalog, gaps=gaps)
    # A gap's hand follows the episode it belongs to, consistent with `hands`
    # whether they came from the planner or from a person's overrides.
    ghands = gap_hands(steps, catalog,
                       {i: h for i, h in enumerate(hands) if h}, gaps) if gaps else []
    have_rank = STRUCTURE_RANK.get(robot_structure, 0)

    def apply_gaps(after: int) -> None:
        for j in gaps_after.get(after, []):
            hand = ghands[j] or (hands[after] if 0 <= after < len(hands) else None)
            skill = _gap_skill(gaps[j])
            for pred in skill["deletes"]:
                state.discard(scoped(pred, hand))
            for pred in skill["postconditions"]:
                state.add(scoped(pred, hand))

    apply_gaps(-1)
    for i, step in enumerate(steps):
        skill = catalog.get(step.skill_id)
        if skill is None:
            issues.append(ValidationIssue(
                step_index=i, kind="unknown_skill",
                detail=f"'{step.skill_id}' is not in the catalog.",
            ))
            apply_gaps(i)
            continue

        hand = hands[i] if i < len(hands) else None
        unmet = [p for p in skill.get("preconditions", [])
                 if scoped(p, hand) not in state]
        if unmet:
            where = f" (on the {hand} hand)" if hand else ""
            issues.append(ValidationIssue(
                step_index=i, kind="unmet_precondition",
                detail=(f"{skill['name']} needs {', '.join(unmet)}{where}, which no "
                        f"earlier step establishes."),
            ))

        misfit = wrong_object(skill, step, kinds, catalog)
        if misfit:
            issues.append(ValidationIssue(step_index=i, kind="wrong_object",
                                          detail=misfit))

        need = skill.get("embodiment", {}).get("structure", "dualarm")
        if STRUCTURE_RANK.get(need, 0) > have_rank:
            issues.append(ValidationIssue(
                step_index=i, kind="embodiment_mismatch",
                detail=(f"{skill['name']} requires structure '{need}'; this robot is "
                        f"configured as '{robot_structure}'."),
            ))

        if skill.get("status") == "catalog" or not skill.get("checkpoint"):
            issues.append(ValidationIssue(
                step_index=i, kind="not_executable",
                detail=(f"{skill['name']} is listed but has no trained checkpoint. "
                        f"It needs demonstration data before it can run."),
            ))

        for pred in skill.get("deletes", []):
            state.discard(scoped(pred, hand))
        for pred in skill.get("postconditions", []):
            state.add(scoped(pred, hand))
        apply_gaps(i)

    # A plan that stops with something still on a hand usually stopped early: a
    # locate nobody grasped, a bottle never put back down.
    for h in HANDS:
        left_over = sorted(p for p in ("holding", "object_located")
                           if f"{p}@{h}" in state)
        if left_over:
            last = max((i for i, x in enumerate(hands) if x == h), default=None)
            what = "still holding something" if "holding" in left_over \
                else "with an object located but never picked up"
            issues.append(ValidationIssue(
                step_index=last, kind="loose_end",
                detail=f"The plan ends with the {h} hand {what}.",
            ))

    return issues, state


def is_blocking(issue: ValidationIssue) -> bool:
    """Issues that stop the plan from being queued at all."""
    return issue.kind in {"unknown_skill", "unmet_precondition",
                          "embodiment_mismatch", "empty_plan", "wrong_object"}


def dependency_graph(
    steps: list[Step],
    catalog: dict[str, Any],
    hands: list[str | None] | None = None,
) -> list[dict[str, Any]]:
    """Work out what each step waits on, so independent work can run at once.

    Four kinds of edge, all physical:
      requires  -- needs a predicate an earlier step established
      consumes  -- clears a predicate an earlier step established
      hand      -- the same hand is still busy with the previous step
      resource  -- both steps write the same world fact (one glass, one pour
                   at a time), or both arms want the same place (only one
                   bottle fits over the glass), so they cannot overlap; or
                   the place is a thing the other hand carried, so it is not
                   there until that hand let go (stacking one cup on another)

    Scoping hand predicates per hand is what makes the parallelism real: two
    chains on different hands share no predicate and share no hand edge, so they
    land in the same layer.
    """
    if hands is None:
        hands = assign_hands(steps, catalog)

    source: dict[str, int] = {p: -1 for p in initial_scoped()}
    last_on_hand: dict[str, int] = {}
    world_writer: dict[str, int] = {}
    nodes: list[dict[str, Any]] = []
    # Where each hand is holding something, and when each place was last vacated.
    # Two arms cannot both be over the glass, so moving there waits for the other
    # hand to leave. Places are named by the move step's target param.
    occupying: dict[str, str] = {}          # hand -> place
    vacated: dict[str, tuple[int, str]] = {}  # place -> (step that left, hand)
    # What each hand carries, and where a carried thing was last set down. A
    # place that is itself a thing another hand moved (the cup a second cup is
    # stacked onto) is only there once that hand has let go of it.
    carrying: dict[str, str] = {}           # hand -> thing it picked up
    set_down: dict[str, tuple[int, str]] = {}  # thing -> (step that let go, hand)

    for i, step in enumerate(steps):
        skill = catalog.get(step.skill_id, {})
        hand = hands[i] if i < len(hands) else None
        deps: list[dict[str, Any]] = []
        seen: set[tuple[int, str]] = set()

        def add(src: int, via: str, kind: str) -> None:
            if src is None or (src, via) in seen:
                return
            seen.add((src, via))
            deps.append({"step": src, "via": via, "kind": kind})

        for pred in skill.get("preconditions", []):
            add(source.get(scoped(pred, hand)), pred, "requires")
        for pred in skill.get("deletes", []):
            src = source.get(scoped(pred, hand))
            if src is not None and src >= 0:
                add(src, pred, "consumes")

        if hand and hand in last_on_hand:
            add(last_on_hand[hand], f"{hand} hand", "hand")

        for pred in skill.get("postconditions", []):
            if pred in HAND_SCOPED:
                continue
            prev = world_writer.get(pred)
            if prev is not None:
                add(prev, pred, "resource")

        moves_to = None
        if hand and "positioned" in skill.get("postconditions", []):
            moves_to = str(step.params.get("target", "")).strip().lower() or None
        leaves = hand in occupying and (
            moves_to is not None or "holding" in skill.get("deletes", []))
        if (moves_to and moves_to not in SHARED_PLACES and moves_to in vacated
                and vacated[moves_to][1] != hand):
            add(vacated[moves_to][0], f"space over the {moves_to}", "resource")
        if moves_to and moves_to in set_down and set_down[moves_to][1] != hand:
            add(set_down[moves_to][0], f"{moves_to} set down", "resource")

        nodes.append({
            "index": i,
            "skill_id": step.skill_id,
            "name": skill.get("name", step.skill_id),
            "title": skill.get("title", ""),
            "hand": hand,
            "hands_required": hands_required(skill),
            "deps": deps,
            "produces": skill.get("postconditions", []),
        })

        for pred in skill.get("deletes", []):
            source.pop(scoped(pred, hand), None)
        for pred in skill.get("postconditions", []):
            source[scoped(pred, hand)] = i
            if pred not in HAND_SCOPED:
                world_writer[pred] = i
        if hand:
            last_on_hand[hand] = i
        if leaves:
            place = occupying.pop(hand)
            vacated[place] = (i, hand)
        if moves_to:
            occupying[hand] = moves_to
        if hand and "holding" in skill.get("deletes", []) and hand in carrying:
            set_down[carrying.pop(hand)] = (i, hand)
        elif hand and "holding" in skill.get("postconditions", []):
            thing = str(step.params.get("target", "")).strip().lower()
            if thing:
                carrying[hand] = thing

    layer: dict[int, int] = {}
    for node in nodes:
        upstream = [layer.get(d["step"], 0) for d in node["deps"] if d["step"] >= 0]
        node["layer"] = max(upstream) + 1 if upstream else 0
        layer[node["index"]] = node["layer"]

    return nodes


def schedule_depth(
    steps: list[Step],
    catalog: dict[str, Any],
    hands: list[str | None],
) -> tuple[int, int]:
    """(time slots, widest parallel branch) for one hand assignment."""
    graph = dependency_graph(steps, catalog, hands)
    width: dict[int, int] = {}
    for node in graph:
        width[node["layer"]] = width.get(node["layer"], 0) + 1
    if not width:
        return 0, 1
    return max(width) + 1, max(width.values())


def balance_hands(
    steps: list[Step],
    catalog: dict[str, Any],
    robot_structure: str = "dualarm",
    max_exhaustive: int = 13,
) -> dict[str, Any]:
    """Pick the hand assignment that finishes soonest.

    One choice per hand episode, not per step, because a hand has to finish what
    it started. The first episode is pinned to the left hand: mirroring every
    choice gives an identical schedule, so searching both halves is wasted work.

    Small plans are solved exactly. Past `max_exhaustive` episodes the exhaustive
    search stops being free, so it falls back to hill climbing -- flip one episode
    at a time, keep the flip if the schedule gets shorter, stop when none do.
    """
    episodes = hand_episodes(steps, catalog)
    baseline_hands = assign_hands(steps, catalog, {})
    base_depth, base_par = schedule_depth(steps, catalog, baseline_hands)
    base_blocking = sum(
        1 for i in validate(steps, catalog, robot_structure, baseline_hands)[0]
        if is_blocking(i)
    )

    result = {
        "overrides": {}, "episodes": len(episodes),
        "before": {"depth": base_depth, "max_parallel": base_par},
        "after": {"depth": base_depth, "max_parallel": base_par},
        "searched": 0, "method": "none",
    }
    if len(episodes) < 2:
        return result

    def score(choice: tuple[str, ...]) -> tuple[Any, ...] | None:
        overrides = {ep[0]: hand for ep, hand in zip(episodes, choice)}
        hands = assign_hands(steps, catalog, overrides)
        blocking = sum(1 for i in validate(steps, catalog, robot_structure, hands)[0]
                       if is_blocking(i))
        if blocking > base_blocking:
            return None                      # never trade correctness for speed
        depth, par = schedule_depth(steps, catalog, hands)
        left = sum(1 for h in hands if h == "left")
        right = sum(1 for h in hands if h == "right")
        # shortest first, then even wear across the two arms, then fewer handoffs
        switches = sum(1 for a, b in zip(choice, choice[1:]) if a != b)
        return (depth, abs(left - right), switches), depth, par, overrides

    best = None
    searched = 0

    if len(episodes) <= max_exhaustive:
        method = "exhaustive"
        for rest in itertools.product(("left", "right"), repeat=len(episodes) - 1):
            searched += 1
            got = score(("left",) + rest)
            if got and (best is None or got[0] < best[0]):
                best = got
    else:
        method = "hill-climb"
        choice = ["left"] * len(episodes)
        best = score(tuple(choice))
        searched += 1
        improved = True
        while improved:
            improved = False
            for i in range(1, len(episodes)):
                flipped = list(choice)
                flipped[i] = "right" if flipped[i] == "left" else "left"
                searched += 1
                got = score(tuple(flipped))
                if got and (best is None or got[0] < best[0]):
                    best, choice, improved = got, flipped, True

    if best is None:
        return result

    _, depth, par, overrides = best
    result.update({
        "overrides": {str(k): v for k, v in overrides.items()},
        "after": {"depth": depth, "max_parallel": par},
        "searched": searched, "method": method,
    })
    return result
