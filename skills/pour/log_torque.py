"""Enregistre positions / vitesses / couples du bras verseur en CSV.

LECTURE SEULE PAR DÉFAUT : aucune commande n'est envoyée.

  # Mac, données simulées (une "pesée" de 3 s avec 50 g de riz en plus)
  python log_torque.py --backend mock --mass-g 60 --duration 3 --approach-side

  # VM robot, pendant que la téléop d'un coéquipier pilote le bras :
  # écoute passive du bus, zéro trame envoyée.
  python log_torque.py --backend sniff --arm right_arm --duration 60 --label teleop_pour

  # VM robot, personne d'autre sur le bus : interroge les moteurs (trames de
  # lecture seulement). Moteurs NON armés => bras mou, couple ~0.
  python log_torque.py --backend openarm --duration 5

  # Pesée statique : arme le bras et tient la position actuelle.
  # Envoie des commandes ! Bras soutenu à la main au démarrage.
  python log_torque.py --backend openarm --hold --approach-side --i-understand-motors-will-be-armed --mass-g 60

Colonnes : t, t_rel, label, mass_g, q_J1..q_gripper, dq_*, tau_*.
"""

from __future__ import annotations

import argparse
import csv
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from robot_io import JOINT_NAMES, Robot

HERE = Path(__file__).resolve().parent   # sorties dans la skill, quel que soit le dossier courant


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", choices=["mock", "sniff", "openarm"], default="mock")
    p.add_argument("--arm", default="right_arm", help="bras verseur (défaut right_arm)")
    p.add_argument("--can", default=None, help="interface CAN (défaut : can0 droit, can1 gauche)")
    p.add_argument("--hz", type=float, default=100.0)
    p.add_argument("--duration", type=float, default=10.0, help="secondes (0 = jusqu'à Ctrl+C)")
    p.add_argument("--label", default="", help="étiquette libre (ex. 'vide', 'pose_A')")
    p.add_argument("--mass-g", type=float, default=None, help="masse ajoutée connue (calibration)")
    p.add_argument("--out", default=None, help="CSV de sortie (défaut data/torque_<date>.csv)")
    p.add_argument("--hold", action="store_true", help="arme le bras et tient la position (envoie des commandes)")
    p.add_argument("--approach-side", action="store_true",
                   help="avec --hold/mock : petit aller-retour de J2 et J4 vers le bas avant de mesurer, "
                        "pour arriver toujours par le même côté (frottement sec)")
    p.add_argument("--i-understand-motors-will-be-armed", dest="confirm", action="store_true")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def main() -> int:
    a = parse_args()
    if a.hold and not a.confirm:
        print("--hold arme les moteurs. Ajoute --i-understand-motors-will-be-armed.", file=sys.stderr)
        return 2
    if a.hold and a.backend == "sniff":
        print("--hold impossible avec le backend sniff (passif).", file=sys.stderr)
        return 2

    kw = {}
    if a.backend in ("sniff", "openarm") and a.can:
        kw["can_interfaces"] = {a.arm: a.can}
    if a.backend == "mock" and a.mass_g is not None:
        kw["content_g"] = a.mass_g  # le mock simule exactement la masse annoncée
    try:
        robot = Robot(a.backend, arms=(a.arm,), control_hz=max(a.hz, 100.0), **kw)
    except RuntimeError as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        return 1

    if a.backend == "mock":
        robot.enable(a.arm)  # simulation : on "tient" le bras pour avoir un couple réaliste
    elif a.hold:
        robot.enable(a.arm)
        print(f">>> {a.arm} armé, position tenue. Ctrl+C pour arrêter (les moteurs RESTENT armés).")
    elif a.backend == "openarm":
        print(">>> lecture seule : moteurs non armés, le couple lu sera ~0.")
    elif a.backend == "sniff":
        print(">>> écoute passive : rien n'est envoyé sur le bus.")

    if a.approach_side:
        if not robot.is_enabled(a.arm):
            print("--approach-side nécessite --hold (bras armé).", file=sys.stderr)
            return 2
        q0 = robot.get_targets(a.arm)
        bump = q0.copy()
        bump[[1, 3]] -= 0.05
        robot.move_joints(a.arm, bump, speed=0.15)
        robot.move_joints(a.arm, q0, speed=0.15)
        time.sleep(0.5)
        print(">>> pose atteinte par le même côté (aller-retour J2/J4 de 0.05 rad)")

    out = Path(a.out) if a.out else HERE / f"data/torque_{datetime.now():%Y%m%d_%H%M%S}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["t", "t_rel", "label", "mass_g"] + [f"{k}_{j}" for k in ("q", "dq", "tau") for j in JOINT_NAMES]

    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))

    n, t0, last_print, last_t = 0, time.time(), 0.0, None
    taus = []
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        period = 1.0 / a.hz
        next_t = time.monotonic()
        while not stop["flag"] and (a.duration <= 0 or time.time() - t0 < a.duration):
            s = robot.get_joint_states(a.arm)
            if s.t != last_t and np.isfinite(s.q).any():  # pas de doublon si aucune trame nouvelle
                last_t = s.t
                row = s.as_row()
                row.update(t_rel=s.t - t0, label=a.label, mass_g="" if a.mass_g is None else a.mass_g)
                w.writerow(row)
                taus.append(s.tau)
                n += 1
            if not a.quiet and time.time() - last_print > 1.0:
                last_print = time.time()
                tau = np.array(taus[-int(a.hz):]) if taus else np.full((1, 8), np.nan)
                print(f"{time.time() - t0:6.1f}s  n={n:6d}  tau moy " +
                      " ".join(f"{v:+6.2f}" for v in np.nanmean(tau, 0)[:7]) +
                      "   std " + " ".join(f"{v:4.2f}" for v in np.nanstd(tau, 0)[:7]))
            next_t += period
            time.sleep(max(0.0, next_t - time.monotonic()))

    robot.close(disable=False)
    print(f">>> {n} échantillons -> {out}")
    if a.backend == "sniff" and n == 0:
        print("    Aucune trame : personne n'interroge les moteurs, ou mauvaise interface (ip -details link show).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
