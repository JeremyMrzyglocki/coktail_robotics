#!/usr/bin/env python3
"""Turn the paper's compile evals into the numbers, tables and plot data in the paper.

    .venv/bin/python paper/analysis.py

Reads the tagged runs data/compile_eval_*_paper-<model>.json (written by
tools/compile_eval.py --tag paper-<model>) and the catalog, and writes
paper/generated/*.tex, which main.tex \\input{}s. Nothing in the paper is typed
by hand that this script can compute.
"""
from __future__ import annotations

import collections
import glob
import itertools
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# A throwaway database, seeded from the catalog files: the analysis never reads
# or writes data/skillstore.db, and the simulated market below has a clean slate.
os.environ["SKILLSTORE_DB"] = str(Path(tempfile.mkdtemp(prefix="paper-")) / "paper.db")

from app import catalog as cat  # noqa: E402
from app import db  # noqa: E402
from app.models import Step  # noqa: E402
from app.validator import assign_hands, balance_hands, dependency_graph  # noqa: E402

OUT = ROOT / "paper" / "generated"
MODELS = [  # tag, label as printed, macro key (LaTeX names are letters only)
    ("paper-gpt41mini", "GPT-4.1 mini", "GPTmini"),
    ("paper-gpt41", "GPT-4.1", "GPT"),
    ("paper-sonnet55", "Claude Sonnet 5.5", "Sonnet"),
    ("paper-opus55", "Claude Opus 5.5", "Opus"),
]
KIND_LABEL = {
    "unmet_precondition": "Unmet precondition",
    "wrong_object": "Wrong object kind",
    "wrong_flow": "Wrong pour direction",
    "embodiment_mismatch": "Embodiment mismatch",
    "unknown_skill": "Unknown skill",
    "empty_plan": "Empty plan",
    "loose_end": "Ends holding (advisory)",
    "pointless_move": "Pointless move (advisory)",
}


def load(tag: str) -> tuple[dict, list[dict], int]:
    """The latest run for this tag: (model config, rows, runs per prompt)."""
    files = sorted(glob.glob(str(ROOT / "data" / f"compile_eval_*_{tag}.json")))
    if not files:
        raise SystemExit(f"no run for {tag}")
    d = json.loads(Path(files[-1]).read_text())
    return d["config"], d["rows"], d["runs"]


def valid_at(row: dict, k: int) -> bool:
    """Was the plan free of blocking issues after k repair rounds?"""
    rounds = [t for t in row["trace"] if t["round"] != "final"]
    final = row["trace"][-1]
    if k < len(rounds):
        return not rounds[k]["blocking"]
    # The loop stopped earlier (already fine) or ran out: the final plan stands.
    return not final["blocking"]


def wilson(ok: int, n: int) -> tuple[float, float]:
    return cat.wilson(ok, n)


def pct(x: float) -> str:
    return f"{100 * x:.0f}"


def parse_step(text: str) -> Step:
    """'move_to_station(paint bucket)' -> Step."""
    sid, _, rest = text.partition("(")
    target = rest[:-1] if rest.endswith(")") else ""
    return Step(skill_id=sid, params={"target": target} if target else {})


def similarity(a: list[str], b: list[str]) -> float:
    """1 - normalised Levenshtein distance between two step sequences."""
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return 1 - prev[-1] / max(len(a), len(b), 1)


