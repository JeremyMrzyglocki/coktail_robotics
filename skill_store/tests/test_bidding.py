"""The data-bid model: more unmet demand must mean a higher bid, repeats of
one prompt must not buy a dataset, and the budget must hold."""
import json

from app import db
from app.bidding import BidParams, bids


def log(prompt, gaps, steps=("locate_object", "grasp_object")):
    plan = {"summary": "", "steps": [{"skill_id": s} for s in steps], "missing": []}
    pid = db.execute("INSERT INTO plans (prompt, robot_model, plan_json, valid) "
                     "VALUES (?,?,?,0)", (prompt, "Moz1", json.dumps(plan)))
    db.execute("INSERT INTO requests (prompt, robot_model, plan_id, missing_json) "
               "VALUES (?,?,?,?)", (prompt, "Moz1", pid, json.dumps(
                   [{"proposed_id": g, "name": g, "description": ""} for g in gaps])))


def by_id(result):
    return {e["skill_id"]: e for e in result["skills"]}


def test_distinct_requests_outbid_one_repeated_prompt(fresh_requests):
    for _ in range(10):
        log("peel a banana", ["peel_item"])
    for k in range(4):
        log(f"cut fruit number {k}", ["cut_item"])
    b = by_id(bids(BidParams(budget_eur=1e9)))
    assert b["cut_item"]["bid_per_episode_eur"] > b["peel_item"]["bid_per_episode_eur"]
    assert b["peel_item"]["requests"] == 10 and b["peel_item"]["distinct_prompts"] == 1


def test_more_demand_never_lowers_the_bid(fresh_requests):
    log("a", ["x_gap"])
    one = by_id(bids(BidParams(budget_eur=1e9)))["x_gap"]["bid_per_episode_eur"]
    log("b", ["x_gap"])
    two = by_id(bids(BidParams(budget_eur=1e9)))["x_gap"]["bid_per_episode_eur"]
    assert two > one


def test_spend_stays_within_budget(fresh_requests):
    for k in range(30):
        log(f"request {k}", [f"gap_{k % 7}"])
    r = bids(BidParams(budget_eur=100))
    assert r["spend_eur"] <= 100 + 1e-6
    assert r["pacing"] < 1


def test_untrained_catalog_skills_count_as_blockers(fresh_requests, catalog):
    untrained = next(sid for sid, s in catalog.items()
                     if s.get("status") == "catalog" and s.get("category") != "composite")
    log("shake it", [], steps=("locate_object", untrained))
    b = by_id(bids())
    assert b[untrained]["kind"] == "untrained"


def test_no_demand_no_bids(fresh_requests):
    r = bids()
    assert r["skills"] == [] and r["spend_eur"] == 0


def test_a_request_made_only_of_gaps_still_gets_a_bid(fresh_requests):
    log("juggle three balls", ["juggle"], steps=())
    assert by_id(bids())["juggle"]["bid_per_episode_eur"] > 0
