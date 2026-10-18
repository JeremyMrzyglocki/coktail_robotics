"""The skill compiler: natural language -> a validated, executable plan.

Two stages, because a model that plans *from* the catalog bends the task to fit
it -- whatever the catalog cannot do gets dropped, or squashed into one gap the
size of the whole request ("draw_image_with_brush").

  1. Act it out. With no catalog in view, the model writes the request the way
     a person's hands would do it: the objects involved (each classified into a
     kind the catalog declares), phases named by their outcome, each broken into
     physical movements, and the goal.
  2. Bind. With the catalog in view, movements become catalog skills or gaps.
     Gaps are therefore movements, not tasks, and sit exactly where they happen.

Design rules, in order of importance:
  1. The model may only name skill IDs that exist. The enum is built from the
     live catalog and enforced by structured outputs, then re-checked locally.
  2. Anything the task needs but the catalog lacks is a gap, never invented into
     `steps`. That list is the product's demand signal, and each gap names the
     open dataset that could train it.
  3. Nothing here knows about buckets, brushes or painting. What a skill can act
     on is declared in the catalog (`acts_on`), what an object is gets decided
     in stage 1, and the validator compares the two.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from . import catalog as cat
from .llm import LLMError, structured_call
from .models import CompiledPlan, MissingSkill, PlanObject, Step

# Part of the cache key: a plan compiled by an older pipeline is not reused.
COMPILER_VERSION = "8"
GAP = "GAP"


ACT_PROMPT = """\
You plan how a robot with two arms and parallel grippers would carry out a \
customer's request, the way a person's two hands would. You do not know what the \
robot can already do. Describe the physical work, not products or skills.

Start state: both hands empty. Everything the request names is within reach on \
the table unless the request says otherwise. A glass already stands on a coaster \
on the table; a drink served in something else (tea or coffee in a cup) starts \
from that empty vessel standing on the table instead. Things are in the everyday state a person would find them on a \
counter: bottles open and ready to pour, food as it is sold (a banana still in \
its peel), appliances (a blender, a kettle, a toaster) standing ready on their \
base. Operating an appliance is pressing its control with a free hand; its jar or \
pot stays on the base while it runs and is only lifted to pour out the result. \
Use the fewest movements that get the work done.

objects -- every thing the work involves: tools, ingredients, containers, and the \
places things are moved to or worked on (the table, a whiteboard, a shelf).
- Give each a short, specific name ("stirring spoon", "white rum", "table") and use \
exactly that name everywhere else.
- Classify each into exactly one kind, by what a gripper would close around:
{kinds}
  Rum comes in a bottle, so "white rum" is a bottle. Soup sits in a pot: "soup" \