def verb(gap_id: str) -> str:
    """Canonical motion for a gap name: its leading verb (dip_into_vessel -> dip)."""
    return gap_id.split("_")[0]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    db.init_db()
    db.seed_skills()
    catalog = {k: v for k, v in cat.load_catalog().items() if v.get("category") != "composite"}
    global MODELS
    have = [m for m in MODELS if glob.glob(str(ROOT / "data" / f"compile_eval_*_{m[0]}.json"))]
    if len(have) < len(MODELS):
        print("WARNING: no run yet for", [m[1] for m in MODELS if m not in have])
    MODELS = have
    runs = {tag: load(tag) for tag, _, _ in MODELS}

    macros: list[str] = []

    def macro(name: str, value) -> None:
        macros.append(f"\\newcommand{{\\{name}}}{{{value}}}")

    # ---- table: model comparison --------------------------------------------
    lines = []
    curve = {}
    first_kinds: dict[str, collections.Counter] = {}
    final_kinds: dict[str, collections.Counter] = {}
    all_rows = []
    for tag, label, key in MODELS:
        cfg, rows, _ = runs[tag]
        ok_rows = [r for r in rows if "error" not in r]
        all_rows += ok_rows
        n = len(ok_rows)
        v0 = sum(valid_at(r, 0) for r in ok_rows)
        v1 = sum(valid_at(r, 1) for r in ok_rows)
        vf = sum(not r["trace"][-1]["blocking"] for r in ok_rows)
        lo, hi = wilson(vf, n)
        empty = sum(r["hands_empty"] for r in ok_rows)
        gaps = sum(len(r["gaps"]) for r in ok_rows)
        secs = statistics.median(r["seconds"] for r in ok_rows)
        steps = statistics.mean(len(r["steps"]) for r in ok_rows)
        curve[label] = [v0 / n, v1 / n, vf / n]
        lines.append(
            f"{label} & {pct(v0 / n)} & {pct(v1 / n)} & \\textbf{{{pct(vf / n)}}} "
            f"\\scriptsize{{[{pct(lo)},{pct(hi)}]}} & {pct(empty / n)} & "
            f"{steps:.1f} & {gaps / n:.1f} & {secs:.0f} \\\\")
        first_kinds[label] = collections.Counter(
            k for r in ok_rows for k in set(r["trace"][0]["blocking"]))
        final_kinds[label] = collections.Counter(
            k for r in ok_rows for k in set(r["trace"][-1]["blocking"]))
        macro(f"N{key}", n)
        macro(f"Fail{key}", len(rows) - n)
        macro(f"ValidZero{key}", pct(v0 / n))
        macro(f"ValidFinal{key}", pct(vf / n))
        macro(f"ValidOne{key}", pct(v1 / n))
        macro(f"Secs{key}", f"{secs:.0f}")
        macro(f"Blocked{key}", n - vf)
    (OUT / "table_models.tex").write_text("\n".join(lines) + "\n")

    # ---- figure: validity per repair round ----------------------------------
    plots = []
    for label, ys in curve.items():
        pts = " ".join(f"({k},{100 * y:.1f})" for k, y in enumerate(ys))
        plots.append(f"\\addplot coordinates {{{pts}}};\n\\addlegendentry{{{label}}}")
    (OUT / "plot_repairs.tex").write_text("\n".join(plots) + "\n")

    # ---- table: failure types at the first binding and after repair ----------
    kinds = [k for k in KIND_LABEL if k not in ("loose_end", "pointless_move")]
    n_all = len(all_rows)
    first_all = collections.Counter(k for r in all_rows for k in set(r["trace"][0]["blocking"]))
    final_all = collections.Counter(k for r in all_rows for k in set(r["trace"][-1]["blocking"]))
    adv_first = collections.Counter(k for r in all_rows for k in set(r["trace"][0]["advisory"]))
    adv_final = collections.Counter(k for r in all_rows for k in set(r["trace"][-1]["advisory"]))
    rows_t = []
    for k in kinds + ["loose_end", "pointless_move"]:
        a = first_all[k] if k in kinds else adv_first[k]
        b = final_all[k] if k in kinds else adv_final[k]
        if a == 0 and b == 0:
            continue
        rows_t.append(f"{KIND_LABEL[k]} & {a} & {pct(a / n_all)} & {b} & {pct(b / n_all)} \\\\")
    (OUT / "table_failures.tex").write_text("\n".join(rows_t) + "\n")
    macro("NAll", n_all)
    macro("BlockedFirstAll", pct(sum(1 for r in all_rows if r["trace"][0]["blocking"]) / n_all))
    macro("BlockedFinalAll", pct(sum(1 for r in all_rows if r["trace"][-1]["blocking"]) / n_all))
    macro("BlockedFirstN", sum(1 for r in all_rows if r["trace"][0]["blocking"]))
    macro("BlockedFinalN", sum(1 for r in all_rows if r["trace"][-1]["blocking"]))
    macro("UnmetFirst", first_all["unmet_precondition"])
    macro("FlowFirst", first_all["wrong_flow"])
    macro("ObjectFirst", first_all["wrong_object"])
    macro("IssuesFirst", sum(first_all.values()))
    macro("PointlessFirst", adv_first["pointless_move"])
    macro("PointlessFinal", adv_final["pointless_move"])

    # ---- novel vs demo --------------------------------------------------------
    split = []
    for tag, label, key in MODELS:
        ok_rows = [r for r in runs[tag][1] if "error" not in r]
        cells = []
        for s in ("demo", "novel"):
            rs = [r for r in ok_rows if r["set"] == s]
            cells.append(pct(sum(not r["trace"][-1]["blocking"] for r in rs) / len(rs)))
        split.append(f"{label} & {cells[0]} & {cells[1]} \\\\")
    (OUT / "table_split.tex").write_text("\n".join(split) + "\n")

    # ---- coverage: what the final plans are made of ---------------------------
    trained = lambda sid: (catalog.get(sid, {}).get("status") in ("trained", "beta")  # noqa: E731
                           and bool(catalog.get(sid, {}).get("checkpoint")))
    tiers = collections.Counter()
    gap_ds = collections.Counter()
    gap_total = gap_with = 0
    for r in all_rows:
        for st in r["steps"]:
            sid = st.split("(")[0]
            tiers["trained" if trained(sid) else "untrained"] += 1
        tiers["gap"] += len(r["gaps"])
        for g in r["gaps"]:
            gap_total += 1
            if g["dataset"]:
                gap_with += 1
                gap_ds[g["dataset"]] += 1
    tot = sum(tiers.values())
    macro("StepsTotal", tot)
    macro("ShareTrained", pct(tiers["trained"] / tot))
    macro("ShareUntrained", pct(tiers["untrained"] / tot))
    macro("ShareGap", pct(tiers["gap"] / tot))
    macro("GapTotal", gap_total)
    macro("GapWithData", pct(gap_with / gap_total) if gap_total else "0")
    top = gap_ds.most_common(5)
    ds = cat.datasets()
    (OUT / "table_gapdata.tex").write_text("\n".join(
        f"{ds.get(k, {}).get('name', k).replace('_', ' ').replace('&', 'and')} & {n} \\\\"
        for k, n in top) + "\n")
    distinct_gaps = len({g["id"] for r in all_rows for g in r["gaps"]})
    macro("DistinctGaps", distinct_gaps)
    macro("ApiFailures", sum(1 for tag, _, _ in MODELS for r in runs[tag][1] if "error" in r))
    ego = sum(n for k, n in gap_ds.items() if ds.get(k, {}).get("kind") == "egocentric")
    macro("GapEgoShare", pct(ego / gap_with) if gap_with else "0")

    # ---- catalog and datasets ----------------------------------------------
    x = {k: v for k, v in json.loads((ROOT / "data" / "skill_datasets.json").read_text()).items()
         if k != "_about"}
    eps = [sum(int(d.get("episodes") or 0) for d in x.get(k, [])) for k in catalog]
    macro("NSkills", len(catalog))
    macro("NTrained", sum(1 for s in catalog.values() if s["status"] == "trained"))
    macro("NBeta", sum(1 for s in catalog.values() if s["status"] == "beta"))
    macro("NCatalogOnly", sum(1 for s in catalog.values() if s["status"] == "catalog"))
    macro("NDatasets", len(cat.datasets()))
    macro("NOpenDatasets", len(cat.open_datasets()))
    macro("NLinks", sum(len(v) for v in x.values()))
    macro("MedianEpisodes", f"{statistics.median(eps):.0f}")
    macro("MinEpisodes", min(eps))
    macro("TotalEpisodes", f"{sum(eps):,}".replace(",", "{,}"))
    preds = set()
    for s in catalog.values():
        preds |= set(s.get("preconditions", [])) | set(s.get("postconditions", []))
    macro("NPredicates", len(preds))
    macro("NKinds", len(cat.object_kinds()))
    macro("NActsOn", sum(1 for s in catalog.values() if s.get("acts_on")))
    macro("Runs", runs[MODELS[0][0]][2])

    extras(runs, catalog, macro)

    # Table bodies as macros too: \input inside a tabular is not reliable.
    for name, fname in (("TabModels", "table_models.tex"), ("TabFailures", "table_failures.tex"),
                        ("TabSplit", "table_split.tex"), ("TabGapData", "table_gapdata.tex"),
                        ("PlotRepairs", "plot_repairs.tex"), ("TabRequests", "table_requests.tex"),
                        ("TabStability", "table_stability.tex"), ("TabVerbs", "table_verbs.tex"),
                        ("TabBids", "table_bids.tex"), ("TabCategories", "table_categories.tex"),
                        ("PlotSpeedup", "plot_speedup.tex")):
        body = (OUT / fname).read_text().strip()
        macros.append(f"\\def\\{name}{{{body}}}")
    (OUT / "numbers.tex").write_text("\n".join(macros) + "\n")
    # A readable summary for whoever runs this.
    for label, ys in curve.items():
        print(f"{label:18} valid after 0/1/2 repairs: " + " / ".join(pct(y) for y in ys))
    print("first-shot blocking kinds:", dict(first_all))
    print("final blocking kinds:", dict(final_all))
    print("tiers:", dict(tiers), "gaps with data:", gap_with, "/", gap_total, "top:", top)
    print("written:", sorted(p.name for p in OUT.iterdir()))


