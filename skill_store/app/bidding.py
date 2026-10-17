"""What Daidai Labs should pay for data, per skill, from the demand it could not serve.

A value-based autobidder, the kind ad exchanges run, pointed at data collection:

  1. Demand. Every logged request whose plan could not run counts toward each
     skill that blocked it: a gap (no catalog skill does the motion) or an
     untrained catalog skill (listed, no checkpoint). Repeats of the same prompt
     are damped harmonically -- the k-th identical request counts 1/k -- so one
     person retrying cannot buy a dataset, while distinct requests count fully.
     Older requests fade with a half-life.

  2. Value. A blocked request is a sale lost: the price of its whole plan, a gap
     counted at a typical skill's price. That plan needs every one of its
     blockers filled, so each gets an equal share.
     Each logged request stands for `sales_per_request` future sales once the
     skill exists (the extrapolation is a parameter, not a fact).

  3. Bid. Spend at most value / target ROI on the skill's data, spread over the
     episodes it needs. A matching open dataset cuts the episodes needed: the
     open data does the pretraining, paid episodes only cover the robot.

  4. Pacing. If all bids together exceed the monthly budget, every bid is scaled
     by the same factor, so the ranking -- more unmet demand, higher bid -- holds.

Every constant is in BidParams; the admin page exposes them as sliders.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from . import catalog as cat
from . import db


@dataclass
class BidParams:
    budget_eur: float = 5000.0          # data budget per month, all skills together
    target_roi: float = 3.0             # pay at most 1/ROI of the value unlocked
    sales_per_request: float = 10.0     # future sales one logged request stands for
    episodes_needed: int = 50           # demonstrations to train one skill from scratch
    open_data_discount: float = 0.4     # share of those an open dataset makes unnecessary
    half_life_days: float = 30.0        # how fast old demand fades
    max_bid_per_episode: float = 60.0   # never pay more than this for one episode
    batch_episodes: int = 10            # the "X" in "per X episodes" on the page


def _age_days(created_at: str, now: datetime) -> float:
    try:
        t = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, (now - t).total_seconds() / 86400)


def _blockers(missing_json: str, plan_json: str | None,
              catalog: dict[str, Any]) -> tuple[list[tuple[str, str, dict]], list[str]]:
    """What stopped one request from running: its gaps and its untrained skills,
    each once. Also returns the plan's distinct skill ids, for pricing it."""
    plan = json.loads(plan_json) if plan_json else {}
    step_ids = list(dict.fromkeys(s["skill_id"] for s in plan.get("steps", [])))
    found: dict[str, tuple[str, str, dict]] = {}
    for g in json.loads(missing_json or "[]"):
        found.setdefault(g["proposed_id"], ("gap", g["proposed_id"], g))
    for sid in step_ids:
        skill = catalog.get(sid)
        if skill and (skill.get("status") == "catalog" or not skill.get("checkpoint")):
            found.setdefault(sid, ("untrained", sid, skill))
    return list(found.values()), step_ids


