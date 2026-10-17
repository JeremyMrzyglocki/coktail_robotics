"""Skill "pour" : verser des M&M's d'une bouteille (une couleur) dans le grand verre.

  pour(robot, target_grams=60, container="red", sensor=..., state=...)
  pour(robot, target_grams="all", container="yellow", ...)        # vider la bouteille

Contrat (à respecter par l'orchestrateur) :
  ENTRÉE  : bras verseur ARMÉ, bouteille `container` en main, verticale, au-dessus du
            verre (ou à `approach_pose` du profil). Verre tenu ou posé à position connue.
  SORTIE  : bouteille redressée, bras à la pose neutre, pince INCHANGÉE (la skill ne
            touche jamais à la pince). `state` mis à jour (grammes restants, verre).
  La fonction reçoit l'objet `robot` partagé et n'ouvre aucune connexion.

Contrôles AVANT tout mouvement (bar_state.check_pour) : quantité > reste estimé de la
bouteille, ou > place dans le verre => PourRequestError (rien ne bouge).

États : APPROACH -> WEIGH -> PRE_TILT -> SEEK -> POURING | EMPTYING -> UPRIGHT -> WEIGH -> NEUTRAL
  - PRE_TILT : rapide jusqu'à (dernier angle de départ connu pour cette bouteille - marge),
               sinon jusqu'à pre_tilt_deg du profil ;
  - SEEK     : rampe lente jusqu'à DÉTECTER l'écoulement : le verre gagne des grammes
               (vision) et/ou le couple de pesée décroche de sa ligne de base (couple vs
               inclinaison apprise pendant la rampe, car le CdG bouge même sans flux) ;
               l'angle de départ dépend du remplissage, il n'est jamais supposé ;
  - POURING  : régulation du débit (g/s) par l'inclinaison ; débit réduit près de la cible ;
               arrêt à cible - (débit × latence) pour compter les M&M's encore en vol ;
  - EMPTYING : ("all") inclinaison progressive jusqu'au max, puis attente d'un niveau
               stable pendant empty_stable_s, avec timeout ;
  - UPRIGHT  : retrait rapide de backoff_deg (coupe le flux), puis redressement.
Toute anomalie (timeout, capteur perdu, stop_event, Ctrl+C) mène à UPRIGHT puis NEUTRAL.
L'arrêt d'urgence (bouton physique, ou robot.emergency_stop()) fige le robot sur place.

Sans caméra (`sensor=None`) : versement par impulsions, pesée au couple entre chacune
(nécessite config/torque_calib.json, cf. EXPERIMENT.md).

  python pour_skill.py --backend mock --container red --grams 60
  python pour_skill.py --backend mock --container yellow --grams all
  python pour_skill.py --backend mock --container red --grams 30 --sensor none   # au couple
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from bar_state import ALL, BarConfig, BarState, Container, PourRequestError, load_bar_config
from robot_io import GRIPPER, JOINT_LIMITS, JOINT_NAMES, TAU_LSB, Robot, SafetyStop

log = logging.getLogger("pour")
__all__ = ["pour", "PourConfig", "PourResult", "PourRequestError"]


@dataclass
class PourConfig:
    """Réglages communs à toutes les bouteilles (le spécifique est dans containers.yaml)."""
    arm: str = "right_arm"
    pour_joint: int = 6              # articulation de basculement (0..6) — À VÉRIFIER sur le robot
    tilt_sign: float = 1.0           # +1 / -1 selon le sens qui verse vers le verre
    neutral_pose: list | None = None  # None = retour à la pose de départ
    approach_speed: float = 0.4      # rad/s
    upright_speed_dps: float = 45.0
    backoff_deg: float = 20.0
    onset_margin_deg: float = 8.0    # pré-inclinaison rapide jusqu'à (dernier départ - marge)
    flow_eps_g: float = 3.0          # gain du verre qui signe l'écoulement (~3 M&M's)
    latency_s: float = 0.30          # vol + retard de mesure ; À AJUSTER avec le biais moyen (EXPERIMENT.md)
    lead_min_g: float = 0.5
    tolerance_g: float = 10.0        # succès si |versé - cible| <= tolerance_g
    timeout_s: float = 90.0
    no_flow_timeout_s: float = 40.0
    sensor_stale_s: float = 1.0
    control_dt: float = 0.05
    empty_stable_s: float = 1.5      # "vider" : niveau stable pendant 1.5 s
    empty_stable_g: float = 1.0
    empty_timeout_s: float = 40.0
    # Couple
    weigh_joint: int = 1             # J2 ; remplacé par config/torque_calib.json s'il existe
    weigh_s: float = 1.5
    weigh_bump_rad: float = 0.03     # arrivée à la pose de pesée toujours par le même côté
    torque_calib: str = "config/torque_calib.json"
    torque_flow_k: float = 4.0       # décrochage du couple > k·sigma ...
    torque_flow_hold_s: float = 0.3  # ... pendant au moins 0.3 s
    # Impulsions (sans caméra)
    pulse_hold_s: float = 1.0
    pulse_step_deg: float = 5.0
    max_pulses: int = 20
    log_dir: str = "data"


@dataclass
class PourResult:
    success: bool
    reason: str
    container: str
    target: float | str
    goal_g: float | None             # quantité visée (résout "all")
    poured_g: float | None           # meilleure estimation (vision > couple)
    source: str                      # "vision" | "torque" | "none"
    poured_g_vision: float | None
    poured_g_torque: float | None
    flow_onset_deg: float | None
    onset_by: str | None             # "vision" | "torque"
    max_tilt_deg: float
    duration_s: float
    warnings: list = field(default_factory=list)
    trace_path: str | None = None
    state: dict | None = None        # résumé BarState après versement (pour le LLM)


class _Abort(Exception):
    pass


class TorqueFlowDetector:
    """Détecte l'écoulement par la chute du couple de pesée.

    Pendant la rampe lente (avant écoulement) on apprend tau = a·sin(tilt) + b : le centre
    de gravité qui se déplace fait bouger le couple même sans flux. L'écoulement = couple
    filtré sous cette ligne de base de plus de k·sigma pendant hold_s.
    """

    def __init__(self, k=4.0, hold_s=0.3, lsb=0.026, min_pts=25, filt_n=10):
        self.k, self.hold_s, self.lsb, self.min_pts = k, hold_s, lsb, min_pts
        self.buf: deque[float] = deque(maxlen=filt_n)
        self.pts: list[tuple[float, float]] = []
        self.fit = None
        self.below_since = None

    def _filtered(self, tau):
        self.buf.append(tau)
        return float(np.mean(self.buf))

    def learn(self, tilt_deg, tau):
        self.pts.append((math.sin(math.radians(tilt_deg)), self._filtered(tau)))

    def update(self, tilt_deg, tau, now) -> bool:
        f = self._filtered(tau)
        if self.fit is None:
            if len(self.pts) < self.min_pts:
                self.pts.append((math.sin(math.radians(tilt_deg)), f))
                return False
            x, y = np.array(self.pts).T
            a, b = np.polyfit(x, y, 1) if np.ptp(x) > 1e-3 else (0.0, float(np.mean(y)))
            sigma = max(float(np.std(y - (a * x + b))), self.lsb / 2)
            self.fit = (a, b, sigma)
        a, b, sigma = self.fit
        if f < a * math.sin(math.radians(tilt_deg)) + b - self.k * sigma:
            self.below_since = self.below_since or now
            return now - self.below_since >= self.hold_s
        self.below_since = None
        return False


class _PourRun:
    def __init__(self, robot: Robot, cfg: PourConfig, ctn: Container, sensor, stop_event):
        self.r, self.cfg, self.ctn, self.sensor = robot, cfg, ctn, sensor
        self.stop_event = stop_event or threading.Event()
        self.arm, self.j = cfg.arm, cfg.pour_joint
        self.t0 = time.monotonic()
        self.state = "INIT"
        self.trace: list[dict] = []
        self.added = None              # grammes ajoutés vus par la caméra
        self.last_read_t = time.monotonic()
        self._last_attempt = 0.0
        self.samples: deque[tuple[float, float]] = deque(maxlen=60)  # (t, added) pour le débit
        self.goal = None
        self.calib = self._load_calib()

    def _load_calib(self):
        p = Path(self.cfg.torque_calib)
        if not p.exists():
            return None
        c = json.loads(p.read_text())
        if c.get("from_mock_demo") and self.r.backend_name != "mock":
            log.warning("%s vient de la démo MOCK : refaire la calibration sur le robot", p)
        self.cfg.weigh_joint = JOINT_NAMES.index(c["joint"])
        return c

    # ---- angles ----
    def elapsed(self):
        return time.monotonic() - self.t0

    def tilt_deg(self):
        return math.degrees(self.cfg.tilt_sign * (self.r.get_command(self.arm)[self.j] - self.upright))

    def set_tilt(self, deg, speed_dps):
        q = self.r.get_targets(self.arm)
        q[self.j] = self.upright + self.cfg.tilt_sign * math.radians(deg)
        self.r.set_joint_targets(self.arm, q, speed=math.radians(speed_dps))

    def max_feasible_tilt(self) -> float:
        lo, hi = JOINT_LIMITS[self.arm][self.j]
        room = (hi - self.upright) if self.cfg.tilt_sign > 0 else (self.upright - lo)
        return min(self.ctn.max_tilt_deg, math.degrees(room) - 1.0)

    # ---- mesures ----
    def read(self):
        if self.sensor is None:
            return None
        self._last_attempt = time.monotonic()
        v = self.sensor.read_added_g()
        if v is not None:
            self.added, self.last_read_t = v, time.monotonic()
            self.samples.append((self.last_read_t, v))
        return self.added

    def rate_gps(self, window_s=0.8) -> float:
        if len(self.samples) < 4:
            return 0.0
        t, g = np.array(self.samples).T
        m = t > t[-1] - window_s
        if m.sum() < 4 or np.ptp(t[m]) < 0.2:
            return 0.0
        return max(0.0, float(np.polyfit(t[m], g[m], 1)[0]))

    def tau(self):
        return float(self.r.get_joint_states(self.arm).tau[self.cfg.weigh_joint])

    def record(self, rate=None):
        s = self.r.get_joint_states(self.arm)
        row = {"t_rel": self.elapsed(), "state": self.state, "tilt_deg": self.tilt_deg(),
               "added_g": np.nan if self.added is None else self.added,
               "goal_g": np.nan if self.goal is None else self.goal,
               "rate_gps": np.nan if rate is None else rate,
               "tau_weigh": s.tau[self.cfg.weigh_joint]}
        row.update({f"tau_{n}": v for n, v in zip(JOINT_NAMES[:7], s.tau[:7])})
        self.trace.append(row)

    def tick(self, rate=None):
        if self.sensor is not None and time.monotonic() - self._last_attempt > self.cfg.control_dt / 2:
            self.read()  # garde le capteur frais pendant pesées et attentes
        self.record(rate)
        time.sleep(self.cfg.control_dt)

    def check_abort(self, allow_stale=False):
        if self.stop_event.is_set():
            raise _Abort("stop demandé")
        if self.elapsed() > self.cfg.timeout_s:
            raise _Abort("timeout global")
        if (self.sensor is not None and not allow_stale
                and time.monotonic() - self.last_read_t > self.cfg.sensor_stale_s):
            raise _Abort("capteur du verre perdu")

    # ---- pesée au couple ----
    def weigh(self) -> float:
        """Couple moyen à l'arrêt, en arrivant TOUJOURS du même côté (frottement sec)."""
        prev = self.state
        self.state = "WEIGH"
        if self.cfg.weigh_bump_rad:
            q = self.r.get_targets(self.arm)
            bump = q.copy()
            bump[self.cfg.weigh_joint] -= self.cfg.weigh_bump_rad
            self.r.move_joints(self.arm, bump, speed=0.15)
            self.r.move_joints(self.arm, q, speed=0.15)
        t_end = time.monotonic() + 0.3
        while time.monotonic() < t_end:
            self.tick()
        vals, t_end, last_tick = [], time.monotonic() + self.cfg.weigh_s, 0.0
        while time.monotonic() < t_end:  # échantillonne à ~100 Hz (fréquence d'état du Robot)
            vals.append(self.tau())
            if time.monotonic() - last_tick >= self.cfg.control_dt:
                last_tick = time.monotonic()
                if self.sensor is not None:
                    self.read()
                self.record()
            time.sleep(0.01)
        self.state = prev
        return float(np.mean(vals))

    def grams_from_torque(self, tau_before, tau_after):
        if not self.calib or tau_before is None or tau_after is None:
            return None
        return (tau_before - tau_after) / self.calib["slope_Nm_per_g"]

    def go_upright(self):
        self.state = "UPRIGHT"
        if self.tilt_deg() > 0:
            self.set_tilt(max(self.tilt_deg() - self.cfg.backoff_deg, 0.0), self.cfg.upright_speed_dps * 2)
            self.r.wait_until_reached(self.arm, 3.0, settle_s=0.0)
        self.set_tilt(0.0, self.cfg.upright_speed_dps)
        self.r.wait_until_reached(self.arm, 6.0)