is a substance and "soup pot" is an item.
- size_cm: its approximate largest dimension in centimetres, as it is in this \
request. Judge every object with the others in view: the parts of a toy are \
toy-sized (a doll's teacup is ~3 cm, a real mug ~10 cm), and a thing that goes \
onto or into another is smaller than what receives it.
- If the request does not name ingredients, choose a short, typical set (two or \
three) for it.

phases -- the work in order, as the outcomes a person would name ("the bottle is \
in hand", "the glass holds juice", "the dough is flat"). Then break every phase \
into the movements that achieve it.
- why: one short sentence tying the phase to the request ("rum is the base spirit \
of a pina colada", "the scoop has to be full before it is tipped out").
- movements: what a hand physically does, each one continuous action toward one \
end, starting with a movement verb: look for X, pick up X (grasp and lift), carry \
X to Y, set X down on Y (lower and let go), tilt X into Y, press X onto Y, drag X \
along Y, lift X off Y, twist X, squeeze X, shake X, flip X, slide X. An outcome \
verb (make, build, clean, prepare, operate, perform, mix) names a phase, never a \
movement: break it down.
- Include what a tool needs before each use (load it, wet it, fill it, open it) and \
what an item needs in the state the customer describes (peel it, unwrap it).
- A cycle that repeats (fill the scoop, carry it over, tilt it out, again) is \
written once, in order, with repeats=true on each movement of the cycle.
- Do not move a thing that is already where the work needs it, and keep holding \
a thing from one phase to the next when the next phase uses it again. A thing \
that only receives another (the glass poured into, the bowl filled, the bottom \
cup of a stack) stays where it stands and is not picked up -- unless it is held \
out to the customer (below).
- Every phase changes something in the world; looking alone is not a phase, \
and neither is "both hands are empty".
- Look for a thing only right before picking it up. A destination is not \
looked for: carrying a thing to it finds it.
- hand: which hand ("left" or "right") does the movement. A hand that picks a \
thing up keeps it until it sets it down. Use one hand at a time where you can; \
when the work needs a thing held while something is done to it (hold the jar \
steady while the other hand twists the lid; hold the bag open while the other \
hand reaches in), the holding hand keeps holding and the other hand does the \
work. Setting a thing on or into another needs no holding hand: what receives \
it stands on its own.
- End with every held thing set down, so both hands are empty -- unless the \
request is to hand something over or keep holding it. Setting a thing down \
where the work puts it (on the table, in the bowl, on top of another thing) \
already empties the hand: never pick it back up or undo the work to end \
empty-handed.
- When the customer says they will finish part of the work themselves (pour \
the water, add the milk), do everything before that and hold out what they will \
work on: one hand picks it up first and keeps holding it while the other hand \
does the rest, and the work ends with it still in that hand.
- When the request is about several things of one kind (stack the cups, put \
the apples in the bowl), name each one (cup1, cup2, ...) and handle each in \
turn.
- object: the name of the thing the movement acts on or holds. place: where it \
happens, or "". For carry and set down, place is the destination -- the other \
thing when X goes onto or into it.

goal -- one sentence: what is true when the work is done.

end_holding -- the objects still in a hand when the work is done because the \
request wants them held (held out to the customer, handed over). Usually none.

Example. "pour me a glass of juice":
  objects: juice (bottle, 25 cm), glass (glass, 12 cm), table (fixed, 120 cm)
  phase "the juice is in hand": look for the juice -> pick up the juice (all left)
  phase "the glass holds juice": carry the juice over the glass ->
        tilt the juice into the glass
  phase "the juice is back on the table": carry the juice to the table ->
        set the juice down on the table
  goal: the glass holds juice and both hands are empty.

Example. "stack the boxes":
  objects: box1 (item, 10 cm), box2 (item, 10 cm), box3 (item, 10 cm), table \
(fixed, 120 cm)
  box1 is the bottom of the stack: it stays on the table, untouched.
  phase "box2 is on box1": look for box2 -> pick up box2 -> carry box2 to \
box1 -> set box2 down on box1 (all left)
  phase "box3 is on box2": look for box3 -> pick up box3 -> carry box3 to \
box2 -> set box3 down on box2 (all right)
  goal: box3 is on box2, box2 is on box1, and both hands are empty.
  Nothing is done after the last set-down: the hand is already empty.
"""


BIND_PROMPT = """\
You bind a robot's motion script to purchasable skills from the catalog below. \
You get the customer's request, the objects involved (each with a kind), and the \
work as phases of hand movements, in order. Return `sequence`: the script, in \
order, its movements turned into catalog skills or gaps.

Binding:
- First check whether one catalog skill covers a whole phase (stir covers \
putting a stirrer in the glass and circling it). Then bind the rest movement by \
movement; one skill may cover several consecutive movements. "look for the rum, \
pick it up" is locate_object(target=white rum) then grasp_bottle(target=white \
rum); "carry it over the glass" is move_to_station(target=glass); "tilt it into \
the glass" is pour_into(target=glass); "carry it to the table, set it down" is \
move_to_station(target=table) then release_object.
- A pour goes FROM what the hand holds INTO the target. To pour the blender into \
the glass: grasp_object(target=blender), move_to_station(target=glass), \
pour_into(target=glass); the glass stays where it is. Never pick up the \
destination to pour into it, and never pour from a glass or shaker that nothing \
was poured into. The simulator keeps a ledger of what each vessel contains. The destination can be \
another object: "carry cup2 over cup1, set it down on cup1" is \
move_to_station(target=cup1) then release_object.
- Only use a skill whose `acts_on` includes the kind of its target (an empty \
acts_on takes anything). A bottle grasp on an item is rejected.
- Prefer status "trained" over "beta" over "catalog" when more than one fits; a \
"catalog" skill that fits still beats a gap.
- target is an object name from the list, exactly, or "" when the skill takes \
none. For move_to_station it is the destination.
- hand: the hand of the movement the item binds; an enabling step you add takes \
the hand of the movement it enables. The simulator tracks each hand separately.
- Keep the script's order and every movement in it. You may add an enabling step the \
script leaves implicit (locate_object right before a grasp, move_to_station before \
a release or a pour, putting a held thing down before grasping another), but do \
not add new work.

Gaps -- movements no catalog skill covers, judged by what the skill does, not its \
name: a grasp includes the lift, release_object includes lowering before letting \
go, any carrying is move_to_station. Each skill's `aka` lists other ways its \
movement gets described ("drag the cloth over" is wipe_surface, "turn on the \
blender" is run_blender): check those before declaring a gap.
- One gap per movement. skill_id "GAP". proposed_id names it as a reusable motion \
primitive, verb plus a generic object or relation (twist_open, press_to_surface, \
tilt_out, peel_item), never the phase or the task. name: title case of it. \
description: one line naming what it acts on here.
- preconditions / postconditions: use the catalog's predicates where one fits \
(holding, positioned, hand_empty, vessel_filled, ...); otherwise new \
lower_snake_case ones. A gap done with a held tool keeps it held.
- dataset_id: the open dataset below whose footage shows this kind of hand \
movement, judged by its `covers`. Match the movement (pressing, dragging, \
scooping, twisting, tilting), not the subject of the request: footage of someone \
stirring soup covers stirring a cocktail. Prefer a full dataset over a small \
sample of it. "none" only when no dataset's footage plausibly contains that \
movement.

rationale -- shown to the customer next to the step: one short sentence on why it \
is needed here, from its phase's why. Not a restatement of the skill's name. On \
the last item of a repeating cycle, say that the cycle repeats until done.

Mechanics, checked by a simulator: each skill's preconditions must hold from the \
start state (hand_empty on both hands, coaster_ready, glass_placed) or an earlier \
step. One gripper holds one thing at a time. A hand-scoped fact (hand_empty, \
object_located, holding, positioned, *_grasped) only counts on the hand that \
produced it.

combo_name: the whole sequence as one product, title case, two to four words, \
naming the process. summary: one sentence for the customer -- what the robot will \
do and what is not yet possible. No marketing language.

DATASETS
========
{datasets}

CATALOG
=======
"""


def _kinds_block() -> str:
    return "\n".join(f"  - {k}: {d}" for k, d in cat.object_kinds().items())


def _datasets_block() -> str:
    lines = []
    for d in sorted(cat.open_datasets().values(), key=lambda d: d["id"]):
        if d.get("episodes_total") is not None:
            # A single-task robot dataset: its id and task line say enough, and
            # there are over a hundred of them, so keep each to one short line.
            lines.append(json.dumps({"id": d["id"], "covers": d.get("covers", "")[:90]},
                                    separators=(",", ":"), ensure_ascii=False))
            continue
        lines.append(json.dumps({
            "id": d["id"], "name": d["name"], "kind": d.get("kind"),
            "covers": d.get("covers", ""), "good_for": d.get("good_for", []),
        }, separators=(",", ":")))
    return "\n".join(lines)


def _catalog_block(catalog: dict[str, dict[str, Any]]) -> str:
    """Compact, stable rendering. Sorted so the cache prefix does not churn."""
    lines = []
    for sid in sorted(catalog):
        s = catalog[sid]
        lines.append(json.dumps({
            "id": s["id"],
            "name": s["name"],
            "status": s["status"],
            "price_eur": s["price_eur"],
            "vendor": s["vendor"],
            "desc": s["description"],
            "aka": s.get("aliases", []),
            "acts_on": s.get("acts_on", []),
            "pre": s.get("preconditions", []),
            "post": s.get("postconditions", []),
            "deletes": s.get("deletes", []),
            "structure": s.get("embodiment", {}).get("structure", "dualarm"),
        }, separators=(",", ":")))
    return "\n".join(lines)


def _act_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "kind": {"type": "string", "enum": sorted(cat.object_kinds())},
                        "size_cm": {"type": "number"},
                    },
                    "required": ["name", "kind", "size_cm"],
                    "additionalProperties": False,
                },
            },
            "phases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "outcome": {"type": "string"},
                        "why": {"type": "string"},
                        "movements": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "movement": {"type": "string"},
                                    "hand": {"type": "string", "enum": ["left", "right"]},
                                    "object": {"type": "string"},
                                    "place": {"type": "string"},
                                    "repeats": {"type": "boolean"},
                                },
                                "required": ["movement", "hand", "object", "place",
                                             "repeats"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["outcome", "why", "movements"],
                    "additionalProperties": False,
                },
            },
            "goal": {"type": "string"},
            "end_holding": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["objects", "phases", "goal", "end_holding"],
        "additionalProperties": False,
    }


def _bind_schema(skill_ids: list[str], dataset_ids: list[str]) -> dict[str, Any]:
    # Nothing request-specific in here: the schema is part of the cached prefix
    # and is compiled into a grammar once, so a per-request enum (the object
    # names) made every compile miss the cache and recompile it. Targets are
    # matched to the object names in code instead (_snap_target).
    strings = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {
            "combo_name": {"type": "string"},
            "summary": {"type": "string"},
            "sequence": {
                "type": "array",
                # A skill item or a gap item. Two shapes rather than one with
                # empty gap fields on every skill: on a forty-step plan that is
                # most of the output, and output is most of the wait.
                "items": {"anyOf": [
                    {
                        "type": "object",
                        "properties": {
                            # The hard constraint: only real skills can appear here.
                            "skill_id": {"type": "string", "enum": skill_ids},
                            "target": {"type": "string"},
                            "hand": {"type": "string", "enum": ["left", "right"]},
                            "rationale": {"type": "string"},
                        },
                        "required": ["skill_id", "target", "hand", "rationale"],
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "properties": {
                            "skill_id": {"type": "string", "enum": [GAP]},
                            "proposed_id": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "preconditions": strings,
                            "postconditions": strings,
                            "dataset_id": {"type": "string",
                                           "enum": dataset_ids + ["none"]},
                            "hand": {"type": "string", "enum": ["left", "right"]},
                            "rationale": {"type": "string"},
                        },
                        "required": ["skill_id", "proposed_id", "name", "description",
                                     "preconditions", "postconditions", "dataset_id",
                                     "hand", "rationale"],
                        "additionalProperties": False,
                    },
                ]},
            },
        },
        "required": ["combo_name", "summary", "sequence"],
        "additionalProperties": False,
    }


def cache_key(prompt: str, robot_model: str, catalog: dict[str, dict[str, Any]],
              structure: str = "dualarm") -> str:
    """Everything the compiler's answer depends on, hashed. Editing the
    compiler's prompts, a skill's conditions, status or acts_on, the datasets or
    the object kinds retires the cached plans built on the old version, as does
    a different robot structure."""
    atoms = {k: v for k, v in catalog.items() if v.get("category") != "composite"}
    h = hashlib.sha256()
    for part in (COMPILER_VERSION, ACT_PROMPT, BIND_PROMPT,
                 " ".join(prompt.lower().split()), robot_model,
                 structure, _catalog_block(atoms), _datasets_block(), _kinds_block()):
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()[:32]


class CompileError(RuntimeError):
    pass


def act_out(prompt: str, robot_model: str) -> dict[str, Any]:
    """Stage 1: the request as objects, phases of hand movements, and a goal."""
    system = ACT_PROMPT.format(kinds=_kinds_block())
    user = f"Robot: {robot_model}\nCustomer request: {prompt.strip()}"
    # Acting it out is the reasoning-heavy half; binding is a constrained lookup.
    # COMPILER_ACT_MODEL lets the first use a stronger model than the second.
    model = os.environ.get("COMPILER_ACT_MODEL", "").strip() or None
    try:
        script = structured_call(system, user, _act_schema(), "motion_script", model)
    except LLMError as exc:
        raise CompileError(str(exc)) from exc
    if not any(p.get("movements") for p in script.get("phases", [])):
        raise CompileError("the planner could not describe this as physical work")
    return script


def _size_cm(v: Any) -> float | None:
    """The planner's size estimate, or None when it gave nothing usable."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _names(script: dict[str, Any]) -> list[str]:
    """Every valid target: the objects, and every place a movement names ("carry
    the jar to the blender base" needs blender base even if it is not an object)."""
    return sorted({o["name"] for o in script["objects"]} |
                  {m[k] for ph in script["phases"] for m in ph["movements"]
                   for k in ("object", "place") if m[k]})


def _snap_target(target: str, names: list[str]) -> str:
    """The object name a target means: exact, else ignoring case, spacing and
    a leading "the". Anything else is kept as written; the validator judges it."""
    t = (target or "").strip()
    if not t or t in names:
        return t
    def key(s: str) -> str:
        s = " ".join(s.lower().split())
        return s[4:] if s.startswith("the ") else s
    by_key = {key(n): n for n in names}
    return by_key.get(key(t), t)


def _to_plan(raw: dict[str, Any], script: dict[str, Any]) -> CompiledPlan:
    """Split the bound sequence into steps and gaps; a gap sits after the step
    before it, so its position is exact by construction."""
    datasets = cat.open_datasets()
    names = _names(script)
    steps: list[Step] = []
    missing: list[MissingSkill] = []
    for item in raw.get("sequence", []):
        if item["skill_id"] == GAP:
            ds = datasets.get(item.get("dataset_id", ""))
            missing.append(MissingSkill(
                proposed_id=item["proposed_id"] or "unnamed_motion",
                name=item["name"] or item["proposed_id"],
                description=item["description"],
                preconditions=item["preconditions"],
                postconditions=item["postconditions"],
                why_needed=item["rationale"],
                insert_after=len(steps) - 1,
                dataset_id=ds["id"] if ds else "",
                dataset_name=ds["name"] if ds else "",
                hand=item.get("hand"),
            ))
        else:
            target = _snap_target(item.get("target", ""), names)
            params = {"target": target} if target else {}
            steps.append(Step(skill_id=item["skill_id"], params=params,
                              rationale=item["rationale"],
                              planned_hand=item.get("hand")))
    objects = [PlanObject(name=o["name"], kind=o["kind"], size_cm=_size_cm(o.get("size_cm")))
               for o in script.get("objects", [])]
    return CompiledPlan(summary=raw.get("summary", ""), combo_name=raw.get("combo_name", ""),
                        steps=steps, missing=missing, objects=objects,
                        goal=script.get("goal", ""),
                        end_holding=[n for n in script.get("end_holding") or []
                                     if n in {o.name for o in objects}])


def compile_plan(
    prompt: str,
    catalog: dict[str, dict[str, Any]],
    robot_model: str = "Spirit AI Moz1",
    structure: str = "dualarm",
    repairs: int = 2,
    trace: list[dict[str, Any]] | None = None,
) -> CompiledPlan:
    """Act the request out, bind it to the catalog, repair. Raises CompileError.

    `trace`, when given, receives one entry per repair round with the issues the
    simulator raised at its start (round 0 is the first binding) -- what the
    evaluation uses to measure how much each round of feedback fixes.
    """
    # Composed skills are sold whole; the compiler builds from atoms, otherwise a
    # request collapses into one opaque, unexecutable step.
    catalog = {k: v for k, v in catalog.items() if v.get("category") != "composite"}

    script = act_out(prompt, robot_model)

    names = _names(script)
    system = BIND_PROMPT.format(datasets=_datasets_block()) + _catalog_block(catalog)
    user = (f"Robot: {robot_model} (structure: {structure})\n"
            f"Customer request: {prompt.strip()}\n\n"
            f"Object names (a target is one of these, exactly, or \"\"): "
            f"{json.dumps(names)}\n\n"
            f"Motion script:\n{json.dumps(script, indent=1)}")
    schema = _bind_schema(sorted(catalog), sorted(cat.open_datasets()))
    try:
        raw = structured_call(system, user, schema, "skill_plan")
    except LLMError as exc:
        raise CompileError(str(exc)) from exc

    try:
        plan = _to_plan(raw, script)
    except Exception as exc:
        raise CompileError(f"compiler returned an unusable plan: {exc}") from exc

    # Belt and braces: the enum should make this impossible.
    unknown = [st.skill_id for st in plan.steps if st.skill_id not in catalog]
    if unknown:
        raise CompileError(f"compiler named skills outside the catalog: {unknown}")

    return _repair(plan, script, catalog, structure, system, user, schema, repairs, trace)


def _producers_hint(issue: Any, plan: CompiledPlan,
                    catalog: dict[str, dict[str, Any]]) -> str:
    """Name the skills that would establish an unmet precondition.

    "needs positioned" alone leaves a small model guessing; "move_to_station
    establishes positioned" turns the repair into a lookup.
    """
    if issue.kind != "unmet_precondition" or issue.step_index is None:
        return ""
    skill = catalog.get(plan.steps[issue.step_index].skill_id, {})
    rank = {"trained": 0, "beta": 1, "catalog": 2}
    hints = []
    for pred in skill.get("preconditions", []):
        if pred not in issue.detail:
            continue
        makers = sorted((s for s in catalog.values()
                         if pred in s.get("postconditions", [])
                         and s.get("category") != "composite"),
                        key=lambda s: (rank.get(s.get("status"), 2), s["id"]))
        if makers:
            hints.append(f"{pred} is established by "
                         f"{', '.join(m['id'] for m in makers[:4])}")
    return f" ({'; '.join(hints)})" if hints else ""


def _busy_hint(issue: Any, plan: CompiledPlan, catalog: dict[str, dict[str, Any]],
               structure: str) -> str:
    """Say what a hand is still holding when a step needs it empty.

    "needs hand_empty (on the left hand)" is true but not actionable; "the left
    hand still holds the bread bag from step 2" names the fix -- set it down
    first, or use the other hand.
    """
    from .validator import _gap_skill, assign_hands, gap_hands  # avoids a cycle

    if issue.kind != "unmet_precondition" or issue.step_index is None \
            or "hand_empty" not in issue.detail:
        return ""
    hands = assign_hands(plan.steps, catalog, gaps=plan.missing)
    ghands = gap_hands(plan.steps, catalog, {i: h for i, h in enumerate(hands) if h},
                       plan.missing)
    hand = hands[issue.step_index]
    events = []                             # (position, what, picks_up, lets_go)
    for i, st in enumerate(plan.steps[:issue.step_index]):
        if hands[i] != hand:
            continue
        sk = catalog.get(st.skill_id, {})
        events.append((i, f"'{st.params.get('target') or st.skill_id}' from step {i + 1}",
                       "holding" in sk.get("postconditions", []),
                       "holding" in sk.get("deletes", [])))
    for j, m in enumerate(plan.missing):
        if ghands[j] == hand and m.insert_after < issue.step_index:
            sk = _gap_skill(m)
            events.append((m.insert_after + 0.5, f"what gap {m.proposed_id} picked up",
                           "holding" in sk["postconditions"] and "holding" not in m.preconditions,
                           "holding" in sk["deletes"]))
    holding = None
    for _, what, picks_up, lets_go in sorted(events):
        if lets_go:
            holding = None
        elif picks_up:
            holding = what
    if not holding:
        return ""
    return (f" -- the {hand} hand still holds {holding}: set it down first "
            f"(move_to_station then release_object), or do this on the other hand")


def _duplicate_gaps(plan: CompiledPlan,
                    catalog: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    """Gaps that restate a catalog skill: same preconditions, same effects.

    The model sometimes renames an existing motion ("grasp_item") and lists it
    as missing. Comparing declared conditions catches that without knowing any
    skill by name.
    """
    out = []
    for m in plan.missing:
        pre, post = set(m.preconditions), set(m.postconditions)
        if not post:
            continue
        for sid in sorted(catalog):
            s = catalog[sid]
            if set(s.get("postconditions", [])) == post and \
                    set(s.get("preconditions", [])) == pre:
                out.append((m.proposed_id, sid))
                break
    return out


def _render(plan: CompiledPlan) -> str:
    """The plan as the model wrote it, gaps in place, for the repair prompt."""
    def gap(m: MissingSkill) -> str:
        return f"GAP:{m.proposed_id}@{m.hand}" if m.hand else f"GAP:{m.proposed_id}"

    parts = [gap(m) for m in plan.missing if m.insert_after < 0]
    for i, s in enumerate(plan.steps):
        t = s.params.get("target")
        at = f"@{s.planned_hand}" if s.planned_hand else ""
        parts.append(f"{s.skill_id}({t}){at}" if t else f"{s.skill_id}{at}")
        parts += [gap(m) for m in plan.missing if m.insert_after == i]
    return " -> ".join(parts)


def _repair(plan: CompiledPlan, script: dict[str, Any],
            catalog: dict[str, dict[str, Any]], structure: str,
            system: str, user: str, schema: dict[str, Any],
            budget: int, trace: list[dict[str, Any]] | None = None) -> CompiledPlan:
    """Hand the validator's complaints back to the binder and let it try again.

    A small model gets step ordering wrong often enough that one-shot output is
    rarely installable. It is much better at *fixing* a named error than at
    avoiding it, so the world model does the reasoning and the model does the
    editing. Only stage 2 is retried: the motion script is not in question.
    """
    from .validator import is_blocking, validate  # local import avoids a cycle

    rounds, extended = 0, False
    while rounds < max(budget, 0):
        rounds += 1
        issues = [i for i in validate(plan.steps, catalog, structure,
                                      kinds=plan.kinds(), gaps=plan.missing,
                                      keep=plan.end_holding)[0]
                  if is_blocking(i) or i.kind in ("loose_end", "pointless_move")]
        if trace is not None:
            trace.append({"round": rounds - 1,
                          "blocking": [i.kind for i in issues if is_blocking(i)],
                          "advisory": [i.kind for i in issues if not is_blocking(i)]})
        # A pour the wrong way round is cheap to fix and expensive to ship:
        # worth one extra round on its own.
        if any(i.kind == "wrong_flow" for i in issues) and rounds == budget \
                and not extended:
            budget += 1
            extended = True      # once: a model that keeps pouring backwards stops here
        wrongly_missing = [m.proposed_id for m in plan.missing if m.proposed_id in catalog]
        duplicates = _duplicate_gaps(plan, catalog)
        if not issues and not wrongly_missing and not duplicates:
            return plan
        # Gaps whose words match a trained skill's aliases. Advice only: it rides
        # along on a round the blocking issues already caused, and the binder
        # keeps the gap when the skill's acts_on or preconditions do not fit.
        # Demanding the swap drove plans into wrong-object grasps (a shovel
        # bound as a scoop), which blocked more than the gap ever did.
        seen = {g for g, _ in duplicates} | set(wrongly_missing)
        lookalikes = []
        for m in plan.missing:
            if m.proposed_id in seen:
                continue
            hit = cat.covering_skill(m.model_dump(), catalog)
            if hit and hit["trained"]:
                lookalikes.append((m.proposed_id, hit["id"]))

        lines = []
        for issue in issues:
            idx = issue.step_index
            if idx is not None and idx < len(plan.steps):
                where = f"step {idx + 1} ({plan.steps[idx].skill_id})"
            else:
                where = "the plan"
            lines.append(f"- {where}: {issue.detail}{_producers_hint(issue, plan, catalog)}"
                         f"{_busy_hint(issue, plan, catalog, structure)}")
        if wrongly_missing:
            lines.append("- these gaps are already IN the catalog -- use them as "
                         f"skills: {', '.join(wrongly_missing)}")
        for gap, sid in duplicates:
            lines.append(f"- gap {gap} declares exactly what catalog skill {sid} "
                         f"does (same preconditions and effects) -- use {sid}")
        for gap, sid in lookalikes:
            aka = ", ".join(catalog[sid].get("aliases", [])[:3])
            lines.append(f"- (advice) gap {gap} reads like trained skill {sid}"
                         f"{' (aka ' + aka + ')' if aka else ''}: use {sid} if its acts_on "
                         f"and preconditions fit this object, otherwise keep the gap")

        retry = (
            f"{user}\n\n"
            f"Your previous sequence was: {_render(plan)}\n"
            f"A simulator rejected it:\n" + "\n".join(lines) + "\n\n"
            "Return a corrected sequence for the same script. Fix exactly these "
            "problems: add the enabling steps that are missing, put a step on the "
            "other hand when the one it is on is busy or holds the wrong thing, swap "
            "a skill for one whose acts_on fits its target, and drop any step this "
            "robot's structure cannot run (it becomes a gap)."
        )
        try:
            # Repairs are where a small model struggles (a 25-step plan with one
            # hand still busy), so they may go to a stronger one: REPAIR_MODEL.
            raw = structured_call(system, retry, schema, "skill_plan",
                                  model=os.environ.get("REPAIR_MODEL", "").strip() or None)
            candidate = _to_plan(raw, script)
        except Exception:
            return plan  # keep the flawed plan; the UI will show why it is blocked
        if any(st.skill_id not in catalog for st in candidate.steps):
            return plan
        plan = candidate

    return plan
