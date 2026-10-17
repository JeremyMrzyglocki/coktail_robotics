#!/usr/bin/env python3
"""Measure what a skill actually does, under a protocol you can repeat.

A success rate is only a claim if the protocol is written down. This fixes the
trial count, the per-trial seed and the start configuration up front, records
every attempt including the failures, and reports Wilson intervals rather than a
bare percentage -- because 18/20 is not "90%", it is 90% [70%, 97%].

    python tools/run_eval.py --skills grasp_bottle,pour_into,stir --trials 20
    python tools/run_eval.py --all-trained --trials 20 --speed 20
    python tools/run_eval.py --skills wipe_surface --trials 20 --robot

Writes data/eval_<stamp>.json (raw) and reports/eval_<stamp>.md (the table you
put in the slide deck). Every attempt also lands in the runs table, so the
storefront's ratings move as the eval proceeds.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import catalog as cat  # noqa: E402
from app import db  # noqa: E402
from runner.executor import MockExecutor  # noqa: E402


def build_executor(args):
    if args.robot:
        from runner.moz1 import Moz1Executor  # noqa: PLC0415

        ex = Moz1Executor(structure=args.structure)
        ex.connect()
        return ex, f"Moz1Executor({args.structure})"
    return MockExecutor(seed=args.seed, speed=args.speed), f"MockExecutor(speed={args.speed})"


def eval_skill(ex, skill: dict, trials: int, robot_model: str, timeout_factor: float,
               seed0: int, verbose: bool) -> dict:
    """Run one skill `trials` times. Each trial is independent and homed first."""
    plan_id = db.execute(
        "INSERT INTO plans (prompt, robot_model, plan_json, valid, status) "
        "VALUES (?,?,?,?,?)",
        (f"eval: {skill['id']}", robot_model,
         json.dumps({"summary": f"evaluation of {skill['id']}", "steps": [], "missing": []}),
         1, "done"),
    )
    step = {
        "step_index": 0,
        "skill_id": skill["id"],
        "params": {},
        "hand": "left",
        "checkpoint": skill.get("checkpoint"),
        "prompt": skill.get("prompt"),
        "est_duration_s": skill.get("est_duration_s", 12.0),
    }
    timeout = float(step["est_duration_s"]) * timeout_factor

    attempts = []
    for t in range(trials):
        # Per-trial seed, so a rerun of trial 7 reproduces trial 7.
        if isinstance(ex, MockExecutor):
            ex.rng.seed(seed0 + t)
        ex.home()
        try:
            ex.load(step)
            outcome = ex.run(step, timeout)
            ok, dur, note = outcome.success, outcome.duration_s, outcome.notes
        except Exception as exc:  # noqa: BLE001
            ok, dur, note = False, 0.0, f"{type(exc).__name__}: {exc}"

        attempts.append({"trial": t, "seed": seed0 + t, "success": ok,
                         "duration_s": dur, "note": note})
        db.execute(
            "INSERT INTO runs (plan_id, step_index, skill_id, robot_model, success, "
            "duration_s, notes) VALUES (?,?,?,?,?,?,?)",
            (plan_id, 0, skill["id"], robot_model, int(ok), dur, note),
        )
        if verbose:
            print(f"    trial {t + 1:>3}/{trials}  "
                  f"{'PASS' if ok else 'FAIL'}  {dur:5.1f}s  {note[:48]}")

    ok_n = sum(1 for a in attempts if a["success"])
    lo, hi = cat.wilson(ok_n, trials)
    durations = [a["duration_s"] for a in attempts if a["success"]]
    return {
        "skill_id": skill["id"],
        "name": skill["name"],
        "status": skill.get("status"),
        "episodes": (skill.get("dataset") or {}).get("episodes", 0),
        "dataset": (skill.get("dataset") or {}).get("id"),
        "trials": trials,
        "successes": ok_n,
        "rate": ok_n / trials if trials else None,
        "ci_low": lo,
        "ci_high": hi,
        "mean_duration_s": round(sum(durations) / len(durations), 2) if durations else None,
        "plan_id": plan_id,
        "attempts": attempts,
    }


def write_report(result: dict, md_path: Path) -> None:
    p = result["protocol"]
    lines = [
        "# Skill evaluation",
        "",
        f"**{p['started']}** · {p['executor']} · robot `{p['robot_model']}` · "
        f"{p['trials']} trials per skill · base seed {p['seed']}",
        "",
        "## Protocol",
        "",
        f"- Every skill is run {p['trials']} times, independently, homed before each trial.",
        "- Trial *t* uses seed `base + t`, so any single trial can be reproduced.",
        "- Every attempt is recorded, failures included; nothing is retried or discarded.",
        "- Intervals are 95% Wilson score, which stays sensible at 0% and 100%.",
        "",
        "## Results",
        "",
        "| Skill | Status | Episodes | Trials | Success | 95% CI | Mean time |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for r in sorted(result["skills"], key=lambda x: -(x["rate"] or 0)):
        ci = f"{r['ci_low'] * 100:.0f}–{r['ci_high'] * 100:.0f}%"
        mean = f"{r['mean_duration_s']:.1f}s" if r["mean_duration_s"] else "—"
        lines.append(
            f"| {r['name']} | {r['status']} | {r['episodes']} | {r['trials']} | "
            f"**{r['rate'] * 100:.0f}%** ({r['successes']}/{r['trials']}) | {ci} | {mean} |"
        )

    total_t = sum(r["trials"] for r in result["skills"])
    total_ok = sum(r["successes"] for r in result["skills"])
    lo, hi = cat.wilson(total_ok, total_t)
    lines += [
        "",
        f"**Overall:** {total_ok}/{total_t} = {total_ok / total_t * 100:.1f}% "
        f"(95% CI {lo * 100:.0f}–{hi * 100:.0f}%)",
        "",
        "## Reading these numbers",
        "",
        f"- At {p['trials']} trials the interval is wide. For ±10pp around 90% you need "
        f"{cat.trials_needed(0.9, 0.10)} trials; for ±5pp, {cat.trials_needed(0.9, 0.05)}.",
        "- A skill is only as good as the interval's lower bound when you are deciding "
        "whether to ship it.",
    ]
    failures = [(r["name"], a["note"]) for r in result["skills"]
                for a in r["attempts"] if not a["success"]]
    if failures:
        lines += ["", "## Failure modes", ""]
        seen: dict[tuple[str, str], int] = {}
        for name, note in failures:
            seen[(name, note)] = seen.get((name, note), 0) + 1
        for (name, note), count in sorted(seen.items(), key=lambda kv: -kv[1])[:12]:
            lines.append(f"- {count}× **{name}** — {note}")
    md_path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    pick = ap.add_mutually_exclusive_group(required=True)
    pick.add_argument("--skills", help="comma-separated skill ids")
    pick.add_argument("--all-trained", action="store_true",
                      help="every skill with a trained checkpoint")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--robot-model", default="Spirit AI Moz1")
    ap.add_argument("--structure", default="dualarm")
    ap.add_argument("--robot", action="store_true", help="drive real hardware")
    ap.add_argument("--speed", type=float, default=20.0, help="mock only")
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--timeout-factor", type=float, default=2.5)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    db.init_db()
    catalog = cat.load_catalog()
    if args.all_trained:
        ids = [k for k, v in catalog.items() if v.get("checkpoint")]
    else:
        ids = [s.strip() for s in args.skills.split(",") if s.strip()]
    missing = [i for i in ids if i not in catalog]
    if missing:
        print(f"unknown skill(s): {missing}")
        return 1
    if not ids:
        print("nothing to evaluate")
        return 1

    ex, ex_name = build_executor(args)
    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    print(f"evaluating {len(ids)} skills x {args.trials} trials  [{ex_name}]")

    t0 = time.time()
    results = []
    try:
        for i, sid in enumerate(ids, 1):
            print(f"  [{i}/{len(ids)}] {sid}")
            results.append(eval_skill(ex, catalog[sid], args.trials, args.robot_model,
                                      args.timeout_factor, args.seed, not args.quiet))
    finally:
        ex.close()

    result = {
        "protocol": {
            "started": started,
            "finished": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "executor": ex_name,
            "robot_model": args.robot_model,
            "trials": args.trials,
            "seed": args.seed,
            "host": platform.node(),
            "wall_s": round(time.time() - t0, 1),
        },
        "skills": results,
    }

    stamp = started.replace(":", "").replace("-", "").replace("+0000", "")
    json_path = ROOT / "data" / f"eval_{stamp}.json"
    md_path = ROOT / "reports" / f"eval_{stamp}.md"
    json_path.write_text(json.dumps(result, indent=2) + "\n")
    write_report(result, md_path)

    print(f"\n{'skill':<24}{'trials':>7}{'rate':>8}   95% CI")
    for r in sorted(results, key=lambda x: -(x["rate"] or 0)):
        print(f"  {r['name']:<22}{r['trials']:>7}{r['rate'] * 100:>7.0f}%   "
              f"[{r['ci_low'] * 100:.0f}%, {r['ci_high'] * 100:.0f}%]")
    print(f"\nraw    -> {json_path.relative_to(ROOT)}")
    print(f"report -> {md_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
