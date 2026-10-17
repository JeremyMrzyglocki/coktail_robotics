"""Exemple d'orchestrateur pour le Skill Store (à donner au coéquipier LLM/UI).

Principe : UNE connexion robot (objet `Robot`) et UN état du bar (`BarState`) créés ici,
passés à chaque skill. Les skills ne se connectent jamais elles-mêmes au CAN : deux
connexions = deux boucles de commande qui se contredisent sur le bus.

  python orchestrator_example.py --prompt "un mojito s'il te plaît"
  python orchestrator_example.py --prompt "vide la bouteille bleue"
  python orchestrator_example.py --plan '{"cocktail": "lagon_bleu"}'
  python orchestrator_example.py --context            # ce qu'on donne au LLM
  python orchestrator_example.py --backend openarm --i-understand-motors-will-be-armed --prompt mojito

Ce que le LLM reçoit (`llm_context`) : skills installées, bouteilles (couleur, boisson,
grammes restants), verre (rempli / place libre / couches), cocktails et s'ils sont faisables.
Ce qu'il renvoie (le "plan"), au choix :
  {"cocktail": "mojito"}
  {"pours": [{"container": "red", "grams": 60}, {"container": "yellow", "grams": "all"}]}
  {"skills": [{"name": "pick_place", "params": {...}}, {"name": "pour", "params": {...}}]}
Les deux premiers sont développés en : pick bouteille -> pour -> reposer bouteille, par couleur.
Le plan entier est validé (BarState.check_plan) AVANT le premier mouvement.

Intégration avec la policy pick & place :
  La policy tourne sur le GPU distant ; ici on n'a qu'un CLIENT : il envoie l'observation et
  applique les actions reçues via `robot.set_joint_targets`. Si la policy est déployée dans
  une dataflow Dora qui ouvre ELLE-MÊME le driver, il y a deux propriétaires du bus : soit
  ce client tourne dans ce processus (recommandé), soit `pour` devient un nœud Dora.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import threading
import time
import urllib.request
from dataclasses import asdict

import numpy as np

from bar_state import ALL, BarConfig, BarState, PourRequestError, load_bar_config
from pour_skill import PourConfig, pour
from robot_io import GRIPPER, Robot

log = logging.getLogger("orchestrator")

POUR_ARM, GLASS_ARM = "right_arm", "left_arm"
# Poses (rad) : À RELEVER SUR LE ROBOT pendant la téléop (log_torque.py --backend sniff).
# J7 = -0.6 : bouteille verticale (même convention que le mock).
APPROACH_ABOVE_GLASS = [0.25, 0.35, 0.0, 1.35, 0.0, 0.0, -0.6, -0.3]
GRIPPER_CLOSED, GRIPPER_OPEN = -0.3, 0.0


# --------------------------------------------------------------------------- skills

def pick_and_place(robot: Robot, object: str = "red_bottle", action: str = "pick",
                   policy_url: str | None = None, hz: float = 10.0, max_steps: int = 150,
                   stop_event: threading.Event | None = None, **_) -> dict:
    """Skill 1 (STUB). En vrai : boucle observation -> policy distante -> actions.

    action="pick"       : saisir `object` ; sortie = bouteille verticale au-dessus du verre
                          (APPROACH_ABOVE_GLASS), pince fermée — contrat d'entrée de `pour`.
    action="place_back" : reposer la bouteille à sa place, pince ouverte.
    """
    stop_event = stop_event or threading.Event()
    t0, queue = time.monotonic(), []
    for step in range(max_steps):
        if stop_event.is_set():
            return {"success": False, "reason": "stop demandé"}
        if not queue:
            obs = {"step": step, "task": f"{action} {object}",
                   "q_right": robot.get_joint_states(POUR_ARM).q.tolist(),
                   "q_left": robot.get_joint_states(GLASS_ARM).q.tolist()}
            queue = [np.asarray(a, float) for a in _call_policy(obs, policy_url, robot, action)]
            if not queue:  # la policy signale la fin de l'épisode
                break
        robot.set_joint_targets(POUR_ARM, queue.pop(0))
        time.sleep(1.0 / hz)
    robot.wait_until_reached(POUR_ARM, timeout=5.0)
    if robot.backend_name == "mock":  # simule le résultat physique du pick / de la dépose
        robot.backend.attach_bottle(object.removesuffix("_bottle") if action == "pick" else None)
    return {"success": True, "reason": "ok", "duration_s": time.monotonic() - t0}


def _call_policy(obs: dict, policy_url: str | None, robot: Robot, action: str) -> list:
    """Renvoie un "chunk" d'actions (liste de 8 positions pour le bras droit)."""
    if policy_url:
        req = urllib.request.Request(policy_url, data=json.dumps(obs).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2.0) as r:
            return json.loads(r.read())["actions"]
    # Stub local : ~150 ms de latence réseau, chunk de 10 actions vers la pose finale.
    time.sleep(0.15)
    cur = robot.get_targets(POUR_ARM)
    goal = np.array(APPROACH_ABOVE_GLASS)
    goal[GRIPPER] = GRIPPER_CLOSED if action == "pick" else GRIPPER_OPEN
    if np.max(np.abs(goal - cur)) < 1e-3:
        return []
    return [cur + (goal - cur) * k / 10 for k in range(1, 11)]


