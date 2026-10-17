"""Couche d'abstraction robot partagée par toutes les skills.

Une seule instance de `Robot` par processus : l'orchestrateur la crée, puis la
passe à chaque skill (`pick_and_place(robot, ...)`, `pour(robot, ...)`). Les
skills ne parlent jamais au CAN directement.

Backends :
  - "mock"    : simulation (macOS OK). Gravité, bruit et quantification des
                moteurs Damiao, bouteilles de M&M's (une couleur chacune) qui se
                vident dans un même verre quand on les incline.
  - "openarm" : vrai robot via openarm_driver (Linux + SocketCAN). Lecture seule
                par défaut ; `enable=True` pour arme les moteurs et commander.
  - "sniff"   : écoute PASSIVE du bus CAN (socket brut, stdlib Python). N'envoie
                aucune trame. Sert à logger le couple pendant que quelqu'un
                d'autre (la téléop) pilote le bras.

Conventions : 8 articulations par bras, index 0..6 = J1..J7, index 7 = pince.
Positions en rad (offsets de la config déjà soustraits), couples en N·m.
"""

from __future__ import annotations

import logging
import math
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("robot_io")

ARMS = ("right_arm", "left_arm")
N_JOINTS = 8
GRIPPER = 7
JOINT_NAMES = [f"J{i}" for i in range(1, 8)] + ["gripper"]

# Recopié de vendor/openarm_can/include/openarm/damiao_motor/dm_motor_constants.hpp
# (pMax rad, vMax rad/s, tMax N·m). Le couple est codé sur 12 bits dans [-tMax, tMax].
MOTOR_LIMITS = {
    "DM8009": (12.5, 45.0, 54.0),
    "DM4340": (12.5, 10.0, 28.0),
    "DM4310": (12.5, 30.0, 10.0),
}
MOTOR_TYPES = ["DM8009", "DM8009", "DM4340", "DM4340", "DM4310", "DM4310", "DM4310", "DM4310"]
TAU_LSB = np.array([2 * MOTOR_LIMITS[t][2] / 4095 for t in MOTOR_TYPES])  # N·m par pas

# Recopié de vendor/openarm_driver/src/openarm_driver/configs/openarm_cell.yaml
DEFAULT_CAN = {"right_arm": "can0", "left_arm": "can1"}
RECV_IDS = list(range(0x11, 0x19))
JOINT_OFFSETS = {
    "right_arm": np.array([0.0, -0.506145, 1.570796, -1.745329, 0.0, 0.331612, -1.570796, 0.0]),
    "left_arm": np.array([0.0, 0.506145, -1.570796, -1.745329, 0.0, -0.331612, 1.570796, 0.0]),
}
JOINT_LIMITS = {
    "right_arm": np.array([[-1.3963, 2.0], [-0.17453, 2.0], [-1.5708, 1.5708], [0.0, 2.4435],
                           [-1.5708, 1.5708], [-0.7854, 0.7854], [-1.5708, 1.5708], [-1.0472, 0.4]]),
    "left_arm": np.array([[-2.0, 1.3963], [-2.0, 0.17453], [-1.5708, 1.5708], [0.0, 2.4435],
                          [-1.5708, 1.5708], [-0.7854, 0.7854], [-1.5708, 1.5708], [-0.4, 1.0472]]),
}
VEL_LIMITS = np.array([2.0, 2.0, 3.3, 3.3, 6.3, 6.3, 6.3, 20.0])  # rad/s


@dataclass
class JointStates:
    t: float               # time.time()
    q: np.ndarray          # positions (rad)
    dq: np.ndarray         # vitesses (rad/s)
    tau: np.ndarray        # couples estimés par le moteur (N·m)
    temp_mos: np.ndarray   # température MOSFET (°C)

    def as_row(self) -> dict:
        row = {"t": self.t}
        for name, arr in (("q", self.q), ("dq", self.dq), ("tau", self.tau)):
            for j, v in zip(JOINT_NAMES, arr):
                row[f"{name}_{j}"] = float(v)
        return row


class ReadOnlyError(RuntimeError):
    """Commande refusée : backend ou bras en lecture seule."""


class SafetyStop(RuntimeError):
    """Arrêt d'urgence logiciel actif, ou arrêt de sécurité du driver."""


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #

