#!/usr/bin/env python3
"""Measure the compiler on requests it was not written for.

The robot eval (run_eval.py) asks "does this skill work?". This asks "does the
compiler turn an unfamiliar request into a plan a robot could follow?" -- the
question that matters every time a customer types something new. Each request is
compiled fresh (no cache; no plans or demand are logged -- only the skills
table is re-seeded from the catalog files, as the server does at start) and
scored by the same simulator the storefront uses:

  valid        no blocking issue: every precondition met, every grasp fits its
               object's kind, nothing this robot's structure cannot run
  hands empty  the plan does not end with a hand still holding something
  gaps         what the catalog could not do, and the open dataset proposed for
               each -- listed for a person to judge whether they are atomic

    python tools/compile_eval.py                  # every prompt once
    python tools/compile_eval.py --runs 3         # repeat, for a rate
    python tools/compile_eval.py --only novel

Writes data/compile_eval_<stamp>.json and reports/compile_eval_<stamp>.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import catalog as cat  # noqa: E402
from app import db  # noqa: E402
from app.compiler import CompileError, compile_plan  # noqa: E402
from app.validator import is_blocking, validate  # noqa: E402

# Requests nothing in the prompts or the catalog was tuned for. Add to this list
# whenever a customer request goes wrong, so the fix is measured, not assumed.
NOVEL = [
    "You have a paint bucket and brush. draw an image on the table",
    "build a small sandcastle on the tray with the bucket and shovel",
    "do a simple card trick with the deck on the table",
    "water the two plants on the shelf",
    "write my name on the whiteboard with the marker",
    "make me a jam sandwich",
    "put the flowers in the vase and add water",
    "feed the cat: open the tin and put the food in her bowl",
]
DEMO = [
    "make me a pina colada",
    "pour me a glass of juice",
    "mix me a smoothie",
    "wipe my table clean after dinner",
    "clear the table and put the bottles away",
]


def score(prompt: str, catalog: dict, structure: str) -> dict:
    t0 = time.monotonic()
    trace: list[dict] = []
    try:
        plan = compile_plan(prompt, catalog, structure=structure, trace=trace)
    except CompileError as exc:
        return {"prompt": prompt, "error": str(exc), "seconds": time.monotonic() - t0}
    seconds = time.monotonic() - t0
    issues, _ = validate(plan.steps, catalog, structure,
                         kinds=plan.kinds(), gaps=plan.missing)
    return {
        "prompt": prompt,
        "seconds": round(seconds, 1),
        "valid": not any(is_blocking(i) for i in issues),
        "hands_empty": not any(i.kind == "loose_end" for i in issues),
        "wrong_object": [i.detail for i in issues if i.kind == "wrong_object"],
        "blocking": [f"{i.kind}: {i.detail}" for i in issues if is_blocking(i)],
        "steps": [s.skill_id + (f"({s.params['target']})" if s.params.get("target") else "")
                  for s in plan.steps],
        "gaps": [{"id": m.proposed_id, "after": m.insert_after,
                  "dataset": m.dataset_id or None, "description": m.description}
                 for m in plan.missing],
        "objects": {o.name: o.kind for o in plan.objects},
        "goal": plan.goal,
        # Issues at the start of each repair round (round 0 = first binding),
        # then the final plan's: the per-round validity curve comes from here.
        "trace": trace + [{"round": "final",
                           "blocking": [i.kind for i in issues if is_blocking(i)],
                           "advisory": [i.kind for i in issues if i.kind in
                                        ("loose_end", "pointless_move")]}],
        "set": "novel" if prompt in NOVEL else "demo",
    }


def config() -> dict:
    """Which models produced these numbers -- recorded with every run."""
    from app.llm import active_provider, default_model
    provider = active_provider()
    base = default_model(provider)
    return {"provider": provider, "bind_model": base,
            "act_model": os.environ.get("COMPILER_ACT_MODEL", "").strip() or base,
            "repair_model": os.environ.get("REPAIR_MODEL", "").strip() or base,
            "effort": os.environ.get("COMPILER_EFFORT", "medium") if provider == "anthropic"
            else None}


def rate(rows: list[dict], key: str) -> str:
    ok = sum(1 for r in rows if r.get(key))
    lo, hi = cat.wilson(ok, len(rows))
    return f"{ok}/{len(rows)} ({ok / len(rows):.0%}, 95% CI {lo:.0%}–{hi:.0%})"


def report(rows: list[dict], args) -> str:
    done = [r for r in rows if "error" not in r]
    out = [f"# Compile eval — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", "",
           f"{len(rows)} compiles ({args.runs} run(s) per prompt, set: {args.only}), "
           f"{len(rows) - len(done)} failed outright.", ""]
    if done:
        out += [f"- **valid:** {rate(done, 'valid')}",
                f"- **hands empty at the end:** {rate(done, 'hands_empty')}",
                f"- **grasp on the wrong kind of object:** "
                f"{sum(1 for r in done if r['wrong_object'])}",
                f"- **gaps with a candidate open dataset:** "
                f"{sum(1 for r in done for g in r['gaps'] if g['dataset'])}"
                f"/{sum(len(r['gaps']) for r in done)}",
                f"- **median seconds:** {sorted(r['seconds'] for r in done)[len(done) // 2]}",
                ""]
    for r in rows:
        out.append(f"## {r['prompt']}")
        if "error" in r:
            out += [f"FAILED: {r['error']}", ""]
            continue
        flags = ["valid" if r["valid"] else "**BLOCKED**",
                 "hands empty" if r["hands_empty"] else "**ends holding**",
                 f"{r['seconds']}s"]
        out.append(" · ".join(flags))
        out.append("")
        out.append("Steps: " + " → ".join(r["steps"]))
        for g in r["gaps"]:
            out.append(f"- gap after step {g['after'] + 1}: `{g['id']}` — {g['description']}"
                       f" (data: {g['dataset'] or 'none'})")
        for b in r["blocking"]:
            out.append(f"- ✗ {b}")
        out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", choices=["all", "novel", "demo"], default="all")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--structure", default="dualarm")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--tag", default="", help="label for this run, kept in the file name")
    args = ap.parse_args()

    db.init_db()
    db.seed_skills()
    catalog = cat.load_catalog()
    prompts = {"all": NOVEL + DEMO, "novel": NOVEL, "demo": DEMO}[args.only]
    jobs = [p for p in prompts for _ in range(args.runs)]
    with ThreadPoolExecutor(args.workers) as ex:
        rows = list(ex.map(lambda p: score(p, catalog, args.structure), jobs))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    name = f"compile_eval_{stamp}" + (f"_{args.tag}" if args.tag else "")
    raw = ROOT / "data" / f"{name}.json"
    md = ROOT / "reports" / f"{name}.md"
    raw.write_text(json.dumps({"config": config(), "runs": args.runs, "rows": rows},
                              indent=2) + "\n")
    md.write_text(report(rows, args) + "\n")
    print(report(rows, args).split("\n## ")[0])
    print(f"-> {md.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