def pour_skill(robot: Robot, sensor=None, state=None, bar=None, stop_event=None,
               container="red", target_grams=60, **_) -> dict:
    res = pour(robot, target_grams, container, sensor=sensor, state=state, bar=bar,
               config=PourConfig(arm=POUR_ARM), stop_event=stop_event)
    return asdict(res)


CATALOG = {
    "pick_place": {"installed": True, "fn": pick_and_place, "desc": "Saisir / reposer un objet (policy apprise)"},
    "pour": {"installed": True, "fn": pour_skill, "desc": "Verser N grammes ou vider une bouteille (boucle fermée)"},
    "wipe": {"installed": False, "fn": None, "desc": "Essuyer une surface (bientôt)"},
}


# --------------------------------------------------------------------------- plans

def llm_context(state: BarState, bar: BarConfig) -> dict:
    """À injecter dans le prompt du LLM (JSON compact)."""
    cocktails = {}
    for name, recipe in bar.cocktails.items():
        try:
            warn = state.check_plan(list(recipe.items()))
            cocktails[name] = {"recipe_g": recipe, "possible": True, "warnings": warn}
        except PourRequestError as e:
            cocktails[name] = {"recipe_g": recipe, "possible": False, "why": str(e)}
    return {"skills": {k: {"installed": v["installed"], "desc": v["desc"]} for k, v in CATALOG.items()},
            **state.summary(bar), "cocktails": cocktails}


def expand_plan(plan: dict, bar: BarConfig) -> tuple[list[dict], list[tuple[str, float | str]]]:
    """Plan LLM -> liste de skills + liste (couleur, grammes) pour la validation."""
    if "skills" in plan:
        steps = plan["skills"]
        pours = [(s["params"]["container"], s["params"].get("target_grams", 60))
                 for s in steps if s["name"] == "pour"]
        return steps, pours
    if "cocktail" in plan:
        pours = list(bar.cocktails[plan["cocktail"]].items())
    else:
        pours = [(p["container"], p["grams"]) for p in plan["pours"]]
    steps = []
    for color, grams in pours:
        steps += [{"name": "pick_place", "params": {"object": f"{color}_bottle", "action": "pick"}},
                  {"name": "pour", "params": {"container": color, "target_grams": grams}},
                  {"name": "pick_place", "params": {"object": f"{color}_bottle", "action": "place_back"}}]
    return steps, pours


def plan_from_prompt(prompt: str, bar: BarConfig) -> dict:
    """Remplaçant du LLM pour tester : mots-clés -> plan."""
    p = prompt.lower()
    for name in bar.cocktails:
        if name.replace("_", " ") in p or name in p:
            return {"cocktail": name}
    colors = {"rouge": "red", "red": "red", "jaune": "yellow", "yellow": "yellow", "bleu": "blue", "blue": "blue"}
    color = next((c for w, c in colors.items() if w in p), None)
    if color and any(w in p for w in ("vide", "empty", "tout")):
        return {"pours": [{"container": color, "grams": ALL}]}
    if color:
        grams = next((int(w) for w in p.replace("g", " ").split() if w.isdigit()), 60)
        return {"pours": [{"container": color, "grams": grams}]}
    return {"skills": [{"name": "pick_place", "params": {"object": "cup"}}]}