class MockBackend:
    """Simulation simple mais "honnête" sur ce qui compte pour le couple et le versement.

    Reproduit volontairement :
      - quantification 12 bits du couple par type de moteur ;
      - bruit blanc + frottement sec avec hystérésis (le couple statique dépend
        du sens d'arrivée : c'est LE piège de la pesée par le couple) ;
      - le centre de gravité de la bouteille qui se décale quand elle penche
        (le couple bouge même sans écoulement) ;
      - M&M's : plusieurs bouteilles d'une couleur chacune, une seule en main ;
        rien ne sort sous un angle critique qui augmente quand la bouteille se
        vide (≈45° pleine, ≈105° vide), puis un débit régulier qui croît avec
        l'inclinaison, par billes de 0.9 g ; ~0.25 s de vol jusqu'au verre ;
      - un seul verre où les couches de couleurs s'empilent.
    """

    read_only = False
    G = 9.81
    DEFAULT_BOTTLES = {"red": 120.0, "yellow": 120.0, "blue": 120.0}

    def __init__(self, arms=ARMS, seed=0, bottles=None, empty_mass_g=40.0, bottle_capacity_g=120.0,
                 glass_capacity_g=300.0, mm_unit_g=0.9, pour_arm="right_arm", pour_joint=6,
                 tilt_sign=1.0, upright_angle=-0.6, content_g=None, **_ignored):
        self.rng = np.random.default_rng(seed)
        self.arms = tuple(arms)
        self.lock = threading.Lock()
        home = np.array([0.0, 0.25, 0.0, 1.3, 0.0, 0.0, 0.0, -0.3])
        home[pour_joint] = upright_angle
        self.q = {a: home.copy() for a in self.arms}
        self.dq = {a: np.zeros(N_JOINTS) for a in self.arms}
        self.cmd = {a: home.copy() for a in self.arms}
        self.enabled = {a: False for a in self.arms}
        self.fric_sign = {a: np.ones(N_JOINTS) for a in self.arms}
        self.t_last = time.monotonic()
        self.pour_arm, self.pour_joint, self.tilt_sign = pour_arm, pour_joint, tilt_sign
        self.upright_angle = upright_angle
        # Bouteilles : couleur -> contenu (kg). content_g : une seule bouteille "test" en main.
        bottles = dict(self.DEFAULT_BOTTLES if bottles is None else bottles)
        if content_g is not None:
            bottles = {"test": content_g}
        self.content_kg = {c: g / 1000 for c, g in bottles.items()}
        self.empty_kg = empty_mass_g / 1000
        self.capacity_kg = bottle_capacity_g / 1000
        self.onset_offset = {c: self.rng.normal(0, 3) for c in bottles}  # formes différentes
        self.attached: str | None = "test" if content_g is not None else None
        self.unit_kg = mm_unit_g / 1000
        self.glass_capacity_kg = glass_capacity_g / 1000
        self.glass_layers: list[list] = []  # [[couleur, kg], ...] du fond vers le haut
        self.in_flight: list[tuple[float, str, float]] = []
        # Paramètres "physiques" (ordres de grandeur, pas une identification)
        self.lever_m = np.array([0.0, 0.40, 0.0, 0.22, 0.0, 0.0, 0.0, 0.0])
        self.arm_tau = np.array([0.0, 6.0, 0.3, 2.5, 0.05, 0.3, 0.05, 0.0])
        self.noise = np.array([0.06, 0.06, 0.04, 0.05, 0.015, 0.015, 0.015, 0.01])
        self.fric = np.array([0.15, 0.15, 0.35, 0.35, 0.05, 0.05, 0.05, 0.02])
        self.com_offset_m = 0.06   # CdG de la bouteille / axe de basculement (poignet)
        self.com_shift_j2_m = 0.02  # décalage horizontal du CdG vu par J2 quand on penche

    # -- API mock spécifique (capteurs simulés, vérité terrain) --
    def attach_bottle(self, color: str | None):
        """Simule le résultat du pick : `color` est maintenant dans la pince (None = pince vide)."""
        with self.lock:
            if color is not None and color not in self.content_kg:
                raise KeyError(color)
            self.attached = color

    def bottle_g(self, color: str) -> float:
        with self.lock:
            return self.content_kg[color] * 1000

    def set_bottle(self, color: str, content_g: float):
        with self.lock:
            self.content_kg[color] = content_g / 1000

    def glass_grams(self) -> float:
        with self.lock:
            self._step()
            return sum(kg for _, kg in self.glass_layers) * 1000

    def glass_fill(self) -> float:
        return self.glass_grams() / (self.glass_capacity_kg * 1000)

    def glass_layers_g(self) -> list[tuple[str, float]]:
        with self.lock:
            return [(c, kg * 1000) for c, kg in self.glass_layers]

    def empty_glass(self):
        with self.lock:
            self.glass_layers, self.in_flight = [], []

    # -- interface backend --
    def enable(self, arm):
        with self.lock:
            self._step()
            self.enabled[arm] = True
            self.cmd[arm] = self.q[arm].copy()

    def disable(self, arm):
        with self.lock:
            self.enabled[arm] = False

    def command(self, arm, q_cmd):
        with self.lock:
            if not self.enabled[arm]:
                raise ReadOnlyError(f"{arm} non armé")
            self.cmd[arm] = np.clip(q_cmd, JOINT_LIMITS[arm][:, 0], JOINT_LIMITS[arm][:, 1])
            self._step()

    def read(self, arm) -> JointStates:
        with self.lock:
            self._step()
            return JointStates(time.time(), self.q[arm].copy(), self.dq[arm].copy(),
                               self._torque(arm), np.full(N_JOINTS, 35))

    def close(self):
        pass

    # -- simulation --
    def _step(self):
        now = time.monotonic()
        dt = min(now - self.t_last, 0.05)
        self.t_last = now
        if dt <= 0:
            return
        for a in self.arms:
            if self.enabled[a]:
                alpha = 1 - math.exp(-dt / 0.04)  # suivi 1er ordre ~40 ms
                q_new = self.q[a] + alpha * (self.cmd[a] - self.q[a])
                self.dq[a] = (q_new - self.q[a]) / dt
                moving = np.abs(self.dq[a]) > 1e-3
                self.fric_sign[a][moving] = np.sign(self.dq[a][moving])
                self.q[a] = q_new
            else:
                self.dq[a][:] = 0.0
        self._flow(now, dt)

    def _tilt(self) -> float:
        a = self.pour_arm
        return self.tilt_sign * (self.q[a][self.pour_joint] - self.upright_angle) if a in self.q else 0.0

    def _flow(self, now, dt):
        c = self.attached
        if c is not None and self.content_kg[c] > 0:
            tilt = math.degrees(self._tilt())
            frac = self.content_kg[c] / self.capacity_kg
            theta_c = 45 + 60 * (1 - min(frac, 1.0)) + self.onset_offset[c]
            if tilt > theta_c:
                rate_kg = min(2.0 * (tilt - theta_c), 40.0) / 1000  # g/s par degré, plafonné par le goulot
                n = self.rng.poisson(rate_kg * dt / self.unit_kg)
                out = min(n * self.unit_kg, self.content_kg[c])
                if out > 0:
                    self.content_kg[c] -= out
                    self.in_flight.append((now + 0.25, c, out))
        landed = [(col, kg) for (ta, col, kg) in self.in_flight if ta <= now]
        self.in_flight = [f for f in self.in_flight if f[0] > now]
        for col, kg in landed:
            if self.glass_layers and self.glass_layers[-1][0] == col:
                self.glass_layers[-1][1] += kg
            else:
                self.glass_layers.append([col, kg])

    def _torque(self, arm) -> np.ndarray:
        q, dq = self.q[arm], self.dq[arm]
        tau = self.arm_tau.copy() * (1 if arm == "right_arm" else -1)
        if arm == self.pour_arm and self.attached is not None:
            m = self.empty_kg + self.content_kg[self.attached]
            tilt = self._tilt()
            tau += m * self.G * self.lever_m
            tau[1] += m * self.G * self.com_shift_j2_m * math.sin(tilt)
            tau[self.pour_joint] += m * self.G * self.com_offset_m * math.sin(tilt)
        if self.enabled[arm]:
            tau += 0.5 * (self.cmd[arm] - q) * np.array([70, 70, 70, 60, 10, 10, 10, 10])
            tau += self.fric * self.fric_sign[arm] * np.where(np.abs(dq) > 1e-3, 1.0, 0.6)
        else:
            tau[:] = 0.0  # moteurs désarmés : aucun courant, donc aucun couple
        tau += self.rng.normal(0, self.noise)
        return np.round(tau / TAU_LSB) * TAU_LSB