def pour(robot: Robot, target_grams: float | str = 60, container: str | Container = "red",
         sensor=None, state: BarState | None = None, config: PourConfig | None = None,
         bar: BarConfig | None = None, use_torque: bool = True, strict: bool = True,
         stop_event: threading.Event | None = None) -> PourResult:
    """Verse `target_grams` (ou "all") de la bouteille `container` dans le verre.

    sensor : GlassScale / MockGlassSensor (API begin_pour / read_added_g / end_pour), ou None
    state  : BarState partagé ; contrôles de sécurité avant, mise à jour après
    strict : False => si la bouteille n'a pas assez, on verse ce qui reste au lieu de refuser
    Lève PourRequestError (sans bouger) si la demande est refusée.
    """
    cfg = config or PourConfig()
    bar = bar or load_bar_config()
    ctn = container if isinstance(container, Container) else bar.containers[container]
    if not robot.is_enabled(cfg.arm):
        raise RuntimeError(f"{cfg.arm} non armé : la bouteille devrait déjà être tenue (contrat d'entrée)")
    if target_grams != ALL:
        target_grams = float(target_grams)

    # ---- contrôles de sécurité : AVANT tout mouvement ----
    warnings: list[str] = []
    if state is not None:
        chk = state.check_pour(ctn.name, target_grams, strict=strict)
        goal, warnings = chk.grams, list(chk.warnings)
    else:
        goal = ctn.capacity_g if target_grams == ALL else target_grams
        warnings.append("pas de BarState : contenu de la bouteille et place dans le verre non vérifiés")
    emptying = target_grams == ALL

    run = _PourRun(robot, cfg, ctn, sensor, stop_event)
    run.goal = goal
    q_start = robot.get_targets(cfg.arm)
    gripper = q_start[GRIPPER]
    run.upright = q_start[cfg.pour_joint]
    torque_on = use_torque and run.calib is not None
    if use_torque and not torque_on:
        warnings.append("pas de calibration couple (config/torque_calib.json) : pesée désactivée")
    det = TorqueFlowDetector(cfg.torque_flow_k, cfg.torque_flow_hold_s, TAU_LSB[cfg.weigh_joint])
    reason, aborted, interrupted = "ok", False, None
    onset, onset_by, max_tilt, tau0, pulse_g = None, None, 0.0, None, None

    try:
        run.state = "APPROACH"
        if ctn.approach_pose is not None:
            pose = np.array(ctn.approach_pose, float)
            pose[GRIPPER] = gripper  # on ne touche jamais à la pince
            robot.move_joints(cfg.arm, pose, speed=cfg.approach_speed, should_abort=run.stop_event.is_set)
            run.upright = pose[cfg.pour_joint]
        max_eff = run.max_feasible_tilt()
        if emptying and max_eff < 100:
            warnings.append(f"inclinaison max atteignable {max_eff:.0f}° : la bouteille risque de ne pas se vider")
        neck_r = float(np.linalg.norm(ctn.neck_offset_m))
        if torque_on or sensor is None:
            tau0 = run.weigh()
            log.info("pesée initiale : %.3f N·m", tau0)
        if sensor is not None:
            h0 = None
            if state is not None and getattr(sensor, "empty_ref", None) is None and hasattr(sensor, "model"):
                h0 = sensor.model.height(state.glass_g)
            sensor.begin_pour(h0=h0, expected=ctn.name, palette={n: c.hsv for n, c in bar.containers.items()})
            for _ in range(10):
                run.read()
                time.sleep(0.03)
            if run.added is None:
                raise _Abort("capteur du verre muet au démarrage")

        if sensor is None:
            reason, max_tilt, pulse_g = _pulse_pour(run, goal, emptying, tau0, max_eff)
        else:
            # PRE_TILT
            known = state.onset_deg.get(ctn.name) if state is not None else None
            pre = min(max(ctn.pre_tilt_deg, known - cfg.onset_margin_deg) if known else ctn.pre_tilt_deg, max_eff)
            run.state = "PRE_TILT"
            run.set_tilt(pre, cfg.upright_speed_dps)
            while run.tilt_deg() < pre - 0.5:
                run.read()
                run.check_abort()
                run.tick()
            # SEEK : rampe lente jusqu'à détection de l'écoulement
            run.state = "SEEK"
            angle, t_seek = run.tilt_deg(), time.monotonic()
            while onset is None:
                g = run.read()
                run.check_abort()
                now = time.monotonic()
                torque_flow = torque_on and det.update(run.tilt_deg(), run.tau(), now)
                if g >= cfg.flow_eps_g or torque_flow:
                    onset, onset_by = run.tilt_deg(), "vision" if g >= cfg.flow_eps_g else "torque"
                    log.info("écoulement détecté à %.1f° (%s)", onset, onset_by)
                    break
                if now - t_seek > cfg.no_flow_timeout_s:
                    raise _Abort("aucun écoulement détecté (bouteille vide ?)")
                angle = min(angle + ctn.tilt_speed_dps * cfg.control_dt, max_eff)
                run.set_tilt(angle, ctn.tilt_speed_dps * 2)
                max_tilt = max(max_tilt, angle)
                run.tick()
            if state is not None:
                state.onset_deg[ctn.name] = round(onset, 1)
            # POURING (quantité) ou EMPTYING (vider)
            run.state = "EMPTYING" if emptying else "POURING"
            stable_since, last_g, t_phase = None, run.added, time.monotonic()
            last_progress_t = time.monotonic()
            while True:
                g = run.read()
                run.check_abort()
                now = time.monotonic()
                rate = run.rate_gps()
                if emptying:
                    if angle < max_eff:
                        angle = min(angle + ctn.tilt_speed_dps * 1.5 * cfg.control_dt, max_eff)
                    elif g - last_g > cfg.empty_stable_g:
                        stable_since, last_g = None, g
                    else:
                        stable_since = stable_since or now
                        if now - stable_since >= cfg.empty_stable_s:
                            break  # plus rien ne sort
                    if angle < max_eff:
                        last_g = g
                    if now - t_phase > cfg.empty_timeout_s:
                        raise _Abort("timeout vidage")
                else:
                    remaining = goal - g
                    if remaining <= rate * cfg.latency_s + cfg.lead_min_g:
                        break
                    desired = ctn.flow_rate_gps if remaining > 20 else ctn.slow_rate_gps
                    if rate > 0.5:
                        last_progress_t = now
                    if rate < 0.6 * desired:
                        angle = min(angle + ctn.tilt_speed_dps * cfg.control_dt, max_eff)
                    elif rate > 1.4 * desired:
                        angle = max(angle - 0.5 * ctn.tilt_speed_dps * cfg.control_dt, onset - 5)
                    if angle >= max_eff and now - last_progress_t > 3.0:
                        raise _Abort("bouteille vide avant la cible")
                run.set_tilt(angle, ctn.tilt_speed_dps * 2)
                max_tilt = max(max_tilt, angle)
                run.tick(rate)
    except _Abort as e:
        reason, aborted = str(e), True
        log.warning("interruption : %s", reason)
    except SafetyStop as e:
        return PourResult(False, f"arrêt d'urgence : {e}", ctn.name, target_grams, goal, None, "none",
                          run.added, None, onset, onset_by, max_tilt, run.elapsed(), warnings, _save_trace(run))
    except KeyboardInterrupt as e:
        reason, aborted, interrupted = "Ctrl+C", True, e

    # ---- toujours : redresser, mesurer, peser, neutre ----
    vision_g = torque_g = None
    try:
        run.go_upright()
        if sensor is not None:
            t_end = time.monotonic() + 0.8  # laisser retomber les M&M's en vol
            while time.monotonic() < t_end:
                run.tick()
            final = sensor.end_pour()
            vision_g = float(final["added_g"])
            col = final.get("color") or {}
            if col.get("ok") is False:
                warnings.append(f"couleur de la nouvelle couche = {col.get('best')} au lieu de {ctn.name} : mauvaise bouteille ?")
            if not final.get("calibrated", True):
                warnings.append("verre non calibré hauteur->grammes : grammes approximatifs")
        if tau0 is not None:
            torque_g = pulse_g if pulse_g is not None else run.grams_from_torque(tau0, run.weigh())
        run.state = "NEUTRAL"
        neutral = np.array(cfg.neutral_pose if cfg.neutral_pose is not None else q_start, float)
        neutral[GRIPPER] = gripper
        robot.move_joints(cfg.arm, neutral, speed=cfg.approach_speed)
        run.state = "DONE"
        run.record()
    except SafetyStop as e:
        reason, aborted = f"arrêt d'urgence pendant le retour : {e}", True

    poured, source = (vision_g, "vision") if vision_g is not None else \
        (torque_g, "torque") if torque_g is not None else (None, "none")
    if poured is None and onset is None and not aborted:
        poured = 0.0
    if state is not None and poured is not None:
        state.record_pour(ctn.name, poured, source=source, target=target_grams,
                          vision_g=vision_g, torque_g=torque_g, reason=reason)
    if emptying:
        success = not aborted and poured is not None
    else:
        success = not aborted and poured is not None and abs(poured - goal) <= cfg.tolerance_g
    trace = _save_trace(run)
    if interrupted:
        raise interrupted
    for w in warnings:
        log.warning(w)
    return PourResult(success, reason, ctn.name, target_grams, goal, poured, source, vision_g, torque_g,
                      onset, onset_by, max_tilt, run.elapsed(), warnings, trace,
                      state.summary(bar) if state is not None else None)


