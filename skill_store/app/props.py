"""Stand-in 3D props for objects the animation has no model for.

The scene kit draws bottles, glasses, fruit and a few others from hand-written
builders; anything else used to be a grey cube. Now an unknown name ("plant",
"flower pot", "paint brush") is designed once by the model as a list of
primitives -- boxes, cylinders, spheres, cones, tori -- and cached. The browser
assembles the primitives; no generated code runs anywhere. One call per new
object, a few hundred tokens, then free forever.

The designer supplies shape only. How big a thing is comes from the plan: the
compiler's act-out stage sizes every object with the whole request in view (a
toy car's wheel is toy-sized), `fit_sizes` makes sure nothing the plan puts onto
or into another thing is bigger than it, and `specs_for` scales the design so its
largest dimension is that size. Designs are cached by base name ("wheel1" and
"wheel2" are both "wheel") and a size bucket, so a toy wheel and a car wheel are
designed separately but four toy wheels once.
"""
from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import db
from .llm import LLMError, structured_call
from .models import CompiledPlan

SHAPES = ["box", "cylinder", "sphere", "cone", "torus"]
MAX_PARTS = 10
MIN_SIZE, MAX_SIZE = 0.004, 0.45     # metres; nothing smaller than a bead or bigger than a chair seat
KNEE = 0.3                           # metres; above this, sizes are compressed into MAX_SIZE
BUCKET = 1.5                         # designs are shared between sizes within this ratio
FIT = 0.8                            # a thing set onto or into another is at most this much of its size

PROMPT = """\
You design a simple grey stand-in 3D model of an everyday object for a robot \
demo, out of geometric primitives. Metres, y up, the object standing on the \
counter at y=0 with its base centred on the origin. Real-world size: a flower \
pot is ~0.12 m tall, a paint brush ~0.2 m long lying flat, a plant ~0.25 m; when \
a size is given, design at that size. The model is rescaled afterwards so its \
largest dimension matches, so get the proportions between parts right. At \
most {max_parts} parts; aim for 3-6. Each part: shape, size (box: width, height, \
depth; cylinder: radius_top, radius_bottom, height; sphere: radius; cone: radius, \
height; torus: ring_radius, tube_radius), pos (centre), rot (euler radians), \
shade 0.15-0.9 (grey; darker for soil, metal; lighter for ceramic, paper). A \
hollow look comes from a lid-less cylinder plus a darker inner disc, not from \
booleans. No text, no colour, no fine detail.

Also say how a hand takes it: hold.mode "top" (fingers down over it: a plant, \
a small box), "side" (from the side at height hold.y: a pot, a bottle, a tool \
handle) or "flat" (sliding under: a cloth, paper), and hold.y in metres. \
`fixed` is true for things that stay where they are (a sink, a wall shelf, a \
large plant on the floor). `height_m` is the overall height.

Worked example, "coffee mug": parts = cylinder r 0.04/0.04 h 0.09 at y 0.045 \
shade 0.8; cylinder r 0.034/0.034 h 0.004 at y 0.088 shade 0.35 (the dark \
inside); torus ring 0.028 tube 0.006 at x 0.05 y 0.05 rot x 0 shade 0.8 (the \
handle). hold: side, y 0.045. fixed false. height_m 0.09.
"""


def _schema() -> dict[str, Any]:
    part = {
        "type": "object",
        "properties": {
            "shape": {"type": "string", "enum": SHAPES},
            "size": {"type": "array", "items": {"type": "number"}},
            "pos": {"type": "array", "items": {"type": "number"}},
            "rot": {"type": "array", "items": {"type": "number"}},
            "shade": {"type": "number"},
        },
        "required": ["shape", "size", "pos", "rot", "shade"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "parts": {"type": "array", "items": part},
            "hold": {
                "type": "object",
                "properties": {"mode": {"type": "string", "enum": ["top", "side", "flat"]},
                               "y": {"type": "number"}},
                "required": ["mode", "y"], "additionalProperties": False,
            },
            "fixed": {"type": "boolean"},
            "height_m": {"type": "number"},
        },
        "required": ["parts", "hold", "fixed", "height_m"],
        "additionalProperties": False,
    }