class OpenArmBackend:
    """Vrai robot via openarm_driver. Une connexion `SingleArmDriver` par bras.

    Important (lu dans le SDK) :
      - `SingleArmDriver.start()` exécute une trajectoire de départ et
        `stop()` une trajectoire d'arrêt qui ferme/ouvre la pince : avec une
        bouteille en main c'est dangereux. On les neutralise via les hooks
        `_on_start` / `_on_stop` prévus par le driver.
      - Sans `enable`, on ne fait que `refresh_all()` (trames de lecture) : le
        bras est mou et le couple lu vaut ~0.
      - `disable` coupe le couple : le bras TOMBE s'il n'est pas soutenu.
    """

    read_only = False

    def __init__(self, arms=ARMS, config=None, can_interfaces=None):
        import openarm_driver as od  # Linux uniquement

        class _NoTrajectoryDriver(od.SingleArmDriver):
            def _on_start(self):
                return True

            def _on_stop(self):
                return True

        cfg = od.Config(config) if isinstance(config, str) else config
        can_interfaces = can_interfaces or {}
        self.drivers = {a: _NoTrajectoryDriver(a, config=cfg, can_interface=can_interfaces.get(a))
                        for a in arms}
        self.enabled = {a: False for a in arms}

    def enable(self, arm):
        if not self.drivers[arm].start():
            raise SafetyStop(f"{arm}: start refusé ({self.drivers[arm].safety_stop_reason})")
        self.enabled[arm] = True

    def disable(self, arm):
        self.drivers[arm].stop()
        self.enabled[arm] = False

    def command(self, arm, q_cmd):
        if not self.enabled[arm]:
            raise ReadOnlyError(f"{arm} non armé")
        if self.drivers[arm].send_position(q_cmd) is False:
            raise SafetyStop(f"{arm}: {self.drivers[arm].safety_stop_reason}")

    def read(self, arm) -> JointStates:
        d = self.drivers[arm]
        # Armé : send_position() vient de rafraîchir l'état. Sinon on interroge.
        s = d.latest_state if (self.enabled[arm] and d.latest_state) else d.fetch_state(refresh=True)
        return JointStates(time.time(), s["qpos"].copy(), s["qvel"].copy(),
                           s["qtorque"].copy(), s["tmos"].copy())

    def close(self):
        pass  # volontairement rien : voir Robot.close()


