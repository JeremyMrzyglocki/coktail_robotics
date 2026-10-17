"""Exemple d'orchestrateur pour le Skill Store (à donner au coéquipier LLM/UI).

Principe : UNE connexion robot (objet `Robot`) créée ici, passée à chaque skill.
Les skills ne se connectent jamais elles-mêmes au CAN : deux connexions = deux
boucles de commande qui se contredisent sur le bus.

  python orchestrator_example.py --prompt "je veux un barman"          # mock
  python orchestrator_example.py --plan '{"skills":[{"name":"pour","params":{"target_amount":0.4}}]}'
  python orchestrator_example.py --backend openarm --i-understand-motors-will-be-armed --prompt barman

Format attendu de la sortie du LLM (le "plan") :
  {"skills": [{"name": "pick_place", "params": {"object": "bottle"}},
              {"name": "pour",       "params": {"target_amount": 0.5}}]}

Intégration avec la policy pick & place :
  La policy tourne sur le GPU distant ; ici on n'a qu'un CLIENT : il envoie
  l'observation (positions articulaires, + images en vrai) et applique les
  actions reçues via `robot.set_joint_targets`. Si la policy est déployée dans
  une dataflow Dora (stack Enactic) qui ouvre ELLE-MÊME le driver, alors il y a
  deux propriétaires du bus : il faut soit faire tourner ce client dans ce
  processus (recommandé), soit transformer `pour` en nœud Dora. À trancher tôt.
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

from pour_skill import PourConfig, pour
from robot_io import GRIPPER, Robot

log = logging.getLogger("orchestrator")

POUR_ARM, GLASS_ARM = "right_arm", "left_arm"
# Poses (rad) : À RELEVER SUR LE ROBOT pendant la téléop (log_torque.py en mode sniff les donne).
APPROACH_ABOVE_GLASS = [0.25, 0.35, 0.0, 1.35, 0.0, 0.0, 0.0, -0.3]
GRIPPER_CLOSED = -0.3


# --------------------------------------------------------------------------- skills

def pick_and_place(robot: Robot, object: str = "bottle", policy_url: str | None = None,
                   hz: float = 10.0, max_steps: int = 150, stop_event: threading.Event | None = None) -> dict:
    """Skill 1 (STUB). En vrai : boucle observation -> policy distante -> actions.

    Contrat de sortie, attendu par `pour` : bouteille dans la pince du bras
    droit, verticale, au-dessus du verre (APPROACH_ABOVE_GLASS), bras armé.
    """
    stop_event = stop_event or threading.Event()
    t0 = time.monotonic()
    queue: list[np.ndarray] = []
    for step in range(max_steps):
        if stop_event.is_set():
            return {"success": False, "reason": "stop demandé"}
        if not queue:
            obs = {"step": step,
                   "q_right": robot.get_joint_states(POUR_ARM).q.tolist(),
                   "q_left": robot.get_joint_states(GLASS_ARM).q.tolist()}
            queue = [np.asarray(a, float) for a in _call_policy(obs, policy_url, robot)]
            if not queue:  # la policy signale la fin de l'épisode
                break
        robot.set_joint_targets(POUR_ARM, queue.pop(0))
        time.sleep(1.0 / hz)
    robot.wait_until_reached(POUR_ARM, timeout=5.0)
    return {"success": True, "reason": "ok", "duration_s": time.monotonic() - t0}


def _call_policy(obs: dict, policy_url: str | None, robot: Robot) -> list:
    """Renvoie un "chunk" d'actions (liste de 8 positions pour le bras droit)."""
    if policy_url:
        req = urllib.request.Request(policy_url, data=json.dumps(obs).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2.0) as r:
            return json.loads(r.read())["actions"]
    # Stub local : on simule ~150 ms de latence réseau et un chunk de 10 actions
    # qui amène la bouteille au-dessus du verre, pince fermée.
    time.sleep(0.15)
    cur = robot.get_targets(POUR_ARM)
    goal = np.array(APPROACH_ABOVE_GLASS)
    goal[GRIPPER] = GRIPPER_CLOSED
    if np.max(np.abs(goal - cur)) < 1e-3:
        return []
    return [cur + (goal - cur) * k / 10 for k in range(1, 11)]