SHORT = {  # request -> label in the per-request table
    "You have a paint bucket and brush. draw an image on the table": "Paint an image",
    "build a small sandcastle on the tray with the bucket and shovel": "Sandcastle",
    "do a simple card trick with the deck on the table": "Card trick",
    "water the two plants on the shelf": "Water plants",
    "write my name on the whiteboard with the marker": "Write on whiteboard",
    "make me a jam sandwich": "Jam sandwich",
    "put the flowers in the vase and add water": "Flowers in vase",
    "feed the cat: open the tin and put the food in her bowl": "Feed the cat",
    "make me a pina colada": "Pi\\~na colada",
    "pour me a glass of juice": "Glass of juice",
    "mix me a smoothie": "Smoothie",
    "wipe my table clean after dinner": "Wipe table",
    "clear the table and put the bottles away": "Clear table",
}


def extras(runs, catalog, macro) -> None:
    """The analyses added for the long version: per-request results, stability
    across runs, two-arm scheduling, gap-name grouping, a simulated data market
    and the curated-data landscape."""
    from app.bidding import BidParams, bids
    from tools.compile_eval import DEMO, NOVEL

    ok = {tag: [r for r in runs[tag][1] if "error" not in r] for tag, _, _ in MODELS}

    # ---- per request: first binding / final, valid out of runs ---------------
    lines = []
    for prompt in NOVEL + DEMO:
        cells = []
        for tag, _, _ in MODELS:
            rs = [r for r in ok[tag] if r["prompt"] == prompt]
            first = sum(valid_at(r, 0) for r in rs)
            final = sum(not r["trace"][-1]["blocking"] for r in rs)
            shade = int(100 * first / max(len(rs), 1))
            mark = "" if final == len(rs) else "$^\\dagger$"
            cells.append(f"\\cellcolor{{green!{max(shade // 3, 4)}}}{first}/{len(rs)}{mark}")
        set_ = "N" if prompt in NOVEL else "D"
        lines.append(f"{SHORT[prompt]} & {set_} & " + " & ".join(cells) + " \\\\")
    (OUT / "table_requests.tex").write_text("\n".join(lines) + "\n")

    # ---- stability across the runs of one request ----------------------------
    lines = []
    for tag, label, key in MODELS:
        sims_skill, sims_full, gap_j, same = [], [], [], 0
        pairs = 0
        for prompt in NOVEL + DEMO:
            rs = [r for r in ok[tag] if r["prompt"] == prompt]
            for a, b in itertools.combinations(rs, 2):
                pairs += 1
                sa = [x.split("(")[0] for x in a["steps"]]
                sb = [x.split("(")[0] for x in b["steps"]]
                sims_skill.append(similarity(sa, sb))
                sims_full.append(similarity(a["steps"], b["steps"]))
                same += a["steps"] == b["steps"]
                ga, gb = {verb(g["id"]) for g in a["gaps"]}, {verb(g["id"]) for g in b["gaps"]}
                gap_j.append(len(ga & gb) / len(ga | gb) if ga | gb else 1.0)
        lines.append(f"{label} & {statistics.mean(sims_skill):.2f} & "
                     f"{statistics.mean(sims_full):.2f} & {pct(same / pairs)} & "
                     f"{statistics.mean(gap_j):.2f} \\\\")
        macro(f"Stab{key}", f"{statistics.mean(sims_skill):.2f}")
        macro(f"Same{key}", pct(same / pairs))
    (OUT / "table_stability.tex").write_text("\n".join(lines) + "\n")

    # ---- two-arm scheduling of the valid final plans ------------------------
    speed_all, both_all, pts, bal_all, bal_pts, par_any, par_bal = [], [], [], [], [], 0, 0
    for tag, label, key in MODELS:
        sp, both, par, bal = [], 0, [], []
        for r in ok[tag]:
            if r["trace"][-1]["blocking"] or not r["steps"]:
                continue
            steps = [parse_step(x) for x in r["steps"]]
            hands = assign_hands(steps, catalog)
            graph = dependency_graph(steps, catalog, hands)
            depth = max(n["layer"] for n in graph) + 1
            width = collections.Counter(n["layer"] for n in graph)
            sp.append(len(steps) / depth)
            par.append(max(width.values()))
            both += len({h for h in hands if h}) == 2
            pts.append((len(steps), depth))
            par_any += depth < len(steps)
            # Episode-level search for a faster split across the two arms; it
            # never accepts an assignment that adds a blocking issue.
            after = balance_hands(steps, catalog)["after"]["depth"]
            bal.append(len(steps) / after)
            bal_pts.append((len(steps), after))
            par_bal += after < len(steps)
        speed_all += sp
        bal_all += bal
        both_all.append((both, len(sp)))
        macro(f"Bal{key}", f"{statistics.mean(bal):.2f}")
        macro(f"Speed{key}", f"{statistics.median(sp):.2f}")
        macro(f"Both{key}", pct(both / len(sp)))
    macro("SpeedAll", f"{statistics.median(speed_all):.2f}")
    macro("SpeedMax", f"{max(speed_all):.1f}")
    macro("BothAll", pct(sum(b for b, _ in both_all) / sum(n for _, n in both_all)))
    macro("SavedAll", pct(1 - 1 / statistics.median(speed_all)))
    macro("NScheduled", len(speed_all))
    macro("ParShare", pct(par_any / len(speed_all)))
    macro("ParShareBal", pct(par_bal / len(speed_all)))
    macro("SpeedMeanDefault", f"{statistics.mean(speed_all):.2f}")
    macro("SpeedMeanBal", f"{statistics.mean(bal_all):.2f}")
    macro("SpeedMaxBal", f"{max(bal_all):.1f}")
    macro("TimeSavedBal", pct(1 - sum(b for _, b in bal_pts) / sum(a for a, _ in bal_pts)))
    (OUT / "plot_speedup.tex").write_text(
        "\\addplot[only marks, mark=*, mark size=1.2pt, gray, fill opacity=0.3, "
        "draw opacity=0.4] coordinates {" + " ".join(f"({a},{b})" for a, b in pts) + "};\n"
        "\\addlegendentry{default hands}\n"
        "\\addplot[only marks, mark=triangle*, mark size=1.5pt, red!70!black, fill opacity=0.5, "
        "draw opacity=0.6] coordinates {" + " ".join(f"({a},{b})" for a, b in bal_pts) + "};\n"
        "\\addlegendentry{balanced}\n")

    # ---- gap names grouped by their leading verb ----------------------------
    all_gaps = [g for tag, _, _ in MODELS for r in ok[tag] for g in r["gaps"]]
    names_by_verb = collections.defaultdict(set)
    count_by_verb = collections.Counter()
    for g in all_gaps:
        names_by_verb[verb(g["id"])].add(g["id"])
        count_by_verb[verb(g["id"])] += 1
    macro("DistinctVerbs", len(names_by_verb))
    lines = []
    for v, n in count_by_verb.most_common(8):
        ex = sorted(names_by_verb[v], key=lambda n: (len(n), n))[:2]   # deterministic
        lines.append(f"\\code{{{v}}} & {n} & {len(names_by_verb[v])} & "
                     + ", ".join(f"\\code{{{e.replace('_', chr(92) + '_')}}}" for e in ex) + " \\\\")
    (OUT / "table_verbs.tex").write_text("\n".join(lines) + "\n")

    # ---- a simulated data market: every compilation as a customer request ----
    def market(rename) -> dict:
        db.execute("DELETE FROM requests")
        db.execute("DELETE FROM plans")
        for tag, _, _ in MODELS:
            for r in ok[tag]:
                plan = {"summary": "", "steps": [{"skill_id": x.split("(")[0]} for x in r["steps"]],
                        "missing": []}
                pid = db.execute("INSERT INTO plans (prompt, robot_model, plan_json, valid) "
                                 "VALUES (?,?,?,0)", (r["prompt"], "sim", json.dumps(plan)))
                gaps = [{"proposed_id": rename(g["id"]), "name": rename(g["id"]),
                         "description": g["description"], "dataset_id": g["dataset"] or ""}
                        for g in r["gaps"]]
                db.execute("INSERT INTO requests (prompt, robot_model, plan_id, missing_json) "
                           "VALUES (?,?,?,?)", (r["prompt"], "sim", pid, json.dumps(gaps)))
        return bids(BidParams())
    raw, canon = market(lambda x: x), market(verb)
    macro("MarketSkillsRaw", len(raw["skills"]))
    macro("MarketSkillsCanon", len(canon["skills"]))
    macro("MarketRequests", raw["unserved_requests"])
    macro("MarketPacingRaw", pct(raw["pacing"]))
    macro("MarketPacingCanon", pct(canon["pacing"]))
    lines = []
    for i in range(6):
        a = raw["skills"][i] if i < len(raw["skills"]) else None
        b = canon["skills"][i] if i < len(canon["skills"]) else None
        cell = lambda e: (f"\\code{{{e['skill_id'].replace('_', chr(92) + '_')}}} & "  # noqa: E731
                          f"{e['bid_per_episode_eur']:.2f}") if e else " & "
        lines.append(f"{i + 1} & {cell(a)} & {cell(b)} \\\\")
    (OUT / "table_bids.tex").write_text("\n".join(lines) + "\n")
    macro("TopBidRaw", f"{raw['skills'][0]['bid_per_episode_eur']:.2f}")
    macro("TopBidCanon", f"{canon['skills'][0]['bid_per_episode_eur']:.2f}")

    # ---- curated data per skill category ------------------------------------
    x = {k: v for k, v in json.loads((ROOT / "data" / "skill_datasets.json").read_text()).items()
         if k != "_about"}
    lines = []
    for c in sorted({s["category"] for s in catalog.values()}):
        ks = [k for k in catalog if catalog[k]["category"] == c]
        eps = [sum(int(d.get("episodes") or 0) for d in x.get(k, [])) for k in ks]
        tr = sum(1 for k in ks if catalog[k]["status"] == "trained")
        lines.append(f"{c.capitalize()} & {len(ks)} & {tr} & {statistics.median(eps):,.0f} \\\\"
                     .replace(",", "{,}"))
    (OUT / "table_categories.tex").write_text("\n".join(lines) + "\n")
    kinds = collections.Counter(d.get("kind") for d in cat.datasets().values())
    macro("NTeleop", kinds.get("teleop", 0))
    macro("NEgo", kinds.get("egocentric", 0))
    macro("NSim", kinds.get("sim", 0))


if __name__ == "__main__":
    main()