def decode_state(idx: int, d: bytes) -> tuple[float, float, float]:
    """Trame d'état Damiao -> (q brut, dq, tau). Cf. CanPacketDecoder::parse_motor_state_data."""
    def u2f(x, lim, bits):
        return x / ((1 << bits) - 1) * 2 * lim - lim

    pmax, vmax, tmax = MOTOR_LIMITS[MOTOR_TYPES[idx]]
    return (u2f((d[1] << 8) | d[2], pmax, 16),
            u2f((d[3] << 4) | (d[4] >> 4), vmax, 12),
            u2f(((d[4] & 0xF) << 8) | d[5], tmax, 12))


class CanSnifferBackend:
    """Écoute passive du bus : décode les réponses d'état des moteurs Damiao.

    Aucune trame n'est envoyée. On ne voit donc des données que si un autre
    programme (téléop, policy, monitor...) interroge ou commande les moteurs.
    Décodage identique à CanPacketDecoder::parse_motor_state_data (openarm_can).
    """

    read_only = True
    CAN_ERR_FLAG = 0x20000000
    CAN_EFF_MASK = 0x1FFFFFFF

    def __init__(self, arms=ARMS, can_interfaces=None, apply_offsets=True):
        if not sys.platform.startswith("linux"):
            raise RuntimeError("Le backend 'sniff' nécessite Linux (SocketCAN).")
        can_interfaces = {**DEFAULT_CAN, **(can_interfaces or {})}
        self.apply_offsets = apply_offsets
        self.lock = threading.Lock()
        self.state = {a: [np.full(N_JOINTS, np.nan) for _ in range(4)] + [0.0] for a in arms}
        self.frames = {a: 0 for a in arms}
        self.running = True
        self.threads = []
        for arm in arms:
            s = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            s.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FD_FRAMES, 1)
            s.settimeout(0.2)
            s.bind((can_interfaces[arm],))
            th = threading.Thread(target=self._rx, args=(arm, s), daemon=True)
            th.start()
            self.threads.append(th)

    def _rx(self, arm, s):
        while self.running:
            try:
                frame = s.recv(72)
            except socket.timeout:
                continue
            self.handle_frame(arm, frame)

    def handle_frame(self, arm, frame: bytes) -> bool:
        """Décode une trame brute SocketCAN (16 octets classique, 72 octets CAN-FD)."""
        can_id, length = struct.unpack_from("=IB", frame)
        if can_id & self.CAN_ERR_FLAG:
            return False
        idx = (can_id & self.CAN_EFF_MASK) - RECV_IDS[0]
        d = frame[8:8 + length]
        if not 0 <= idx < N_JOINTS or len(d) < 8:
            return False
        if d[2] in (0x33, 0x55) and d[1] == 0 and (d[0] >> 4) == 0:
            return False  # réponse à une lecture de paramètre, pas un état
        q, dq, tau = decode_state(idx, d)
        with self.lock:
            st = self.state[arm]
            st[0][idx] = q - (JOINT_OFFSETS[arm][idx] if self.apply_offsets else 0.0)
            st[1][idx], st[2][idx], st[3][idx] = dq, tau, d[6]
            st[4] = time.time()
            self.frames[arm] += 1
        return True

    def enable(self, arm):
        raise ReadOnlyError("backend sniff : lecture seule")

    disable = enable

    def command(self, arm, q_cmd):
        raise ReadOnlyError("backend sniff : lecture seule")

    def read(self, arm) -> JointStates:
        with self.lock:
            q, dq, tau, tmos, t = self.state[arm]
            return JointStates(t, q.copy(), dq.copy(), tau.copy(), tmos.copy())

    def close(self):
        self.running = False


