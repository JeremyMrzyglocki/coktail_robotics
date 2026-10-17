#!/usr/bin/env python3
"""Terminal control for the skill store. Stdlib only, so it runs anywhere.

    python cli.py skills --filter pour
    python cli.py compile "mix me a smoothie"
    python cli.py install 3
    python cli.py run "wipe my table clean"      # compile + install + follow
    python cli.py gaps
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("SKILLSTORE_API", "http://127.0.0.1:8000")
TOKEN = os.environ.get("ROBOT_SHARED_SECRET", "")

BOLD, DIM, GREEN, RED, YELLOW, RESET = (
    "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[33m", "\033[0m")
if not sys.stdout.isatty():
    BOLD = DIM = GREEN = RED = YELLOW = RESET = ""


def call(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"content-type": "application/json"}
    if TOKEN:
        headers["authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except Exception:
            pass
        sys.exit(f"{RED}HTTP {exc.code}{RESET} {detail}")
    except urllib.error.URLError as exc:
        sys.exit(f"{RED}cannot reach {API}{RESET} ({exc.reason})\n"
                 f"start it with:  uvicorn app.api:app --port 8000")
    return json.loads(body) if body else {}


def pct(rate, n):
    if rate is None:
        return f"{DIM}no data{RESET}"
    p = round(rate * 100)
    col = GREEN if p >= 85 else YELLOW if p >= 60 else RED
    return f"{col}{p}%{RESET} {DIM}(n={n}){RESET}"


def cmd_skills(args) -> None:
    body = call("GET", f"/api/skills?robot_model={urllib.parse.quote(args.robot)}")
    rows = body["skills"]
    if args.filter:
        q = args.filter.lower()
        rows = [s for s in rows if q in (s["id"] + s["name"] + s["category"]
                                         + s["vendor"] + s["description"]).lower()]
    if args.status:
        rows = [s for s in rows if s["status"] == args.status]
    print(f"{BOLD}{len(rows)} skills{RESET} on {body['robot_model']}\n")
    for s in rows:
        mark = {"trained": f"{GREEN}*{RESET}", "beta": f"{YELLOW}~{RESET}"}.get(
            s["status"], f"{DIM}-{RESET}")
        print(f" {mark} {s['id']:<24} {('EUR %.2f' % s['price_eur']):>10}  "
              f"{pct(s['success_rate'], s['n_trials']):<22} {DIM}{s['vendor']}{RESET}")
    print(f"\n {GREEN}*{RESET} trained   {YELLOW}~{RESET} beta   {DIM}-{RESET} catalog only")


def print_plan(p: dict) -> None:
    print(f"\n{BOLD}{p['summary']}{RESET}")
    print(f"{DIM}plan {p['plan_id']} · {p['robot_model']} · "
          f"{p['executable_steps']}/{len(p['steps'])} executable"
          f"{' · cached' if p.get('cached') else ''}{RESET}\n")
    for i, s in enumerate(p["steps"], 1):
        flag = {"trained": GREEN + "*" + RESET, "beta": YELLOW + "~" + RESET}.get(
            s["status"], RED + "!" + RESET)
        params = " ".join(f"{k}={v}" for k, v in (s["params"] or {}).items())
        cost = "incl." if s.get("repeat_of") is not None else "EUR %.2f" % s["price_eur"]
        print(f" {i:>2}. {flag} {s['name']:<22} {cost:>10}  "
              f"{pct(s['success_rate'], s['n_trials']):<22} {DIM}{s['vendor']}{RESET}")
        if params:
            print(f"      {DIM}{params}{RESET}")
    print(f"\n     {BOLD}total  EUR {p['total_price_eur']:.2f}{RESET}")

    if p["missing"]:
        print(f"\n{YELLOW}Not in the catalog yet{RESET} "
              f"{DIM}(logged as demand){RESET}")
        for m in p["missing"]:
            print(f"  - {m['name']} {DIM}({m['proposed_id']}){RESET}: {m['description']}")
    if p["issues"]:
        print(f"\n{YELLOW}Validator{RESET}")
        for i in p["issues"]:
            where = "plan" if i["step_index"] is None else f"step {i['step_index'] + 1}"
            print(f"  [{i['kind']}] {where}: {i['detail']}")
    verdict = f"{GREEN}valid{RESET}" if p["valid"] else f"{RED}blocked{RESET}"
    print(f"\n status: {verdict}")


def cmd_compile(args) -> dict:
    p = call("POST", "/api/compile", {
        "prompt": args.prompt, "robot_model": args.robot,
        "structure": args.structure, "use_cache": not args.no_cache,
    })
    print_plan(p)
    return p


def cmd_install(args) -> None:
    r = call("POST", "/api/install", {"plan_id": args.plan_id})
    print(f"plan {r['plan_id']} -> {r['status']}")
    if args.follow:
        follow(args.plan_id)


def follow(plan_id: int) -> None:
    print(f"\n{DIM}following plan {plan_id} (ctrl-c to detach){RESET}")
    seen: set[str] = set()
    while True:
        s = call("GET", f"/api/plans/{plan_id}/status")
        for run in s["runs"]:
            key = f"{run['step_index']}:{run['created_at']}:{run['success']}"
            if key in seen:
                continue
            seen.add(key)
            tag = f"{GREEN}PASS{RESET}" if run["success"] else f"{RED}FAIL{RESET}"
            dur = f"{run['duration_s']:.1f}s" if run["duration_s"] is not None else "-"
            print(f"  {tag} step {run['step_index'] + 1:>2} "
                  f"{run['skill_id']:<22} {dur:>7}  {DIM}{run['notes'] or ''}{RESET}")
        if s["status"] in {"done", "failed"}:
            col = GREEN if s["status"] == "done" else RED
            print(f"\n plan {plan_id}: {col}{s['status']}{RESET}")
            return
        time.sleep(0.5)


def cmd_run(args) -> None:
    p = cmd_compile(args)
    if not p["valid"]:
        sys.exit(f"\n{RED}not installing: the validator blocked this plan{RESET}")
    call("POST", "/api/install", {"plan_id": p["plan_id"]})
    follow(p["plan_id"])


def cmd_gaps(args) -> None:
    g = call("GET", f"/api/gaps?limit={args.limit}")
    print(f"{BOLD}Unmet demand{RESET} {DIM}· {g['total_requests']} requests "
          f"· {g['distinct_gaps']} distinct gaps{RESET}\n")
    for x in g["gaps"]:
        print(f" {x['requests']:>3}x  {x['name']:<26} {DIM}{x['proposed_id']}{RESET}")
        print(f"       {DIM}{x['description']}{RESET}")
        for ex in x["example_prompts"]:
            print(f"       {DIM}“{ex}”{RESET}")


def main() -> None:
    ap = argparse.ArgumentParser(description="robot skill store CLI")
    ap.add_argument("--robot", default="Spirit AI Moz1")
    ap.add_argument("--structure", default="dualarm")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("skills"); s.set_defaults(fn=cmd_skills)
    s.add_argument("--filter"); s.add_argument("--status",
        choices=["trained", "beta", "catalog"])

    c = sub.add_parser("compile"); c.set_defaults(fn=cmd_compile)
    c.add_argument("prompt"); c.add_argument("--no-cache", action="store_true")

    i = sub.add_parser("install"); i.set_defaults(fn=cmd_install)
    i.add_argument("plan_id", type=int); i.add_argument("--follow", action="store_true")

    r = sub.add_parser("run"); r.set_defaults(fn=cmd_run)
    r.add_argument("prompt"); r.add_argument("--no-cache", action="store_true")

    g = sub.add_parser("gaps"); g.set_defaults(fn=cmd_gaps)
    g.add_argument("--limit", type=int, default=20)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