def pour_skill(robot: Robot, sensor=None, stop_event=None, **params) -> dict:
    cfg = PourConfig(arm=POUR_ARM)  # approach_pose=None : pick_place nous a déjà amenés au-dessus du verre
    res = pour(robot, sensor=sensor, config=cfg, stop_event=stop_event, **params)
    return asdict(res)


CATALOG = {
    "pick_place": {"installed": True, "fn": pick_and_place, "desc": "Saisir et déplacer un objet (policy apprise)"},
    "pour": {"installed": True, "fn": pour_skill, "desc": "Verser riz/bonbons dans un verre (boucle fermée)"},
    "wipe": {"installed": False, "fn": None, "desc": "Essuyer une surface (bientôt)"},
}

RECIPES = {  # ce que le LLM proposerait
    "barman": [{"name": "pick_place", "params": {"object": "bottle"}},
               {"name": "pour", "params": {"target_amount": 0.5}}],
    "pick": [{"name": "pick_place", "params": {"object": "cup"}}],
}


def plan_from_prompt(prompt: str) -> dict:
    """Remplaçant du LLM pour tester : mot-clé -> recette."""
    p = prompt.lower()
    key = "barman" if any(w in p for w in ("barman", "verse", "pour", "drink")) else "pick"
    return {"skills": RECIPES[key]}


def run_plan(robot: Robot, plan: dict, sensor=None, stop_event=None) -> list[dict]:
    results = []
    for item in plan["skills"]:
        name = item["name"]
        entry = CATALOG.get(name)
        if not entry or not entry["installed"]:
            results.append({"skill": name, "success": False, "reason": "skill non installée"})
            break
        log.info(">>> skill %s %s", name, item.get("params", {}))
        kwargs = dict(item.get("params", {}), stop_event=stop_event)
        if name == "pour":
            kwargs["sensor"] = sensor
        res = entry["fn"](robot, **kwargs)
        results.append({"skill": name, **res})
        log.info("<<< %s : %s (%s)", name, "OK" if res["success"] else "ÉCHEC", res["reason"])
        if not res["success"]:
            break  # on n'enchaîne pas sur un état inconnu
    return results


def main() -> int:
    from glass_level import GlassLevelSensor, MockGlassSensor

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", choices=["mock", "openarm"], default="mock")
    p.add_argument("--prompt", default="je veux un barman")
    p.add_argument("--plan", default=None, help="plan JSON (sortie du LLM)")
    p.add_argument("--policy-url", default=None, help="endpoint HTTP de la policy pick & place")
    p.add_argument("--camera", default="0")
    p.add_argument("--i-understand-motors-will-be-armed", dest="confirm", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if a.backend == "openarm" and not a.confirm:
        print("Le vrai robot va être armé et va bouger. Ajoute --i-understand-motors-will-be-armed.")
        return 2

    plan = json.loads(a.plan) if a.plan else plan_from_prompt(a.prompt)
    if a.policy_url:
        for it in plan["skills"]:
            if it["name"] == "pick_place":
                it.setdefault("params", {})["policy_url"] = a.policy_url
    print("Plan :", json.dumps(plan, ensure_ascii=False))

    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())  # Ctrl+C = arrêt propre (redresse la bouteille)

    robot = Robot(a.backend, arms=(POUR_ARM, GLASS_ARM))  # <- LA connexion unique
    try:
        robot.enable(POUR_ARM)
        robot.enable(GLASS_ARM)  # le bras du verre tient sa position
        if a.backend == "mock":
            sensor = MockGlassSensor(robot)
        else:
            sensor = GlassLevelSensor(camera=int(a.camera) if a.camera.isdigit() else a.camera)
        results = run_plan(robot, plan, sensor=sensor, stop_event=stop_event)
        print(json.dumps(results, indent=2, ensure_ascii=False, default=float))
        return 0 if all(r["success"] for r in results) else 1
    finally:
        robot.close(disable=False)  # ne coupe pas les moteurs : la bouteille ne tombe pas


if __name__ == "__main__":
    raise SystemExit(main())