# --------------------------------------------------------------------------- #
# Robot : l'objet partagé
# --------------------------------------------------------------------------- #

class Robot:
    """Point d'accès unique au robot, partagé entre les skills.

    Un thread de contrôle (control_hz) envoie en continu, pour chaque bras armé,
    une consigne qui rejoint la cible courante à vitesse limitée. Les skills ne
    font que changer les cibles (`set_joint_targets`, `move_joint`, ...).
    """

    def __init__(self, backend="mock", arms=ARMS, control_hz=100.0, **backend_kwargs):
        self.arms = tuple(arms)
        self.backend_name = backend
        if backend == "mock":
            self.backend = MockBackend(arms=self.arms, **backend_kwargs)
        elif backend == "openarm":
            self.backend = OpenArmBackend(arms=self.arms, **backend_kwargs)
        elif backend == "sniff":
            self.backend = CanSnifferBackend(arms=self.arms, **backend_kwargs)
        else:
            raise ValueError(f"backend inconnu : {backend}")
        self.dt = 1.0 / control_hz
        self._lock = threading.RLock()
        self._enabled = {a: False for a in self.arms}
        self._cmd: dict[str, np.ndarray] = {}
        self._target: dict[str, np.ndarray] = {}
        self._speed: dict[str, np.ndarray] = {}
        self._state = {a: self.backend.read(a) for a in self.arms}
        self._estop = False
        self._error: Exception | None = None
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="robot-control", daemon=True)
        self._thread.start()

    # ---- état ----
    @property
    def read_only(self) -> bool:
        return self.backend.read_only

    def is_enabled(self, arm) -> bool:
        return self._enabled[arm]

    def get_joint_states(self, arm="right_arm") -> JointStates:
        with self._lock:
            return self._state[arm]

    def get_targets(self, arm) -> np.ndarray:
        with self._lock:
            return self._target.get(arm, self._state[arm].q).copy()

    def get_command(self, arm) -> np.ndarray:
        """Consigne réellement envoyée en ce moment (rejoint la cible à vitesse limitée)."""
        with self._lock:
            return self._cmd.get(arm, self._state[arm].q).copy()

    # ---- armement ----
    def enable(self, arm):
        """Arme les moteurs et tient la position ACTUELLE (aucun mouvement)."""
        self._check_writable()
        with self._lock:
            self.backend.enable(arm)
            q = self.backend.read(arm).q
            self._cmd[arm], self._target[arm] = q.copy(), q.copy()
            self._speed[arm] = VEL_LIMITS * 0.5
            self._enabled[arm] = True

    def disable(self, arm):
        """Coupe le couple. ATTENTION : le bras tombe et la pince lâche."""
        with self._lock:
            self._enabled[arm] = False
            self.backend.disable(arm)

    # ---- commandes ----
    def set_joint_targets(self, arm, q, speed=None):
        """Nouvelle cible (8 valeurs, rad). Non bloquant. speed en rad/s (scalaire ou 8)."""
        self._check_can_move(arm)
        q = np.clip(np.asarray(q, float), JOINT_LIMITS[arm][:, 0], JOINT_LIMITS[arm][:, 1])
        with self._lock:
            self._target[arm] = q
            if speed is not None:
                self._speed[arm] = np.minimum(np.broadcast_to(speed, (N_JOINTS,)), VEL_LIMITS)

    def move_joints(self, arm, q, speed=0.5, timeout=None, should_abort=None) -> bool:
        """Mouvement articulaire bloquant. Renvoie False si interrompu."""
        q = np.asarray(q, float)
        cur = self.get_targets(arm)
        speed_v = np.minimum(np.broadcast_to(speed, (N_JOINTS,)).astype(float), VEL_LIMITS)
        # vitesses synchronisées : toutes les articulations arrivent ensemble
        dist = np.abs(q - cur)
        duration = float(np.max(dist / speed_v)) if np.any(dist > 0) else 0.0
        sync = np.where(dist > 0, dist / max(duration, 1e-6), speed_v)
        self.set_joint_targets(arm, q, speed=sync)
        return self.wait_until_reached(arm, timeout or 2.0 + 1.5 * duration, should_abort)

    def move_joint(self, arm, joint, angle, speed=0.5, timeout=None, should_abort=None) -> bool:
        q = self.get_targets(arm)
        q[joint] = angle
        return self.move_joints(arm, q, speed, timeout, should_abort)

    def move_wrist(self, angle, speed=0.2, arm="right_arm", joint=6, **kw) -> bool:
        """Raccourci pour l'articulation de versement (par défaut J7 du bras droit)."""
        return self.move_joint(arm, joint, angle, speed, **kw)

    def wait_until_reached(self, arm, timeout, should_abort=None, settle_s=0.1) -> bool:
        """Attend que la CONSIGNE ait rejoint la cible (+ settle_s).

        On ne teste pas la position mesurée : en commande MIT (PD) le bras garde
        une erreur statique due à la gravité, qui ferait échouer un test strict.
        """
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if self._error:
                raise self._error
            if self._estop:
                raise SafetyStop("arrêt d'urgence actif")
            if should_abort and should_abort():
                self.hold(arm)
                return False
            with self._lock:
                done = np.max(np.abs(self._cmd[arm] - self._target[arm])) < 1e-6
            if done:
                time.sleep(settle_s)
                return True
            time.sleep(0.01)
        log.warning("%s : cible non atteinte en %.1fs", arm, timeout)
        return False

    def hold(self, arm=None):
        """Fige la consigne là où elle est (sans à-coup)."""
        with self._lock:
            for a in ([arm] if arm else self._enabled):
                if self._enabled[a]:
                    self._target[a] = self._cmd[a].copy()

    def emergency_stop(self, disable=False):
        """Arrêt d'urgence LOGICIEL : fige les bras. disable=True coupe le couple (le bras tombe).

        Le vrai arrêt d'urgence reste le bouton physique.
        """
        self._estop = True
        self.hold()
        log.error("ARRÊT D'URGENCE (disable=%s)", disable)
        if disable:
            for a in self.arms:
                if self._enabled[a]:
                    self.disable(a)

    def reset_emergency_stop(self):
        self.hold()
        self._estop = False

    def close(self, disable=False):
        """Arrête le thread. Par défaut NE coupe PAS les moteurs (un bras qui tient
        une bouteille ne doit pas tomber parce qu'un script se termine)."""
        self._running = False
        self._thread.join(timeout=1.0)
        if disable:
            for a in self.arms:
                if self._enabled[a]:
                    self.backend.disable(a)
        self.backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- interne ----
    def _check_writable(self):
        if self.backend.read_only:
            raise ReadOnlyError(f"backend '{self.backend_name}' en lecture seule")

    def _check_can_move(self, arm):
        self._check_writable()
        if self._estop:
            raise SafetyStop("arrêt d'urgence actif")
        if not self._enabled[arm]:
            raise ReadOnlyError(f"{arm} non armé : appeler robot.enable('{arm}')")

    def _loop(self):
        next_t = time.monotonic()
        faulted: set[str] = set()
        while self._running:
            with self._lock:
                for a in self.arms:
                    try:
                        if self._enabled[a] and a not in faulted:
                            step = self._speed[a] * self.dt
                            self._cmd[a] = self._cmd[a] + np.clip(self._target[a] - self._cmd[a], -step, step)
                            self.backend.command(a, self._cmd[a])
                        self._state[a] = self.backend.read(a)
                    except Exception as e:  # noqa: BLE001 - remonté au prochain appel bloquant
                        log.exception("boucle de contrôle (%s)", a)
                        faulted.add(a)  # on arrête de commander ce bras
                        self._error, self._estop = e, True
            next_t += self.dt
            time.sleep(max(0.0, next_t - time.monotonic()))
            if time.monotonic() - next_t > 0.5:  # on a pris du retard : on recale
                next_t = time.monotonic()
