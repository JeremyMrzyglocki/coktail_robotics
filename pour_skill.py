"""Skill "pour" : verser du riz / des bonbons dans un verre, en boucle fermée.

Contrat (à respecter par l'orchestrateur) :
  ENTRÉE  : bras verseur ARMÉ, bouteille en main, verticale, au-dessus du verre
            ou à une pose d'approche connue (`approach_pose`). Le verre est tenu
            par l'autre bras (ou posé) à une position fixe et connue.
  SORTIE  : bouteille redressée, bras verseur à la pose neutre, pince INCHANGÉE
            (la skill ne touche jamais à la pince : la bouteille reste en main).
  La fonction reçoit l'objet `robot` partagé et n'ouvre aucune connexion.

États : APPROACH -> PRE_TILT -> SLOW_TILT -> POURING -> UPRIGHT -> NEUTRAL -> DONE
  - PRE_TILT  : inclinaison rapide jusqu'à un angle où rien ne coule encore ;
  - SLOW_TILT : rampe lente jusqu'à détecter que le niveau monte (début de flux) ;
  - POURING   : on tient l'angle, on ne ré-incline que si le flux s'arrête ;
                stop quand niveau >= cible - `lead` (le riz en vol + l'avalanche) ;
  - UPRIGHT   : retrait rapide de `backoff_deg` pour couper le flux, puis redressement.
Toute anomalie (timeout, capteur perdu, stop_event, Ctrl+C) mène à UPRIGHT puis
NEUTRAL : on ne laisse jamais une bouteille penchée. L'arrêt d'urgence (bouton
physique, ou robot.emergency_stop()) fige le robot sur place.

Mode "au poids" sans caméra (`sensor=None, target_grams=...`) : versement par
impulsions (incliner, tenir, redresser, peser au couple, recommencer).

  python pour_skill.py --backend mock --target 0.5            # simulation
  python pour_skill.py --backend mock --torque                # + pesée au couple
  python pour_skill.py --backend mock --grams 60              # au poids, sans caméra
  python pour_skill.py --backend openarm --sensor camera --i-understand-motors-will-be-armed
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from robot_io import GRIPPER, JOINT_NAMES, Robot, SafetyStop

log = logging.getLogger("pour")


@dataclass
class PourConfig:
    arm: str = "right_arm"           # bras qui tient la bouteille
    pour_joint: int = 6              # articulation de basculement (index 0..6) — À VÉRIFIER sur le robot
    tilt_sign: float = 1.0           # +1 ou -1 selon le sens qui fait verser vers le verre
    approach_pose: list | None = None  # 8 valeurs (rad) au-dessus du verre ; None = on ne bouge pas
    neutral_pose: list | None = None   # None = retour à la pose de départ
    approach_speed: float = 0.4      # rad/s
    pre_tilt_deg: float = 30.0       # rapide jusqu'ici (aucun écoulement attendu)
    max_tilt_deg: float = 85.0
    tilt_speed_dps: float = 3.0      # rampe lente : le riz part d'un coup
    upright_speed_dps: float = 45.0
    backoff_deg: float = 15.0        # retrait immédiat à l'arrêt pour couper le flux
    flow_eps: float = 0.02           # hausse de niveau qui signe le début du flux
    stall_s: float = 2.0             # flux arrêté depuis stall_s -> on ré-incline
    lead: float = 0.04               # on arrête à cible - lead (anticipation)
    tolerance: float = 0.08          # |final - cible| <= tolerance => succès
    timeout_s: float = 60.0
    no_flow_timeout_s: float = 30.0
    sensor_stale_s: float = 1.0
    control_dt: float = 0.05
    # Couple
    weigh_joint: int = 1             # J2 par défaut ; remplacé par config/torque_calib.json s'il existe
    weigh_s: float = 1.5
    torque_calib: str = "config/torque_calib.json"
    # Mode impulsions (au poids)
    pulse_hold_s: float = 1.0
    pulse_step_deg: float = 5.0
    max_pulses: int = 15
    log_dir: str = "data"


@dataclass
class PourResult:
    success: bool
    reason: str
    amount: float | None          # niveau final mesuré (fraction) ; None en mode au poids
    target: float | None
    poured_g_torque: float | None  # estimation par le couple (si activée)
    flow_onset_deg: float | None
    max_tilt_deg: float
    duration_s: float
    trace_path: str | None = None
    extra: dict = field(default_factory=dict)


class _Abort(Exception):
    pass


class _PourRun:
    def __init__(self, robot: Robot, cfg: PourConfig, sensor, stop_event):
        self.r, self.cfg, self.sensor = robot, cfg, sensor
        self.stop_event = stop_event or threading.Event()
        self.arm, self.j = cfg.arm, cfg.pour_joint
        self.t0 = time.monotonic()
        self.state = "INIT"
        self.trace: list[dict] = []
        self.level = None
        self.last_level_t = time.monotonic()
        self.calib = self._load_calib()

    # ---- utilitaires ----
    def _load_calib(self):
        p = Path(self.cfg.torque_calib)
        if p.exists():
            c = json.loads(p.read_text())
            if c.get("from_mock_demo") and self.r.backend_name != "mock":
                log.warning("%s vient de la démo MOCK : refaire la calibration sur le robot", p)
            self.cfg.weigh_joint = JOINT_NAMES.index(c["joint"])
            return c
        return None

    def elapsed(self):
        return time.monotonic() - self.t0

    def tilt_deg(self):
        q = self.r.get_command(self.arm)[self.j]
        return math.degrees(self.cfg.tilt_sign * (q - self.upright))

    def set_tilt(self, deg, speed_dps):
        q = self.r.get_targets(self.arm)
        q[self.j] = self.upright + self.cfg.tilt_sign * math.radians(deg)
        self.r.set_joint_targets(self.arm, q, speed=math.radians(speed_dps))

    def read_level(self):
        if self.sensor is None:
            return None
        self._last_read_attempt = time.monotonic()
        v = self.sensor.read()
        if v is not None:
            self.level, self.last_level_t = v, time.monotonic()
        return self.level

    def record(self, target=None):
        s = self.r.get_joint_states(self.arm)
        row = {"t_rel": self.elapsed(), "state": self.state, "tilt_deg": self.tilt_deg(),
               "fill": self.level if self.level is not None else np.nan,
               "target": target if target is not None else np.nan,
               "tau_weigh": s.tau[self.cfg.weigh_joint]}
        row.update({f"tau_{n}": v for n, v in zip(JOINT_NAMES[:7], s.tau[:7])})
        self.trace.append(row)

    def check_abort(self, allow_stale=False):
        if self.stop_event.is_set():
            raise _Abort("stop demandé")
        if self.elapsed() > self.cfg.timeout_s:
            raise _Abort("timeout global")
        if (self.sensor is not None and not allow_stale
                and time.monotonic() - self.last_level_t > self.cfg.sensor_stale_s):
            raise _Abort("capteur de niveau perdu")

    def sleep_tick(self, target=None):
        # garde le capteur "frais" aussi pendant les pesées et les attentes
        if time.monotonic() - getattr(self, "_last_read_attempt", 0.0) > self.cfg.control_dt / 2:
            self.read_level()
        self.record(target)
        time.sleep(self.cfg.control_dt)

    def weigh(self) -> float:
        """Couple moyen à l'arrêt sur l'articulation de pesée (N·m)."""
        time.sleep(0.3)
        vals, t_end = [], time.monotonic() + self.cfg.weigh_s
        while time.monotonic() < t_end:
            vals.append(self.r.get_joint_states(self.arm).tau[self.cfg.weigh_joint])
            self.sleep_tick()
        return float(np.mean(vals))

    def grams(self, tau_before, tau_after):
        if not self.calib:
            return None
        return (tau_before - tau_after) / self.calib["slope_Nm_per_g"]

    def go_upright(self, fast_first=True):
        self.state = "UPRIGHT"
        if fast_first and self.tilt_deg() > 0:
            self.set_tilt(max(self.tilt_deg() - self.cfg.backoff_deg, 0.0), self.cfg.upright_speed_dps * 2)
            self.r.wait_until_reached(self.arm, 3.0, settle_s=0.0)
        self.set_tilt(0.0, self.cfg.upright_speed_dps)
        self.r.wait_until_reached(self.arm, 5.0)


def pour(robot: Robot, target_amount: float = 0.5, sensor=None, config: PourConfig | None = None,
         use_torque: bool = False, target_grams: float | None = None,
         stop_event: threading.Event | None = None) -> PourResult:
    """Verse jusqu'à `target_amount` (fraction de la hauteur du verre, vue par `sensor`).

    sensor       : objet avec .read() -> float | None (GlassLevelSensor, MockGlassSensor)
    use_torque   : pèse la bouteille au couple avant/après (estimation des grammes versés)
    target_grams : sans capteur, versement "au poids" par impulsions (nécessite la calibration couple)
    stop_event   : threading.Event levé par l'orchestrateur/UI pour interrompre proprement
    """
    cfg = config or PourConfig()
    if not robot.is_enabled(cfg.arm):
        raise RuntimeError(f"{cfg.arm} non armé : la bouteille devrait déjà être tenue (contrat d'entrée)")
    if sensor is None and target_grams is None:
        raise ValueError("il faut un capteur de niveau, ou target_grams (mode au poids)")

    run = _PourRun(robot, cfg, sensor, stop_event)
    q_start = robot.get_targets(cfg.arm)
    gripper = q_start[GRIPPER]
    run.upright = q_start[cfg.pour_joint]
    reason, flow_onset, max_tilt, tau0, poured_g = "ok", None, 0.0, None, None
    aborted = False
    interrupted = None

    try:
        # APPROACH
        run.state = "APPROACH"
        if cfg.approach_pose is not None:
            pose = np.array(cfg.approach_pose, float)
            pose[GRIPPER] = gripper  # on ne touche jamais à la pince
            robot.move_joints(cfg.arm, pose, speed=cfg.approach_speed, should_abort=run.stop_event.is_set)
            run.upright = pose[cfg.pour_joint]
        if sensor is not None:
            sensor.reset()
            for _ in range(10):
                run.read_level()
                time.sleep(0.03)
            if run.level is None:
                raise _Abort("capteur de niveau muet au démarrage")
        if use_torque or target_grams is not None:
            tau0 = run.weigh()
            log.info("pesée initiale : %.3f N·m", tau0)

        if sensor is None:
            reason, max_tilt, poured_g = _pulse_pour(run, target_grams, tau0)
        else:
            level0 = run.level
            if level0 >= target_amount - cfg.lead:
                raise _Abort("verre déjà au niveau cible")
            # PRE_TILT
            run.state = "PRE_TILT"
            run.set_tilt(cfg.pre_tilt_deg, cfg.upright_speed_dps)
            while run.tilt_deg() < cfg.pre_tilt_deg - 0.5:
                run.read_level()
                run.check_abort()
                run.sleep_tick(target_amount)
            # SLOW_TILT puis POURING
            run.state = "SLOW_TILT"
            angle = run.tilt_deg()
            last_progress_t, last_progress_level = time.monotonic(), level0
            t_tilt_start = time.monotonic()
            while True:
                lv = run.read_level()
                run.check_abort()
                now = time.monotonic()
                if lv >= target_amount - cfg.lead:
                    break
                if run.state == "SLOW_TILT":
                    if lv - level0 > cfg.flow_eps:
                        run.state, flow_onset = "POURING", run.tilt_deg()
                        last_progress_t, last_progress_level = now, lv
                        log.info("début du flux à %.1f°", flow_onset)
                    elif now - t_tilt_start > cfg.no_flow_timeout_s:
                        raise _Abort("aucun écoulement détecté")
                    else:
                        angle += cfg.tilt_speed_dps * cfg.control_dt
                else:  # POURING
                    if lv > last_progress_level + 0.005:
                        last_progress_t, last_progress_level = now, lv
                    elif now - last_progress_t > cfg.stall_s:
                        angle += cfg.tilt_speed_dps * cfg.control_dt  # flux tari : on ré-incline doucement
                if angle >= cfg.max_tilt_deg:
                    angle = cfg.max_tilt_deg
                    if now - last_progress_t > cfg.stall_s * 3:
                        raise _Abort("inclinaison max sans flux (bouteille vide ?)")
                run.set_tilt(angle, cfg.tilt_speed_dps * 2)
                max_tilt = max(max_tilt, angle)
                run.sleep_tick(target_amount)
    except _Abort as e:
        reason, aborted = str(e), True
        log.warning("interruption : %s", reason)
    except SafetyStop as e:
        return PourResult(False, f"arrêt d'urgence : {e}", run.level, target_amount, None,
                          flow_onset, max_tilt, run.elapsed(), _save_trace(run))
    except KeyboardInterrupt as e:
        reason, aborted, interrupted = "Ctrl+C", True, e

    # Toujours : redresser, peser, neutre.
    try:
        run.go_upright()
        if sensor is not None:
            t_end = time.monotonic() + 0.8  # laisser retomber le riz en vol
            while time.monotonic() < t_end:
                run.read_level()
                run.sleep_tick(target_amount)
        if tau0 is not None and target_grams is None:
            poured_g = run.grams(tau0, run.weigh())
        run.state = "NEUTRAL"
        neutral = np.array(cfg.neutral_pose if cfg.neutral_pose is not None else q_start, float)
        neutral[GRIPPER] = gripper
        robot.move_joints(cfg.arm, neutral, speed=cfg.approach_speed)
        run.state = "DONE"
        run.record(target_amount)
    except SafetyStop as e:
        reason, aborted = f"arrêt d'urgence pendant le retour : {e}", True

    trace = _save_trace(run)
    if interrupted:
        raise interrupted
    if sensor is not None:
        amount = run.level
        success = not aborted and amount is not None and abs(amount - target_amount) <= cfg.tolerance
        extra = {"error": None if amount is None else amount - target_amount}
    else:
        amount = None
        success = not aborted and poured_g is not None and abs(poured_g - target_grams) <= max(5.0, 0.15 * target_grams)
        extra = {"target_grams": target_grams}
    return PourResult(success, reason, amount, target_amount if sensor is not None else None, poured_g,
                      flow_onset, max_tilt, run.elapsed(), trace, extra)


def _pulse_pour(run: _PourRun, target_grams: float, tau0: float):
    """Au poids : impulsions courtes, pesée entre chaque. La pesée se fait
    toujours après un redressement, donc on arrive à la pose de mesure par le
    même côté : l'hystérésis du frottement reste constante."""
    cfg = run.cfg
    if not run.calib:
        raise _Abort("mode au poids : lancer d'abord analyze_torque.py (config/torque_calib.json)")
    angle, poured, max_tilt = cfg.pre_tilt_deg + 10, 0.0, 0.0
    for i in range(cfg.max_pulses):
        remaining = target_grams - poured
        if remaining <= max(3.0, 0.1 * target_grams):
            return "ok", max_tilt, poured
        run.state = f"PULSE_{i + 1}"
        run.set_tilt(angle, cfg.tilt_speed_dps * 4)
        while run.tilt_deg() < angle - 0.5:
            run.check_abort(allow_stale=True)
            run.sleep_tick()
        hold = cfg.pulse_hold_s * min(1.0, remaining / max(target_grams, 1e-6) + 0.3)
        t_end = time.monotonic() + hold
        while time.monotonic() < t_end:
            run.check_abort(allow_stale=True)
            run.sleep_tick()
        max_tilt = max(max_tilt, angle)
        run.go_upright()
        before = poured
        poured = run.grams(tau0, run.weigh())
        log.info("impulsion %d à %.0f° : %.1f g versés au total", i + 1, angle, poured)
        if poured - before < 3.0:
            angle = min(angle + cfg.pulse_step_deg, cfg.max_tilt_deg)  # rien n'est sorti : plus fort
    return "nombre max d'impulsions atteint", max_tilt, poured