def _clamp(v: float, lo: float, hi: float) -> float:
    try:
        return float(min(max(float(v), lo), hi))
    except (TypeError, ValueError):
        return lo


def _sanitise(raw: dict[str, Any]) -> dict[str, Any]:
    """Bound every number so a wild answer cannot fill the screen or vanish."""
    need = {"box": 3, "cylinder": 3, "sphere": 1, "cone": 2, "torus": 2}
    parts = []
    for p in (raw.get("parts") or [])[:MAX_PARTS]:
        shape = p.get("shape") if p.get("shape") in SHAPES else "box"
        size = [_clamp(x, MIN_SIZE, MAX_SIZE) for x in (p.get("size") or [])][:3]
        while len(size) < need[shape]:
            size.append(0.03)
        pos = [_clamp(x, -0.5, 0.6) for x in (p.get("pos") or [0, 0, 0])[:3]]
        while len(pos) < 3:
            pos.append(0.0)
        rot = [_clamp(x, -6.3, 6.3) for x in (p.get("rot") or [0, 0, 0])[:3]]
        while len(rot) < 3:
            rot.append(0.0)
        parts.append({"shape": shape, "size": size, "pos": pos, "rot": rot,
                      "shade": _clamp(p.get("shade", 0.6), 0.1, 0.95)})
    if not parts:
        parts = [{"shape": "box", "size": [0.05, 0.05, 0.05], "pos": [0, 0.025, 0],
                  "rot": [0, 0, 0], "shade": 0.6}]
    hold = raw.get("hold") or {}
    height = _clamp(raw.get("height_m", 0.05), MIN_SIZE, MAX_SIZE)
    return {
        "parts": parts,
        "hold": {"mode": hold.get("mode") if hold.get("mode") in ("top", "side", "flat") else "side",
                 "y": _clamp(hold.get("y", height / 2), 0.0, MAX_SIZE)},
        "fixed": bool(raw.get("fixed", False)),
        "height_m": height,
    }


# ---------------------------------------------------------------- sizes

def base_name(name: str) -> str:
    """'Wheel3' -> 'wheel', 'box 2' -> 'box': numbered copies share one design."""
    n = " ".join(str(name or "").lower().split())
    return re.sub(r"[\s_#-]*\d+$", "", n) or n


def _bucket(size_cm: float) -> int:
    return round(math.log(max(size_cm, 0.1)) / math.log(BUCKET))


def _cache_key(base: str, size_cm: float | None) -> str:
    return base if not size_cm else f"{base}|{_bucket(size_cm)}"


def display_m(size_cm: float) -> float:
    """The size drawn, in metres. True to scale up to KNEE; bigger things are
    compressed towards MAX_SIZE, so a car still shows bigger than its wheel."""
    m = max(size_cm / 100.0, 2 * MIN_SIZE)
    if m <= KNEE:
        return m
    return KNEE + (MAX_SIZE - KNEE) * (1 - math.exp(-(m - KNEE) / 0.6))


def _rotate(v: tuple[float, float, float], rot: list[float]) -> tuple[float, float, float]:
    """Euler XYZ, as three.js applies it (R = Rx * Ry * Rz)."""
    x, y, z = v
    c, s = math.cos(rot[2]), math.sin(rot[2])
    x, y = x * c - y * s, x * s + y * c                          # about z first
    c, s = math.cos(rot[1]), math.sin(rot[1])
    x, z = x * c + z * s, -x * s + z * c                         # then y
    c, s = math.cos(rot[0]), math.sin(rot[0])
    y, z = y * c - z * s, y * s + z * c                          # then x
    return x, y, z