def _pulse_pour(run: _PourRun, goal: float, emptying: bool, tau0: float | None, max_eff: float):
    """Sans caméra : impulsions courtes, pesée au couple entre chacune. La pesée suit
    toujours un redressement + petit aller-retour de l'articulation de pesée, donc on arrive
    à la pose de mesure par le même côté : l'hystérésis du frottement reste constante."""
    cfg, ctn = run.cfg, run.ctn
    if not run.calib or tau0 is None:
        raise _Abort("sans caméra il faut la calibration couple (EXPERIMENT.md, test 1)")
    angle = max_eff if emptying else min(ctn.pre_tilt_deg + 10, max_eff)
    poured, max_tilt, dry = 0.0, 0.0, 0
    for i in range(cfg.max_pulses):
        remaining = goal - poured
        if not emptying and remaining <= max(3.0, 0.1 * goal):
            return "ok", max_tilt, poured
        run.state = f"PULSE_{i + 1}"
        run.set_tilt(angle, ctn.tilt_speed_dps * 4)
        while run.tilt_deg() < angle - 0.5:
            run.check_abort(allow_stale=True)
            run.tick()
        hold = cfg.pulse_hold_s * (2.0 if emptying else min(1.0, remaining / max(goal, 1e-6) + 0.3))
        t_end = time.monotonic() + hold
        while time.monotonic() < t_end:
            run.check_abort(allow_stale=True)
            run.tick()
        max_tilt = max(max_tilt, angle)
        run.go_upright()
        before = poured
        poured = run.grams_from_torque(tau0, run.weigh())
        log.info("impulsion %d à %.0f° : %.1f g versés au total", i + 1, angle, poured)
        if poured - before < 3.0:
            dry += 1
            if emptying and dry >= 2:
                return "ok", max_tilt, poured  # plus rien ne sort
            angle = min(angle + cfg.pulse_step_deg, max_eff)
        else:
            dry = 0
    return "nombre max d'impulsions atteint", max_tilt, poured