def run_plan(robot: Robot, plan: dict, state: BarState, bar: BarConfig, sensor=None, stop_event=None,
             policy_url: str | None = None) -> list[dict]:
    steps, pours = expand_plan(plan, bar)
    try:
        for w in state.check_plan(pours):
            log.warning(w)
    except PourRequestError as e:
        return [{"skill": "plan", "success": False, "reason": f"refusé avant de bouger : {e}"}]
    results = []
    for item in steps:
        name = item["name"]
        entry = CATALOG.get(name)
        if not entry or not entry["installed"]:
            results.append({"skill": name, "success": False, "reason": "skill non installée"})
            break
        log.info(">>> skill %s %s", name, item.get("params", {}))
        kwargs = dict(item.get("params", {}), stop_event=stop_event)
        if name == "pour":
            kwargs.update(sensor=sensor, state=state, bar=bar)
        elif name == "pick_place" and policy_url:
            kwargs["policy_url"] = policy_url
        try:
            res = entry["fn"](robot, **kwargs)
        except PourRequestError as e:
            res = {"success": False, "reason": f"refusé : {e}"}
        results.append({"skill": name, **res})
        log.info("<<< %s : %s (%s)", name, "OK" if res["success"] else "ÉCHEC", res["reason"])
        if not res["success"] and not (name == "pour" and res.get("poured_g") is not None):
            break  # on n'enchaîne pas sur un état inconnu (un versement imprécis mais mesuré continue)
    return results


def main() -> int:
    from glass_level import GlassScale, MockGlassSensor

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", choices=["mock", "openarm"], default="mock")
    p.add_argument("--prompt", default="un mojito s'il te plaît")
    p.add_argument("--plan", default=None, help="plan JSON (sortie du LLM)")
    p.add_argument("--context", action="store_true", help="affiche le contexte LLM et quitte")
    p.add_argument("--state", choices=["fresh", "load"], default="fresh")
    p.add_argument("--policy-url", default=None, help="endpoint HTTP de la policy pick & place")
    p.add_argument("--camera", default="0")
    p.add_argument("--i-understand-motors-will-be-armed", dest="confirm", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    bar = load_bar_config()
    state = BarState.load_or_fresh(bar) if a.state == "load" else BarState.fresh(bar)
    if a.context:
        print(json.dumps(llm_context(state, bar), indent=2, ensure_ascii=False))
        return 0
    if a.backend == "openarm" and not a.confirm:
        print("Le vrai robot va être armé et va bouger. Ajoute --i-understand-motors-will-be-armed.")
        return 2

    plan = json.loads(a.plan) if a.plan else plan_from_prompt(a.prompt, bar)
    print("Plan :", json.dumps(plan, ensure_ascii=False))
    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())  # Ctrl+C = arrêt propre (redresse la bouteille)

    kw = dict(bottles=dict(state.remaining_g), glass_capacity_g=bar.glass_capacity_g) if a.backend == "mock" else {}
    robot = Robot(a.backend, arms=(POUR_ARM, GLASS_ARM), **kw)  # <- LA connexion unique
    try:
        robot.enable(POUR_ARM)
        robot.enable(GLASS_ARM)  # le bras du verre tient sa position
        sensor = MockGlassSensor(robot) if a.backend == "mock" else \
            GlassScale(camera=int(a.camera) if a.camera.isdigit() else a.camera)
        results = run_plan(robot, plan, state, bar, sensor=sensor, stop_event=stop_event, policy_url=a.policy_url)
        brief = [{k: r.get(k) for k in ("skill", "success", "reason", "container", "target", "poured_g")
                  if r.get(k) is not None} for r in results]
        print(json.dumps(brief, indent=2, ensure_ascii=False, default=float))
        print("État :", json.dumps(state.summary(bar), ensure_ascii=False, default=float))
        if a.backend == "mock":
            print("(vérité mock : verre", [(c, round(g, 1)) for c, g in robot.backend.glass_layers_g()], ")")
        return 0 if all(r["success"] for r in results) else 1
    finally:
        robot.close(disable=False)  # ne coupe pas les moteurs : la bouteille ne tombe pas


if __name__ == "__main__":
    raise SystemExit(main())