def _half_extents(part: dict[str, Any]) -> tuple[float, float, float]:
    s = part["size"]
    if part["shape"] == "cylinder":
        r = max(s[0], s[1])
        return r, s[2] / 2, r
    if part["shape"] == "sphere":
        return s[0], s[0], s[0]
    if part["shape"] == "cone":
        return s[0], s[1] / 2, s[0]
    if part["shape"] == "torus":                                  # lies in the xy plane
        return s[0] + s[1], s[0] + s[1], s[1]
    return s[0] / 2, s[1] / 2, s[2] / 2


def bounds(spec: dict[str, Any]) -> tuple[list[float], list[float]]:
    """Axis-aligned bounding box of the assembled parts: (min xyz, max xyz)."""
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for p in spec["parts"]:
        hx, hy, hz = _half_extents(p)
        for corner in ((a, b, c) for a in (-hx, hx) for b in (-hy, hy) for c in (-hz, hz)):
            r = _rotate(corner, p["rot"])
            for i in range(3):
                lo[i] = min(lo[i], r[i] + p["pos"][i])
                hi[i] = max(hi[i], r[i] + p["pos"][i])
    return lo, hi


def largest_dimension(spec: dict[str, Any]) -> float:
    lo, hi = bounds(spec)
    return max(h - l for l, h in zip(lo, hi))


def scaled(spec: dict[str, Any], size_cm: float) -> dict[str, Any]:
    """The same design, uniformly scaled so its largest dimension is size_cm
    (as drawn; see display_m). Sizes, positions and the grip height scale
    together, so proportions hold; _sanitise still bounds the result."""
    k = display_m(size_cm) / max(largest_dimension(spec), 1e-6)
    parts = [{**p, "size": [x * k for x in p["size"]],
              "pos": [x * k for x in p["pos"]]} for p in spec["parts"]]
    out = _sanitise({**spec, "parts": parts,
                     "hold": {**spec["hold"], "y": spec["hold"]["y"] * k},
                     "height_m": spec["height_m"] * k})
    top = bounds(out)[1][1]
    if top > 0:
        out["height_m"] = _clamp(top, MIN_SIZE, MAX_SIZE)
    return out