def _save_trace(run: _PourRun) -> str | None:
    if not run.trace:
        return None
    import pandas as pd

    p = Path(run.cfg.log_dir) / f"pour_{run.ctn.name}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(run.trace).to_csv(p, index=False)
    return str(p)


def main() -> int:
    from glass_level import GlassScale, MockGlassSensor

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", choices=["mock", "openarm"], default="mock")
    p.add_argument("--container", default="red")
    p.add_argument("--grams", default="60", help='grammes, ou "all" pour vider')
    p.add_argument("--sensor", choices=["mock", "camera", "none"], default=None)
    p.add_argument("--camera", default="0")
    p.add_argument("--no-torque", action="store_true")
    p.add_argument("--no-strict", action="store_true", help="verser ce qui reste si la bouteille n'a pas assez")
    p.add_argument("--state", choices=["fresh", "load"], default="fresh",
                   help="fresh = bouteilles pleines/verre vide ; load = state/bar_state.json")
    p.add_argument("--config", type=Path, default=None, help="JSON surchargeant PourConfig")
    p.add_argument("--i-understand-motors-will-be-armed", dest="confirm", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    cfg = PourConfig(**json.loads(a.config.read_text())) if a.config else PourConfig()
    if a.backend == "openarm" and not a.confirm:
        print("Le vrai robot va être armé et va bouger. Ajoute --i-understand-motors-will-be-armed.")
        return 2
    bar = load_bar_config()
    state = BarState.load_or_fresh(bar) if a.state == "load" else BarState.fresh(bar)
    sensor_kind = a.sensor or ("mock" if a.backend == "mock" else "camera")

    kw = dict(pour_joint=cfg.pour_joint, tilt_sign=cfg.tilt_sign,
              bottles=dict(state.remaining_g), glass_capacity_g=bar.glass_capacity_g) if a.backend == "mock" else {}
    robot = Robot(a.backend, arms=(cfg.arm,), **kw)
    try:
        robot.enable(cfg.arm)  # tient la pose actuelle, aucun mouvement
        if a.backend == "mock":
            robot.backend.attach_bottle(a.container)
        sensor = {"mock": lambda: MockGlassSensor(robot),
                  "camera": lambda: GlassScale(camera=int(a.camera) if a.camera.isdigit() else a.camera),
                  "none": lambda: None}[sensor_kind]()
        try:
            res = pour(robot, a.grams, a.container, sensor=sensor, state=state, config=cfg, bar=bar,
                       use_torque=not a.no_torque, strict=not a.no_strict)
        except PourRequestError as e:
            print(f"REFUSÉ (aucun mouvement) : {e}")
            return 3
        print(json.dumps(asdict(res), indent=2, ensure_ascii=False, default=float))
        if a.backend == "mock":
            print(f"(vérité mock : verre {robot.backend.glass_grams():.1f} g, "
                  f"bouteille {a.container} {robot.backend.bottle_g(a.container):.1f} g)")
        if res.trace_path:
            print(f"Figure : python analyze_torque.py --pour {res.trace_path}")
        return 0 if res.success else 1
    finally:
        robot.close(disable=False)


if __name__ == "__main__":
    raise SystemExit(main())
