"""FastAPI service. Runs entirely on one laptop; the robot runner polls it.

    uvicorn app.api:app --reload --port 8000
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import catalog as cat
from . import db
from .compiler import CompileError, cache_key, compile_plan
from .models import CompiledPlan, PlanResponse, RunReport, Step
from .validator import (assign_hands, balance_hands, dependency_graph,
                        hand_episodes, is_blocking, validate)

ROOT = Path(__file__).resolve().parent
DEFAULT_ROBOT = "Spirit AI Moz1"


def _clips() -> dict[str, Any]:
    """Dataset preview clips written by tools/fetch_clips.py, keyed by dataset id."""
    path = ROOT.parent / "data" / "clip_sources.json"
    return json.loads(path.read_text()) if path.exists() else {}
INITIAL_LIKE = {"hand_empty", "coaster_ready", "glass_placed"}

app = FastAPI(title="Robot Skill Store", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    # Always reload the seed, so editing tools/make_catalog.py and restarting is
    # enough. Composed skills are kept.
    n = db.seed_skills()
    print(f"seeded {n} skills")


# --------------------------------------------------------------------------
# auth for the robot-facing endpoints
# --------------------------------------------------------------------------
def robot_auth(authorization: str = Header(default="")) -> None:
    """The job queue dispatches physical arm motions. It does not go unauthenticated."""
    secret = os.environ.get("ROBOT_SHARED_SECRET", "")
    if not secret:
        raise HTTPException(500, "ROBOT_SHARED_SECRET is not set on the server")
    if authorization != f"Bearer {secret}":
        raise HTTPException(401, "bad or missing robot token")


# --------------------------------------------------------------------------
# storefront
# --------------------------------------------------------------------------
@app.get("/api/skills")
def list_skills(robot_model: str = DEFAULT_ROBOT) -> dict[str, Any]:
    catalog = cat.load_catalog()
    rates = cat.success_rates(robot_model)
    per_robot = cat.rates_by_robot()
    skills = []
    for sid in sorted(catalog):
        s = dict(catalog[sid])
        rate, n = rates.get(sid, (None, 0))
        s["success_rate"] = round(rate, 3) if rate is not None else None
        s["n_trials"] = n
        s["by_robot"] = per_robot.get(sid, [])
        avail, ds = cat.availability(s)
        s["availability"] = avail
        s["dataset_name"] = (ds or {}).get("name", "")
        skills.append(s)
    return {"robot_model": robot_model, "count": len(skills), "skills": skills}


@app.get("/api/skills/{skill_id}")
def skill_detail(skill_id: str, robot_model: str = DEFAULT_ROBOT) -> dict[str, Any]:
    """Everything known about one skill -- what the detail popup shows."""
    catalog = cat.load_catalog()
    skill = catalog.get(skill_id)
    if not skill:
        raise HTTPException(404, "no such skill")
    avail, ds = cat.availability(skill)
    credits_path = ROOT.parent / "data" / "thumb_sources.json"
    credits = json.loads(credits_path.read_text()) if credits_path.exists() else {}
    rate, n = cat.success_rates(robot_model).get(skill_id, (None, 0))

    used_by = db.query(
        """SELECT COUNT(DISTINCT plan_id) AS plans, COUNT(*) AS runs
           FROM runs WHERE skill_id = ?""", (skill_id,))
    return {
        **skill,
        "availability": avail,
        "dataset": {**(skill.get("dataset") or {}), "detail": ds},
        "success_rate": round(rate, 3) if rate is not None else None,
        "n_trials": n,
        "by_robot": cat.rates_by_robot().get(skill_id, []),
        "thumb_credit": credits.get(skill_id),
        # Footage of the data this skill trains on (or would) -- never of the
        # skill itself, and the popup says so.
        "clip": _clips().get((skill.get("dataset") or {}).get("id") or ""),
        "usage": dict(used_by[0]) if used_by else {"plans": 0, "runs": 0},
    }


class CompileRequest(BaseModel):
    prompt: str
    robot_model: str = DEFAULT_ROBOT
    structure: str = "dualarm"
    use_cache: bool = True


def _schedule(steps, catalog, structure, overrides=None, plan=None):
    """Hands, validation and the dependency graph, which all depend on each other.

    `plan` supplies the compiler's object kinds and gaps, when there is one.
    """
    hands = assign_hands(steps, catalog, overrides or {},
                         gaps=plan.missing if plan else None)
    for step, hand in zip(steps, hands):
        step.hand = hand
    issues, _ = validate(steps, catalog, structure, hands,
                         kinds=plan.kinds() if plan else None,
                         gaps=plan.missing if plan else None)
    graph = dependency_graph(steps, catalog, hands)
    width: dict[int, int] = {}
    for node in graph:
        width[node["layer"]] = width.get(node["layer"], 0) + 1
    return hands, issues, graph, (max(width) + 1 if width else 0), (max(width.values()) if width else 1)


def _assemble(plan: CompiledPlan, prompt: str, robot_model: str, structure: str,
              plan_id: int, cached: bool) -> PlanResponse:
    catalog = cat.load_catalog()
    hands, issues, graph, depth, par = _schedule(plan.steps, catalog, structure, plan=plan)
    rates = cat.success_rates(robot_model)
    priced = cat.price_steps(plan.steps, catalog, rates)
    return PlanResponse(
        hands=hands, depth=depth, max_parallel=par,
        graph=graph,
        combo_name=plan.combo_name,
        plan_id=plan_id,
        prompt=prompt,
        robot_model=robot_model,
        summary=plan.summary,
        steps=priced,
        missing=plan.missing,
        issues=issues,
        valid=not any(is_blocking(i) for i in issues),
        total_price_eur=round(sum(p.price_eur for p in priced), 2),
        executable_steps=sum(1 for p in priced if p.executable),
        cached=cached,
    )


@app.post("/api/compile", response_model=PlanResponse)
def compile_endpoint(req: CompileRequest) -> PlanResponse:
    catalog = cat.load_catalog()
    if not catalog:
        raise HTTPException(500, "catalog is empty -- run tools/make_catalog.py and restart")

    key = cache_key(req.prompt, req.robot_model, list(catalog))
    cached = False
    plan: CompiledPlan | None = None

    if req.use_cache:
        row = db.query("SELECT plan_json FROM compile_cache WHERE cache_key = ?", (key,))
        if row:
            plan = CompiledPlan.model_validate_json(row[0]["plan_json"])
            cached = True

    if plan is None:
        try:
            plan = compile_plan(req.prompt, catalog, req.robot_model, req.structure)
        except CompileError as exc:
            raise HTTPException(502, str(exc)) from exc
        db.execute(
            "INSERT OR REPLACE INTO compile_cache (cache_key, plan_json) VALUES (?,?)",
            (key, plan.model_dump_json()),
        )

    issues, _ = validate(plan.steps, catalog, req.structure,
                         kinds=plan.kinds(), gaps=plan.missing)
    valid = not any(is_blocking(i) for i in issues)
    plan_id = db.execute(
        "INSERT INTO plans (prompt, robot_model, plan_json, valid) VALUES (?,?,?,?)",
        (req.prompt, req.robot_model, plan.model_dump_json(), int(valid)),
    )
    cat.record_demand(req.prompt, req.robot_model, plan_id, plan.missing)
    return _assemble(plan, req.prompt, req.robot_model, req.structure, plan_id, cached)


@app.get("/api/plans/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: int, structure: str = "dualarm") -> PlanResponse:
    rows = db.query("SELECT * FROM plans WHERE id = ?", (plan_id,))
    if not rows:
        raise HTTPException(404, "no such plan")
    row = rows[0]
    plan = CompiledPlan.model_validate_json(row["plan_json"])
    resp = _assemble(plan, row["prompt"], row["robot_model"], structure, plan_id, True)
    return resp


@app.get("/api/plans/{plan_id}/status")
def plan_status(plan_id: int) -> dict[str, Any]:
    """Polled by the live run panel. Cheap on purpose -- no SSE to break on stage."""
    rows = db.query("SELECT status FROM plans WHERE id = ?", (plan_id,))
    if not rows:
        raise HTTPException(404, "no such plan")
    runs = db.query(
        """SELECT step_index, skill_id, success, duration_s, notes, created_at
           FROM runs WHERE plan_id = ? ORDER BY step_index, id""",
        (plan_id,),
    )
    return {
        "plan_id": plan_id,
        "status": rows[0]["status"],
        "runs": [dict(r) for r in runs],
    }


@app.post("/api/install")
def install(payload: dict[str, Any]) -> dict[str, Any]:
    """Queue a plan for the robot. The install button.

    Refuses an invalid plan -- the validator, not the model, decides what runs.
    """
    plan_id = int(payload.get("plan_id", 0))
    rows = db.query("SELECT * FROM plans WHERE id = ?", (plan_id,))
    if not rows:
        raise HTTPException(404, "no such plan")
    if not rows[0]["valid"]:
        raise HTTPException(409, "plan failed validation and will not be queued")
    db.execute("UPDATE plans SET status = 'queued' WHERE id = ?", (plan_id,))
    return {"plan_id": plan_id, "status": "queued"}


class ValidateRequest(BaseModel):
    steps: list[dict[str, Any]]
    robot_model: str = DEFAULT_ROBOT
    structure: str = "dualarm"
    plan_id: int | None = None
    hand_overrides: dict[int, str] = {}
    changed_step: int | None = None


@app.post("/api/validate")
def validate_endpoint(req: ValidateRequest) -> dict[str, Any]:
    """Re-check an order the user dragged into place. No model call, so it is instant.

    This is what makes drag-and-drop meaningful: move a step somewhere impossible
    and the world model says so immediately.
    """
    catalog = cat.load_catalog()
    steps = [Step(skill_id=s["skill_id"], params=s.get("params") or {},
                  rationale=s.get("rationale", ""),
                  planned_hand=s.get("planned_hand")) for s in req.steps]

    overrides = dict(req.hand_overrides)
    stored = None
    if req.plan_id:
        rows = db.query("SELECT plan_json FROM plans WHERE id = ?", (req.plan_id,))
        if rows:
            stored = CompiledPlan.model_validate_json(rows[0]["plan_json"])
    hands, issues, graph, depth, par = _schedule(steps, catalog, req.structure,
                                                 overrides, stored)

    # Switching one step switches its whole hand episode; say which steps went
    # with it. (Comparing against "the override removed" was wrong whenever an
    # earlier auto-balance had put that episode on the other hand.)
    moved: list[int] = []
    if req.changed_step is not None:
        for ep in hand_episodes(steps, catalog, stored.missing if stored else None):
            if req.changed_step in ep:
                moved = [i for i in ep if i != req.changed_step]
    warning = ""
    if moved and req.changed_step is not None:
        names = [catalog.get(steps[i].skill_id, {}).get("name", steps[i].skill_id)
                 for i in moved]
        uniq: list[str] = []
        for n in names:
            if n not in uniq:
                uniq.append(n)
        warning = (f"Moved {len(moved)} linked step{'s' if len(moved) > 1 else ''} too "
                   f"({', '.join(uniq[:4])}{'…' if len(uniq) > 4 else ''}) — "
                   f"one hand has to finish what it started.")

    valid = not any(is_blocking(i) for i in issues)
    rates = cat.success_rates(req.robot_model)
    priced = cat.price_steps(steps, catalog, rates)
    if stored is not None:
        stored.steps = steps
        db.execute("UPDATE plans SET plan_json = ?, valid = ? WHERE id = ?",
                   (stored.model_dump_json(), int(valid), req.plan_id))
    return {
        "valid": valid,
        "graph": graph,
        "hands": hands,
        "depth": depth,
        "max_parallel": par,
        "hand_warning": warning,
        "moved": moved,
        "issues": [i.model_dump() for i in issues],
        "steps": [p.model_dump() for p in priced],
        "total_price_eur": round(sum(p.price_eur for p in priced), 2),
        "executable_steps": sum(1 for p in priced if p.executable),
    }


class BalanceRequest(BaseModel):
    steps: list[dict[str, Any]]
    structure: str = "dualarm"


@app.post("/api/autobalance")
def autobalance(req: BalanceRequest) -> dict[str, Any]:
    """Search hand assignments for the shortest schedule.

    One decision per hand episode rather than per step, so the result is always
    physically runnable: a hand finishes what it started.
    """
    catalog = cat.load_catalog()
    steps = [Step(skill_id=s["skill_id"], params=s.get("params") or {},
                  planned_hand=s.get("planned_hand"))
             for s in req.steps]
    if not steps:
        raise HTTPException(409, "nothing to balance")
    return balance_hands(steps, catalog, req.structure)


@app.get("/api/datasets")
def list_datasets() -> dict[str, Any]:
    path = ROOT.parent / "data" / "datasets.json"
    datasets = json.loads(path.read_text())
    credits_path = ROOT.parent / "data" / "thumb_sources.json"
    credits = json.loads(credits_path.read_text()) if credits_path.exists() else {}
    catalog = cat.load_catalog()
    clips = _clips()
    for d in datasets:
        d["clip"] = clips.get(d["id"])
        d["skills"] = sum(1 for s in catalog.values()
                          if (s.get("dataset") or {}).get("id") == d["id"])
        d["episodes"] = sum((s.get("dataset") or {}).get("episodes", 0)
                            for s in catalog.values()
                            if (s.get("dataset") or {}).get("id") == d["id"])
    return {"datasets": datasets, "thumb_credits": credits}


class ComposeRequest(BaseModel):
    plan_id: int
    name: str = ""


@app.post("/api/compose")
def compose(req: ComposeRequest) -> dict[str, Any]:
    """Turn a verified chain into a single new skill in the catalog.

    Its preconditions are whatever the chain needs from the world that no earlier
    member provides; its postconditions are what the chain leaves behind. Price is
    the sum of its parts, and it is only as ready as its least ready member.
    """
    rows = db.query("SELECT * FROM plans WHERE id = ?", (req.plan_id,))
    if not rows:
        raise HTTPException(404, "no such plan")
    row = rows[0]
    plan = CompiledPlan.model_validate_json(row["plan_json"])
    if not plan.steps:
        raise HTTPException(409, "nothing to compose")
    if not row["valid"]:
        raise HTTPException(409, "this chain does not validate, so it cannot be sold")

    catalog = cat.load_catalog()
    name = (req.name or plan.combo_name or row["prompt"]).strip()
    skill_id = "combo_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40]

    produced: set[str] = set()
    needs: list[str] = []
    leaves: set[str] = set()
    price = 0.0
    worst = "trained"
    rank = {"trained": 0, "beta": 1, "catalog": 2}
    parts: list[str] = []

    for step in plan.steps:
        skill = catalog.get(step.skill_id)
        if not skill:
            continue
        if step.skill_id not in parts:      # a skill is bought once, however often used
            price += float(skill.get("price_eur", 0))
        parts.append(step.skill_id)
        if rank.get(skill.get("status", "catalog"), 2) > rank.get(worst, 0):
            worst = skill.get("status", "catalog")
        for pre in skill.get("preconditions", []):
            if pre not in produced and pre not in needs:
                needs.append(pre)
        for gone in skill.get("deletes", []):
            leaves.discard(gone)
            produced.discard(gone)
        for post in skill.get("postconditions", []):
            produced.add(post)
            leaves.add(post)

    manifest = {
        "id": skill_id,
        "name": name,
        "title": plan.summary[:160],
        "category": "composite",
        "status": worst,
        "price_eur": round(price, 2),
        "vendor": "Composed here",
        "description": (f"Composite of {len(parts)} skills: "
                        f"{' → '.join(parts)}."),
        "preconditions": [p for p in needs if p not in INITIAL_LIKE],
        "postconditions": sorted(leaves),
        "deletes": [],
        "embodiment": (catalog.get(parts[0], {}) or {}).get("embodiment", {}),
        "checkpoint": None,
        "prompt": None,
        "thumbnail": "",
        "dataset": {"id": None, "episodes": 0, "status": "candidate"},
        "composed_of": parts,
        "est_duration_s": sum((catalog.get(p, {}) or {}).get("est_duration_s", 12.0)
                              for p in parts),
    }
    db.execute(
        """INSERT OR REPLACE INTO skills
           (id, name, vendor, category, price_eur, status, description, manifest)
           VALUES (?,?,?,?,?,?,?,?)""",
        (manifest["id"], manifest["name"], manifest["vendor"], manifest["category"],
         manifest["price_eur"], manifest["status"], manifest["description"],
         json.dumps(manifest)),
    )
    return {"skill": manifest, "parts": len(parts)}


@app.get("/api/benchmark")
def benchmark(robot_model: str | None = None) -> dict[str, Any]:
    """Measured performance, with intervals. Produced by tools/run_eval.py."""
    rows = cat.benchmark(robot_model)
    total_n = sum(r["n"] for r in rows)
    total_ok = sum(r["successes"] for r in rows)
    lo, hi = cat.wilson(total_ok, total_n) if total_n else (0.0, 1.0)
    return {
        "rows": rows,
        "total_trials": total_n,
        "total_successes": total_ok,
        "overall_rate": round(total_ok / total_n, 4) if total_n else None,
        "overall_ci": [round(lo, 4), round(hi, 4)],
        "trials_for_5pp": cat.trials_needed(0.9, 0.05),
        "trials_for_10pp": cat.trials_needed(0.9, 0.10),
    }


@app.get("/api/gaps")
def gaps(limit: int = 20) -> dict[str, Any]:
    return cat.gap_report(limit)


# --------------------------------------------------------------------------
# robot-facing (outbound polling only -- no inbound connection to the laptop)
# --------------------------------------------------------------------------
@app.get("/api/jobs/next", dependencies=[Depends(robot_auth)])
def next_job() -> dict[str, Any]:
    rows = db.query(
        "SELECT * FROM plans WHERE status = 'queued' ORDER BY id LIMIT 1"
    )
    if not rows:
        return {"job": None}
    row = rows[0]
    db.execute(
        "UPDATE plans SET status = 'running', claimed_at = datetime('now') WHERE id = ?",
        (row["id"],),
    )
    plan_obj = CompiledPlan.model_validate_json(row["plan_json"])
    catalog = cat.load_catalog()
    # Honour the hands the plan was saved with, so the robot runs what the
    # operator balanced rather than a freshly derived default.
    saved = {i: st.hand for i, st in enumerate(plan_obj.steps) if st.hand}
    hands, _, graph, depth, par = _schedule(plan_obj.steps, catalog, "dualarm", saved)
    layer_of = {n["index"]: n["layer"] for n in graph}

    steps = []
    for i, step in enumerate(plan_obj.steps):
        skill = catalog.get(step.skill_id, {})
        steps.append({
            "step_index": i,
            "skill_id": step.skill_id,
            "params": step.params,
            "hand": hands[i] if i < len(hands) else None,
            "layer": layer_of.get(i, 0),
            "checkpoint": skill.get("checkpoint"),
            "prompt": skill.get("prompt"),
            "structure": skill.get("embodiment", {}).get("structure", "dualarm"),
            "est_duration_s": skill.get("est_duration_s", 12.0),
        })

    # Group into waves. Everything in a wave is free to run at the same time;
    # the runner decides whether its executor can actually do that.
    waves: list[list[dict[str, Any]]] = [[] for _ in range(depth or 1)]
    for step in steps:
        waves[min(step["layer"], len(waves) - 1)].append(step)

    return {
        "job": {
            "plan_id": row["id"],
            "robot_model": row["robot_model"],
            "task": plan_obj.summary,
            "steps": steps,
            "waves": [w for w in waves if w],
            "depth": depth,
            "max_parallel": par,
        }
    }


@app.post("/api/runs", dependencies=[Depends(robot_auth)])
def report_run(report: RunReport) -> dict[str, Any]:
    run_id = db.execute(
        """INSERT INTO runs (plan_id, step_index, skill_id, robot_model, success,
                             duration_s, notes)
           VALUES (?,?,?,?,?,?,?)""",
        (report.plan_id, report.step_index, report.skill_id, report.robot_model,
         int(report.success), report.duration_s, report.notes),
    )
    return {"run_id": run_id}


class PlanDone(BaseModel):
    plan_id: int
    status: str  # done | failed


@app.post("/api/plans/complete", dependencies=[Depends(robot_auth)])
def complete_plan(payload: PlanDone) -> dict[str, Any]:
    if payload.status not in {"done", "failed"}:
        raise HTTPException(400, "status must be 'done' or 'failed'")
    db.execute("UPDATE plans SET status = ? WHERE id = ?", (payload.status, payload.plan_id))
    return {"plan_id": payload.plan_id, "status": payload.status}


# --------------------------------------------------------------------------
# static storefront
# --------------------------------------------------------------------------
class NoCacheStatic(StaticFiles):
    """Dev server: never let a cached app.js hide an edit you just made."""

    def is_not_modified(self, response_headers, request_headers) -> bool:  # noqa: ARG002
        return False

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["cache-control"] = "no-store, must-revalidate"
        return response


app.mount("/static", NoCacheStatic(directory=ROOT / "static"), name="static")


@app.get("/")
def landing() -> HTMLResponse:
    """The Daidai Labs landing page; its 'Amazon for Skills' bar opens /store."""
    html = (ROOT / "static" / "landing" / "index.html").read_text()
    return HTMLResponse(html, headers={"cache-control": "no-store"})


@app.get("/store")
def index() -> HTMLResponse:
    """Stamp the asset URLs with their mtime.

    Browsers cache /static/app.js hard enough that an edit can silently not load,
    which is a miserable way to lose ten minutes mid-demo. A changed file gets a
    new URL, so it always loads.
    """
    static = ROOT / "static"
    html = (static / "index.html").read_text()
    for asset in ("app.js", "style.css"):
        stamp = int((static / asset).stat().st_mtime)
        html = html.replace(f"/static/{asset}", f"/static/{asset}?v={stamp}")
    return HTMLResponse(html, headers={"cache-control": "no-store"})