def _save_trace(run: _PourRun) -> str | None:
    if not run.trace:
        return None
    import pandas as pd

    p = Path(run.cfg.log_dir) / f"pour_{datetime.now():%Y%m%d_%H%M%S}.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(run.trace).to_csv(p, index=False)
    return str(p)


def main() -> int:
    from glass_level import GlassLevelSensor, MockGlassSensor

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", choices=["mock", "openarm"], default="mock")
    p.add_argument("--target", type=float, default=0.5, help="niveau cible (fraction de la zone)")
    p.add_argument("--sensor", choices=["mock", "camera", "none"], default=None)
    p.add_argument("--camera", default="0")
    p.add_argument("--torque", action="store_true", help="pesée au couple avant/après")
    p.add_argument("--grams", type=float, default=None, help="mode au poids (sans caméra)")
    p.add_argument("--config", type=Path, default=None, help="JSON surchargeant PourConfig")
    p.add_argument("--i-understand-motors-will-be-armed", dest="confirm", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    cfg = PourConfig(**json.loads(a.config.read_text())) if a.config else PourConfig()
    if a.backend == "openarm" and not a.confirm:
        print("Le vrai robot va être armé et va bouger. Ajoute --i-understand-motors-will-be-armed.")
        return 2
    sensor_kind = a.sensor or ("none" if a.grams else ("mock" if a.backend == "mock" else "camera"))

    robot = Robot(a.backend, arms=(cfg.arm,), pour_joint=cfg.pour_joint, tilt_sign=cfg.tilt_sign) \
        if a.backend == "mock" else Robot(a.backend, arms=(cfg.arm,))
    try:
        robot.enable(cfg.arm)  # tient la pose actuelle, aucun mouvement
        sensor = {"mock": lambda: MockGlassSensor(robot),
                  "camera": lambda: GlassLevelSensor(camera=int(a.camera) if a.camera.isdigit() else a.camera),
                  "none": lambda: None}[sensor_kind]()
        res = pour(robot, target_amount=a.target, sensor=sensor, config=cfg,
                   use_torque=a.torque, target_grams=a.grams)
        print(json.dumps(asdict(res), indent=2, ensure_ascii=False, default=float))
        if a.backend == "mock":
            print(f"(vérité mock : {robot.backend.poured_g():.1f} g versés, "
                  f"verre {robot.backend.glass_fill() * 100:.1f} %)")
        if res.trace_path:
            print(f"Figure : python analyze_torque.py --pour {res.trace_path}")
        return 0 if res.success else 1
    finally:
        robot.close(disable=False)


if __name__ == "__main__":
    raise SystemExit(main())