def unserved_demand(p: BidParams) -> tuple[list[dict[str, Any]], int]:
    """Every skill that blocked at least one request, with its demand and value,
    and how many requests were blocked at all."""
    catalog = cat.load_catalog()
    # A gap, once filled, is a skill the customer buys too; until it has a price
    # it is worth what a typical skill costs. Without this, a request made only
    # of gaps would be worth nothing however often it was asked.
    prices = sorted(float(s.get("price_eur", 0)) for s in catalog.values()
                    if s.get("category") != "composite")
    typical = prices[len(prices) // 2] if prices else 0.0
    rows = db.query("""SELECT r.prompt, r.missing_json, r.created_at, p.plan_json
                       FROM requests r LEFT JOIN plans p ON p.id = r.plan_id
                       ORDER BY r.id""")
    now = datetime.now(timezone.utc)
    seen_prompt: dict[tuple[str, str], int] = {}
    out: dict[str, dict[str, Any]] = {}
    blocked = 0

    for r in rows:
        blockers, step_ids = _blockers(r["missing_json"], r["plan_json"], catalog)
        if not blockers:
            continue
        blocked += 1
        plan_value = sum(float(catalog.get(sid, {}).get("price_eur", 0)) for sid in step_ids) \
            + typical * sum(1 for kind, _, _ in blockers if kind == "gap")
        share = plan_value / len(blockers)
        decay = 0.5 ** (_age_days(r["created_at"], now) / p.half_life_days)
        prompt = " ".join(r["prompt"].lower().split())

        for kind, key, info in blockers:
            n = seen_prompt.get((key, prompt), 0) + 1
            seen_prompt[(key, prompt)] = n
            weight = decay / n                      # harmonic damping of repeats
            e = out.setdefault(key, {
                "skill_id": key, "kind": kind,
                "name": info.get("name") or key,
                "description": info.get("description", ""),
                "requests": 0, "prompts": set(), "effective_demand": 0.0,
                "value_blocked_eur": 0.0, "dataset_id": "", "dataset_name": "",
                "last_seen": r["created_at"],
            })
            e["requests"] += 1
            e["prompts"].add(prompt)
            e["effective_demand"] += weight
            e["value_blocked_eur"] += weight * share
            e["last_seen"] = r["created_at"]
            if kind == "gap" and info.get("dataset_id") and not e["dataset_id"]:
                ds = cat.open_datasets().get(info["dataset_id"])
                if ds:
                    e["dataset_id"], e["dataset_name"] = ds["id"], ds["name"]
            elif kind == "untrained" and not e["dataset_id"]:
                avail, ds = cat.availability(info)
                if avail == "data_only" and ds:
                    e["dataset_id"], e["dataset_name"] = ds["id"], ds["name"]
    return list(out.values()), blocked


def bids(p: BidParams | None = None) -> dict[str, Any]:
    p = p or BidParams()
    items, blocked = unserved_demand(p)
    for e in items:
        has_data = bool(e["dataset_id"])
        e["episodes_needed"] = max(1, round(p.episodes_needed *
                                            (1 - p.open_data_discount if has_data else 1)))
        e["projected_value_eur"] = e["value_blocked_eur"] * p.sales_per_request
        e["max_spend_eur"] = e["projected_value_eur"] / p.target_roi
        e["bid_per_episode_raw"] = min(p.max_bid_per_episode,
                                       e["max_spend_eur"] / e["episodes_needed"])

    total = sum(e["bid_per_episode_raw"] * e["episodes_needed"] for e in items)
    pacing = min(1.0, p.budget_eur / total) if total > 0 else 1.0
    for e in items:
        e["bid_per_episode_eur"] = round(e["bid_per_episode_raw"] * pacing, 2)
        e["bid_per_batch_eur"] = round(e["bid_per_episode_eur"] * p.batch_episodes, 2)
        e["spend_eur"] = round(e["bid_per_episode_raw"] * pacing * e["episodes_needed"], 2)
        e["distinct_prompts"] = len(e["prompts"])
        e["example_prompts"] = sorted(e.pop("prompts"))[:3]
        for k in ("effective_demand", "value_blocked_eur", "projected_value_eur",
                  "max_spend_eur", "bid_per_episode_raw"):
            e[k] = round(e[k], 2)

    items.sort(key=lambda e: (-e["bid_per_episode_eur"], -e["effective_demand"]))
    spend = total * pacing          # from unrounded bids, so it never tops the budget
    return {
        "params": asdict(p),
        "pacing": round(pacing, 4),
        "unpaced_spend_eur": round(total, 2),
        "spend_eur": round(spend, 2),
        "value_blocked_eur": round(sum(e["value_blocked_eur"] for e in items), 2),
        "unserved_requests": blocked,
        "total_requests": db.query("SELECT COUNT(*) AS n FROM requests")[0]["n"],
        "skills": items,
    }