def placements(plan: CompiledPlan, catalog: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    """(thing, destination) for everything the plan puts onto or into another.

    Read from declared data only. A hand holds X after a step whose skill
    leaves it `holding`; a step that leaves it `positioned` carries X to that
    step's target D. X is then on or in D when that hand lets go there (a step
    or gap that leaves the hand empty) or when a gap fastens it there (attach,
    insert, press ...). A pour is a carry with no let-go, so the bottle over
    the glass is never paired with it.
    """
    gaps_after: dict[int, list[Any]] = {}
    for m in plan.missing:
        gaps_after.setdefault(m.insert_after, []).append(m)
    seq: list[tuple[str, Any, str]] = [("gap", m, m.hand or "") for m in gaps_after.get(-1, [])]
    for i, st in enumerate(plan.steps):
        hand = st.hand or st.planned_hand or ""
        seq.append(("step", st, hand))
        seq += [("gap", m, m.hand or hand) for m in gaps_after.get(i, [])]

    held: dict[str, str] = {}
    at: dict[str, str] = {}
    out: list[tuple[str, str]] = []
    for what, x, hand in seq:
        if what == "step":
            sk = catalog.get(x.skill_id, {})
            pre, post = set(sk.get("preconditions") or []), set(sk.get("postconditions") or [])
            target = (x.params or {}).get("target", "")
        else:
            pre, post, target = set(x.preconditions), set(x.postconditions), ""
        thing = held.get(hand)
        if what == "step" and "holding" in post and "holding" not in pre and target:
            held[hand], at[hand] = target, ""
            continue
        if not thing:
            continue
        if what == "step" and "positioned" in post and target and target != thing:
            at[hand] = target
            continue
        dest = at.get(hand) or (target if target and target != thing else "")
        fastens = what == "gap" and bool(FASTEN.search(f"{x.proposed_id} {x.name}".lower()))
        if dest and ("hand_empty" in post or fastens):
            out.append((thing, dest))
        if "hand_empty" in post:
            held.pop(hand, None)
            at.pop(hand, None)
    return out


# Gap names that leave the held thing joined to where it was carried.
FASTEN = re.compile(r"(^|[\s_])(attach|insert|mount|fit|plug|press|place|put|set|stack|"
                    r"load|join|connect|snap|screw|slot|push|nest|assemble|hang)(e?s|e?d|ing)?(?![a-z])")


def fit_sizes(plan: CompiledPlan, catalog: dict[str, dict[str, Any]]) -> dict[str, float | None]:
    """Each object's size in cm, with every thing the plan puts onto or into
    another made smaller than its destination (at most FIT of it). Copies of
    one thing (box2 onto box1) may match: that is a stack. Chains settle,
    since a size only ever shrinks."""
    sizes = {o.name: o.size_cm for o in plan.objects}
    pairs = placements(plan, catalog)
    for _ in range(len(pairs) + 1):
        changed = False
        for thing, dest in pairs:
            a, b = sizes.get(thing), sizes.get(dest)
            if not a or not b or base_name(thing) == base_name(dest):
                continue
            if a > FIT * b:
                sizes[thing] = round(FIT * b, 2)
                changed = True
        if not changed:
            break
    return sizes


# ---------------------------------------------------------------- designs

def design(name: str, size_cm: float | None = None) -> dict[str, Any]:
    """Ask the model for one object's shape. Raises LLMError."""
    what = f"Object: {name}"
    if size_cm:
        what += f", about {size_cm:.3g} cm at its largest"
    raw = structured_call(PROMPT.format(max_parts=MAX_PARTS), what, _schema(), "prop_design")
    return _sanitise(raw)


def specs_for(names: list[str], sizes: dict[str, float | None] | None = None
              ) -> dict[str, dict[str, Any] | None]:
    """Specs for these names, keyed by the lower-cased name, designing the
    missing ones in parallel. `sizes` gives a name's largest dimension in cm;
    a sized spec is scaled to it, an unsized one keeps the designer's size.

    None for a name the model could not design right now; the browser then
    falls back to its grey cube and tries again on the next compile.
    """
    sizes = {k.strip().lower(): v for k, v in (sizes or {}).items()}
    wanted: dict[str, tuple[str, str, float | None]] = {}     # name -> (key, base, cm)
    for n in names:
        name = n.strip().lower()
        if name and name not in wanted:
            cm = sizes.get(name) or None
            base = base_name(name)
            wanted[name] = (_cache_key(base, cm), base, cm)
    out: dict[str, dict[str, Any] | None] = {}
    if not wanted:
        return out
    keys = sorted({k for k, _, _ in wanted.values()})
    marks = ",".join("?" * len(keys))
    designs: dict[str, dict[str, Any] | None] = {
        r["name"]: json.loads(r["spec_json"])
        for r in db.query(f"SELECT name, spec_json FROM props WHERE name IN ({marks})", keys)}
    # One call per key, at the size its bucket stands for.
    todo = {k: (b, BUCKET ** _bucket(cm) if cm else None)
            for k, b, cm in wanted.values() if k not in designs}

    def one(key: str) -> tuple[str, dict[str, Any] | None]:
        base, cm = todo[key]
        try:
            return key, design(base, cm)
        except LLMError:
            return key, None

    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, spec in pool.map(one, list(todo)):
            designs[key] = spec
            if spec is not None:
                db.execute("INSERT OR REPLACE INTO props (name, spec_json) VALUES (?, ?)",
                           (key, json.dumps(spec)))
    for name, (key, _, cm) in wanted.items():
        spec = designs.get(key)
        out[name] = scaled(spec, cm) if spec and cm else spec
    return out
