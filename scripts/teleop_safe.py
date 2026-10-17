"""Cautious OpenArm Mini -> OpenArm follower teleoperation over socketcan (Linux).

Default (--check) and --watch are read-only: leader position reads and Damiao refresh requests only.
--run enables torque, but only if the preflight passes and you type GO:
  1. hold the follower where it is while the gains ramp up from 0,
  2. move it to the leader's pose slowly (--approach-speed), however far it is,
  3. track the leader with a speed cap and reduced gains,
  4. disable torque on Ctrl+C or on any fault (missing motor, motor error, overheat, tracking error).
Disabling torque makes the arm go limp: keep it near its rest pose or support it when stopping.

Usage:
  uv run python scripts/teleop_safe.py --left /dev/ttyACM0:can0 --right /dev/ttyACM1:can1          # check
  uv run python scripts/teleop_safe.py --left /dev/ttyACM0:can0 --watch                             # live check
  uv run python scripts/teleop_safe.py --left /dev/ttyACM0:can0 --run                               # teleop
  uv run python scripts/teleop_safe.py --left /dev/ttyACM0:can0 --directions                        # sign test

--directions (read-only) compares how leader and follower joints move when you move both the same way,
and saves the joints to invert in calibration/teleop_flips.json, which every mode applies.
"""

import argparse
import json
import math
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import can  # noqa: E402
from lerobot.robots.openarm_follower.config_openarm_follower import (  # noqa: E402
    LEFT_DEFAULT_JOINTS_LIMITS,
    RIGHT_DEFAULT_JOINTS_LIMITS,
)
from lerobot.teleoperators.openarm_mini import OpenArmMini, OpenArmMiniConfig  # noqa: E402

from hardware.damiao import (  # noqa: E402
    ARM_MOTORS,
    collect_states,
    read_states,
    send_disable,
    send_enable,
    send_mit,
)

LEADER_CALIBRATION = ROOT / "calibration" / "teleoperators" / "openarm_mini"
# Per side, joints whose leader reading is inverted on top of LeRobot's own flips (set by --directions).
FLIPS_FILE = ROOT / "calibration" / "teleop_flips.json"
# Per side, degrees added to a leader joint (after the flips) so that leader and follower read the
# same in a matched pose, e.g. a wrist whose zero differs by ~90 deg (set by --align).
OFFSETS_FILE = ROOT / "calibration" / "teleop_offsets.json"
# Per side, pairs of follower joints whose leader readings are exchanged, applied before flips and
# offsets. LeRobot already maps leader joint_6/7 to follower joint_7/6; with the wrist roll zeros
# 90 deg apart that mapping is wrong and [["joint_6", "joint_7"]] undoes it.
SWAPS_FILE = ROOT / "calibration" / "teleop_swaps.json"
DIRECTION_MIN_DEG = 5.0  # a joint must move at least this much on both arms to be judged
# Per side, joint ranges measured on this robot (scripts/measure_range.py, minus a margin) that
# replace LeRobot's generic limits joint by joint: a command past a real mechanical stop makes the
# motor push into it at full torque and overheat (right joint_3 reached 81 C that way).
LIMITS_FILE = ROOT / "calibration" / "joint_limits.json"


def load_joint_limits() -> dict[str, dict[str, tuple[float, float]]]:
    limits = {"left": dict(LEFT_DEFAULT_JOINTS_LIMITS), "right": dict(RIGHT_DEFAULT_JOINTS_LIMITS)}
    if LIMITS_FILE.exists():
        for side, joints in json.loads(LIMITS_FILE.read_text()).items():
            for name, (lo, hi) in joints.items():
                limits[side][name] = (float(lo), float(hi))
    return limits


JOINT_LIMITS = load_joint_limits()
NAMES = [name for name, _, _ in ARM_MOTORS]
# LeRobot openarm_follower position gains, scaled down by --gain-scale.
KP = dict(zip(NAMES, [240.0, 240.0, 240.0, 240.0, 24.0, 31.0, 25.0, 25.0]))
KD = dict(zip(NAMES, [5.0, 5.0, 3.0, 5.0, 0.3, 0.3, 0.3, 0.3]))

ALIGN_TOL_DEG = 10.0  # leader/follower gaps above this are flagged; closed at the approach speed
TARGET_FAR_DEG = 20.0  # a target this far past a limit is a bad reading (wrap, calibration): refuse
LIMIT_MARGIN_DEG = 5.0  # follower may start this far outside its limits: brought back at approach speed
TRACKING_ERROR_DEG = 60.0  # commanded vs measured gap that triggers a stop while running
LEADER_JUMP_DEG = 45.0  # leader change in one cycle no hand can make (bad read, angle wrap): stop
MAX_TEMP_C = 80
MAX_MISSED_S = 0.5  # a motor silent this long stops everything (counted in cycles at the loop rate)
VEL_SMOOTHING = 0.5  # EMA weight of the newest velocity feedforward sample (leader readings are noisy)


def stop_on_signals():
    """Turn SIGTERM / SIGHUP (kill, closed terminal) into KeyboardInterrupt, so the same cleanup
    as Ctrl+C runs and torque is disabled. Without this, Python exits without running `finally`."""
    def handler(signum, frame):
        raise KeyboardInterrupt(signal.Signals(signum).name)

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, handler)


def load_flips() -> dict[str, list[str]]:
    return json.loads(FLIPS_FILE.read_text()) if FLIPS_FILE.exists() else {}


def load_offsets() -> dict[str, dict[str, float]]:
    return json.loads(OFFSETS_FILE.read_text()) if OFFSETS_FILE.exists() else {}


def load_swaps() -> dict[str, list[list[str]]]:
    return json.loads(SWAPS_FILE.read_text()) if SWAPS_FILE.exists() else {}


class Arm:
    """One follower arm on a CAN channel, with its leader unless leader_port is None (policy runs)."""

    def __init__(self, side: str, leader_port: str | None, can_channel: str):
        self.side = side
        self.can_channel = can_channel
        self.limits = JOINT_LIMITS[side]
        self.leader = None if leader_port is None else OpenArmMini(OpenArmMiniConfig(
            port=leader_port, side=side, id=f"my_openarm_mini_{side}", calibration_dir=LEADER_CALIBRATION))
        self.bus: can.BusABC | None = None
        self.enabled = False
        self.flips = set(load_flips().get(side, []))
        self.offsets = load_offsets().get(side, {})
        self.swaps = load_swaps().get(side, [])

    def connect(self):
        # Ping + reads only: no configure(), no calibration write, the leader stays as it is.
        if self.leader is not None:
            self.leader.bus.connect()
        self.bus = can.Bus(interface="socketcan", channel=self.can_channel, fd=True)

    def disconnect(self, keep_torque: bool = False):
        """Close the buses. keep_torque leaves the motors enabled on their last command (handover)."""
        if self.bus is not None:
            if self.enabled and not keep_torque:
                self.disable()
            self.bus.shutdown()
            self.bus = None
        if self.leader is not None and self.leader.bus.is_connected:
            self.leader.bus.disconnect(disable_torque=False)

    def leader_targets(self) -> dict[str, float]:
        action = self.leader.get_action()
        for a, b in self.swaps:
            action[f"{a}.pos"], action[f"{b}.pos"] = action[f"{b}.pos"], action[f"{a}.pos"]
        out = {n: (-action[f"{n}.pos"] if n in self.flips else action[f"{n}.pos"]) + self.offsets.get(n, 0.0)
               for n in NAMES}
        # A leader joint turned past +-180 deg reads as a jump to the other end; unwrap it so a real
        # move stays continuous (179 -> 181) instead of tripping the jump check (179 -> -180).
        last = getattr(self, "_last_leader", None)
        for n in NAMES:
            if last is None:  # first reading: the turn closest to zero (an offset can push it past 180)
                out[n] = (out[n] + 180.0) % 360.0 - 180.0
            else:
                out[n] += 360.0 * round((last[n] - out[n]) / 360.0)
        self._last_leader = out
        return out

    def clip(self, name: str, deg: float) -> float:
        lo, hi = self.limits[name]
        return min(max(deg, lo), hi)

    def follower_states(self):
        return read_states(self.bus, timeout=0.2)

    def enable_and_hold(self, hold_deg: dict[str, float], scale: float):
        self.enabled = True
        for name, send_id, mtype in ARM_MOTORS:
            send_enable(self.bus, send_id)
            send_mit(self.bus, send_id, mtype, math.radians(hold_deg[name]),
                     kp=KP[name] * scale, kd=KD[name] * max(scale, 0.2))
        return collect_states(self.bus, ARM_MOTORS, timeout=0.05)

    def command(self, cmd_deg: dict[str, float], scale: float, vel_dps: dict[str, float] | None = None):
        """MIT command; vel_dps (deg/s) is the commanded velocity, so kd damps the error to the
        intended motion instead of braking every move (0 when holding)."""
        for name, send_id, mtype in ARM_MOTORS:
            send_mit(self.bus, send_id, mtype, math.radians(cmd_deg[name]),
                     dq=math.radians(vel_dps[name]) if vel_dps else 0.0,
                     kp=KP[name] * scale, kd=KD[name] * max(scale, 0.2))
        return collect_states(self.bus, ARM_MOTORS, timeout=0.01)

    def disable(self):
        for _, send_id, _ in ARM_MOTORS:
            send_disable(self.bus, send_id)
        self.enabled = False


def preflight(arm: Arm, target: dict[str, float] | None = None) -> tuple[bool, tuple[str, float]]:
    """Read-only check of one arm against its leader, or against `target` (e.g. a policy's first
    action). Returns (ok, (joint, gap) of the biggest startup move)."""
    states = arm.follower_states()
    leader = arm.leader_targets() if target is None else target
    source = f"leader {arm.leader.config.port}" if target is None else "target"
    ok = True
    biggest = ("", 0.0)
    print(f"\n[{arm.side}] {source} -> follower {arm.can_channel}")
    print(f"  {'joint':<9}{'follower':>9}{'target':>9}{'gap':>7}  limits         problem")
    follower = {}
    for name in NAMES:
        s = states.get(name)
        lo, hi = arm.limits[name]
        if s is None:
            print(f"  {name:<9}{'--':>9}{leader[name]:>9.1f}{'':>7}  [{lo:>4.0f},{hi:>4.0f}]  no answer")
            ok = False
            continue
        f = math.degrees(s.q)
        follower[name] = f
        gap = arm.clip(name, leader[name]) - f
        problems = []
        if s.status not in (0x0, 0x1):
            problems.append(s.status_name)
        elif s.status == 0x1:
            # Not blocking, but the start ramps the gains from 0: an arm held up by another
            # program's command goes limp for a moment. Support it or disable it first.
            problems.append("already ENABLED (another program?): support the arm")
        if not lo - LIMIT_MARGIN_DEG <= f <= hi + LIMIT_MARGIN_DEG:
            problems.append("follower outside limits")
        if not lo - TARGET_FAR_DEG <= leader[name] <= hi + TARGET_FAR_DEG:
            problems.append(f"target > {TARGET_FAR_DEG:.0f} deg outside limits: check the leader")
        elif not lo <= leader[name] <= hi:
            problems.append("target outside limits (clipped)")
        if max(s.t_mos, s.t_rotor) > MAX_TEMP_C:
            problems.append("hot")
        ok &= all("clipped" in p or "already ENABLED" in p for p in problems)
        if abs(gap) > ALIGN_TOL_DEG:
            problems.append("slow approach")
        if abs(gap) > abs(biggest[1]):
            biggest = (name, gap)
        print(f"  {name:<9}{f:>9.1f}{leader[name]:>9.1f}{gap:>7.1f}  [{lo:>4.0f},{hi:>4.0f}]  "
              f"{', '.join(problems)}")
    print(f"  -> {'OK' if ok else 'NOT READY'}")
    return ok, biggest


def watch_view(arms: list[Arm]):
    """One compact table (fits a 24-line terminal), redrawn in place. Read-only."""
    reads = []
    for arm in arms:
        states, leader = arm.follower_states(), arm.leader_targets()
        reads.append({n: (math.degrees(states[n].q) if n in states else None, leader[n]) for n in NAMES})
    lines = ["  " + f"{'':<9}" + "".join(f"{arm.side + ' ' + arm.can_channel:^24}" for arm in arms),
             "  " + f"{'joint':<9}" + f"{'follower':>9}{'leader':>8}{'gap':>7}" * len(arms)]
    for name in NAMES:
        row = f"  {name:<9}"
        for arm, read in zip(arms, reads):
            f, lead = read[name]
            if f is None:
                row += f"{'--':>9}{lead:>8.1f}{'':>7}"
                continue
            gap = arm.clip(name, lead) - f
            row += f"{f:>9.1f}{lead:>8.1f}{gap:>6.1f}{'!' if abs(gap) > ALIGN_TOL_DEG else ' '}"
        lines.append(row)
    lines.append(f"\n  ! = gap > {ALIGN_TOL_DEG:.0f} deg.  Read-only, no torque.  Ctrl+C to stop.")
    print("\033[H\033[J" + "\n".join(lines), flush=True)


def direction_test(arms: list[Arm]):
    """Read-only: find the joints whose leader reading moves opposite to the follower."""
    def snapshot():
        out = {}
        for arm in arms:
            states = arm.follower_states()
            out[arm.side] = ({n: math.degrees(states[n].q) for n in states}, arm.leader_targets())
        return out

    print("\nDirection test (read-only, no torque).\n"
          "Put each leader and its follower in the same pose, then press Enter.")
    input()
    before = snapshot()
    print("Now move some joints by 20-40 deg, the SAME way on the leader and on its follower\n"
          "(e.g. joints 1-4 together, then rerun for 5-7). Press Enter when both are in the new pose.")
    input()
    after = snapshot()

    flips = load_flips()
    changed = False
    for arm in arms:
        (f0, l0), (f1, l1) = before[arm.side], after[arm.side]
        print(f"\n[{arm.side}] leader {arm.leader.config.port} / follower {arm.can_channel}")
        print(f"  {'joint':<9}{'follower':>10}{'leader':>9}  verdict")
        side_flips = set(flips.get(arm.side, []))
        for name in NAMES:
            if name not in f0 or name not in f1:
                print(f"  {name:<9}{'--':>10}")
                continue
            df, dl = f1[name] - f0[name], l1[name] - l0[name]
            if abs(df) < DIRECTION_MIN_DEG and abs(dl) < DIRECTION_MIN_DEG:
                verdict = "not moved"
            elif abs(df) < DIRECTION_MIN_DEG or abs(dl) < DIRECTION_MIN_DEG:
                verdict = "only one moved: wrong leader/follower pairing?"
            elif (df > 0) == (dl > 0):
                verdict = "same direction, OK"
            elif name == "gripper":
                verdict = "OPPOSITE: gripper needs a leader gripper calibration, not a flip"
            else:
                verdict = "OPPOSITE -> will invert"
                side_flips ^= {name}
                changed = True
            print(f"  {name:<9}{df:>+10.1f}{dl:>+9.1f}  {verdict}")
        flips[arm.side] = sorted(side_flips)

    if not changed:
        print("\nNothing to invert.")
        return
    print(f"\nNew inversions: {json.dumps(flips)}\nSave them to {FLIPS_FILE.relative_to(ROOT)}? [y/N] ",
          end="", flush=True)
    if input().strip().lower() == "y":
        FLIPS_FILE.write_text(json.dumps(flips, indent=2) + "\n")
        print("Saved. They apply to --watch, the check and --run.")
    else:
        print("Not saved.")


class Teleop:
    """Torque-on control loop shared by --run, scripts/record.py and scripts/run_policy.py.

    start() holds the pose while the gains ramp up; each step() then moves the follower towards the
    target (the leader by default, or targets(arm) -> {joint: deg}), at approach_speed until it has
    reached the target once, then at max_speed.
    """

    def __init__(self, arms: list[Arm], fps: float, max_speed: float, approach_speed: float,
                 gain_scale: float, ramp_s: float, targets=None):
        self.arms = arms
        self.targets = targets or (lambda arm: arm.leader_targets())
        self.dt = 1.0 / fps
        self.max_step = max_speed * self.dt
        self.approach_step = approach_speed * self.dt
        self.max_speed, self.approach_speed = max_speed, approach_speed
        self.gain_scale = gain_scale
        self.ramp_s = ramp_s
        self.cmd: dict[str, dict[str, float]] = {}
        self.measured: dict[str, dict[str, float]] = {}
        self.missed = {arm.side: {n: 0 for n in NAMES} for arm in arms}
        self.last_target: dict[str, dict[str, float]] = {}
        self.synced = False
        self.vel = {arm.side: {n: 0.0 for n in NAMES} for arm in arms}
        self.max_missed = max(1, round(MAX_MISSED_S / self.dt))
        self.reset_stats()

    def reset_stats(self):
        """Start a new tracking measurement (counted only once synced, see summary())."""
        self.stats = {arm.side: {n: {"err_sum": 0.0, "err_max": 0.0, "capped": 0} for n in NAMES}
                      for arm in self.arms}
        self.stat_cycles = 0

    def summary(self) -> str:
        """Per joint: command vs measured error (low gains -> sag, lag) and share of cycles at the
        speed cap (high -> --max-speed is what limits the follower)."""
        if not self.stat_cycles:
            return "No tracking stats (never in sync)."
        lines = [f"Tracking over {self.stat_cycles} cycles ({self.max_speed:.0f} deg/s cap, "
                 f"gains x{self.gain_scale}):",
                 f"  {'joint':<9}" + "".join(f"{arm.side + ' err mean/max':>22}{'at cap':>8}" for arm in self.arms)]
        for name in NAMES:
            row = f"  {name:<9}"
            for arm in self.arms:
                s = self.stats[arm.side][name]
                row += (f"{s['err_sum'] / self.stat_cycles:>14.1f} /{s['err_max']:>5.1f}"
                        f"{100 * s['capped'] / self.stat_cycles:>7.0f}%")
            lines.append(row)
        lines.append("  err: command - measured, deg (a few deg max is good; more -> raise GAIN_SCALE).\n"
                     "  at cap: share of cycles limited by the speed cap (often high -> raise MAX_SPEED).")
        return "\n".join(lines)

    def _check(self, arm: Arm, states):
        for name in NAMES:
            s = states.get(name)
            if s is None:
                self.missed[arm.side][name] += 1
                if self.missed[arm.side][name] > self.max_missed:
                    raise RuntimeError(f"{arm.side} {name}: no answer")
                continue
            self.missed[arm.side][name] = 0
            if s.status >= 0x8:  # real fault codes only (overcurrent, overheat, ...)
                raise RuntimeError(f"{arm.side} {name}: {s.status_name}")
            if max(s.t_mos, s.t_rotor) > MAX_TEMP_C:
                raise RuntimeError(f"{arm.side} {name}: temperature {max(s.t_mos, s.t_rotor)} C")
            self.measured[arm.side][name] = math.degrees(s.q)
            err = self.cmd[arm.side][name] - self.measured[arm.side][name]
            if abs(err) > TRACKING_ERROR_DEG:
                raise RuntimeError(f"{arm.side} {name}: tracking error {err:.1f} deg")
            if self.synced:
                st = self.stats[arm.side][name]
                st["err_sum"] += abs(err)
                st["err_max"] = max(st["err_max"], abs(err))

    def start(self):
        """Phase 1: hold the current pose while the gains ramp up from 0."""
        for arm in self.arms:
            states = arm.follower_states()
            self.cmd[arm.side] = {n: math.degrees(states[n].q) for n in NAMES}
            self.measured[arm.side] = dict(self.cmd[arm.side])
            arm.enable_and_hold(self.cmd[arm.side], 0.0)
        print(f"Torque on, holding pose; gains ramping over {self.ramp_s:.1f} s...")
        t0 = time.monotonic()
        while (elapsed := time.monotonic() - t0) < self.ramp_s:
            scale = self.gain_scale * elapsed / self.ramp_s
            for arm in self.arms:
                self._check(arm, arm.command(self.cmd[arm.side], scale))
            time.sleep(self.dt)
        print(f"Moving to the target pose at {self.approach_speed:.0f} deg/s. Keep the leader still.")
        self.last_target = {arm.side: self.targets(arm) for arm in self.arms}

    def step(self):
        """Phase 2, one cycle: move each joint towards the target by at most one speed-capped step."""
        step = self.max_step if self.synced else self.approach_step
        reached = True
        for arm in self.arms:
            target = self.targets(arm)
            last = self.last_target[arm.side]
            for name in NAMES:
                if abs(target[name] - last[name]) > LEADER_JUMP_DEG:
                    raise RuntimeError(f"{arm.side} target {name} jumped "
                                       f"{last[name]:.1f} -> {target[name]:.1f} deg")
            self.last_target[arm.side] = target
            for name in NAMES:
                goal = arm.clip(name, target[name])
                prev = self.cmd[arm.side][name]
                self.cmd[arm.side][name] = prev + min(max(goal - prev, -step), step)
                reached &= abs(goal - prev) <= step
                if self.synced and abs(goal - prev) > step:
                    self.stats[arm.side][name]["capped"] += 1
                v = self.vel[arm.side]
                v[name] += VEL_SMOOTHING * ((self.cmd[arm.side][name] - prev) / self.dt - v[name])
            self._check(arm, arm.command(self.cmd[arm.side], self.gain_scale, self.vel[arm.side]))
        if self.synced:
            self.stat_cycles += 1
        if reached and not self.synced:
            self.synced = True
            print(f"In sync. Teleop running ({self.max_speed:.0f} deg/s cap, gains x{self.gain_scale}).")

    def hold(self):
        """One cycle of holding the last command (no new target, zero velocity)."""
        for arm in self.arms:
            self.vel[arm.side] = {n: 0.0 for n in NAMES}
            self._check(arm, arm.command(self.cmd[arm.side], self.gain_scale))

    def retarget(self, targets):
        """Switch the target source, e.g. from a frozen first action to the live policy."""
        self.targets = targets
        self.last_target = {arm.side: targets(arm) for arm in self.arms}


def confirm_start(arms: list[Arm], approach_speed: float, targets=None) -> bool:
    """Preflight every arm (against its leader, or targets(arm)), show the startup moves and ask
    for GO. True only if torque may go on."""
    checks = [preflight(arm, None if targets is None else targets(arm)) for arm in arms]
    if not all(ok for ok, _ in checks):
        print("\nPreflight failed: not enabling torque.")
        return False
    for arm, (_, (name, gap)) in zip(arms, checks):
        print(f"[{arm.side}] biggest startup move: {name} {gap:+.1f} deg, "
              f"~{abs(gap) / approach_speed:.1f} s at {approach_speed:.0f} deg/s")
    # Prompt on stdout ourselves: input() may write it to stderr, which watch/teleop.sh filter.
    print("\nTorque will be enabled on the follower. Type GO and press Enter to start: ", end="", flush=True)
    if input().strip() != "GO":
        print("Aborted, torque was never enabled.")
        return False
    return True


def align_offsets(arms: list[Arm], joints: list[str]):
    """Read-only: leader and follower in the same pose -> per-joint leader offset, averaged over 1 s."""
    sums = {arm.side: {n: 0.0 for n in joints} for arm in arms}
    count = 0
    t0 = time.monotonic()
    while time.monotonic() - t0 < 1.0:
        for arm in arms:
            states, leader = arm.follower_states(), arm.leader_targets()
            for n in joints:
                if n not in states:
                    raise RuntimeError(f"{arm.side} {n}: no answer")
                # Wrapped difference: the leader can read +-180 for the same orientation.
                d = math.degrees(states[n].q) - leader[n]
                sums[arm.side][n] += (d + 180.0) % 360.0 - 180.0
        count += 1
        time.sleep(0.05)

    offsets = load_offsets()
    print(f"\n  {'side':<6}{'joint':<9}{'current':>9}{'measured':>10}{'new':>9}")
    for arm in arms:
        side = offsets.setdefault(arm.side, {})
        for n in joints:
            extra = sums[arm.side][n] / count
            new = round(side.get(n, 0.0) + extra, 1)
            print(f"  {arm.side:<6}{n:<9}{side.get(n, 0.0):>9.1f}{extra:>+10.1f}{new:>9.1f}")
            side[n] = new
    print(f"\nSave these leader offsets to {OFFSETS_FILE.relative_to(ROOT)}? [y/N] ", end="", flush=True)
    if input().strip().lower() == "y":
        OFFSETS_FILE.write_text(json.dumps(offsets, indent=2) + "\n")
        print("Saved. They apply to --watch, the check, --run, recording and the policy runs.")
    else:
        print("Not saved.")


def run(arms: list[Arm], fps: float, max_speed: float, approach_speed: float, gain_scale: float,
        ramp_s: float):
    teleop = Teleop(arms, fps, max_speed, approach_speed, gain_scale, ramp_s)
    teleop.start()
    print("Ctrl+C to stop.")
    try:
        while True:
            start = time.monotonic()
            teleop.step()
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))
    finally:
        print("\n" + teleop.summary())


def parse_pair(value: str) -> tuple[str, str]:
    leader_port, sep, can_channel = value.partition(":")
    if not sep:
        raise argparse.ArgumentTypeError("expected LEADER_PORT:CAN_CHANNEL, e.g. /dev/ttyACM0:can0")
    return leader_port, can_channel


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--left", type=parse_pair, help="LEADER_PORT:CAN_CHANNEL of the left arm")
    p.add_argument("--right", type=parse_pair, help="LEADER_PORT:CAN_CHANNEL of the right arm")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true", help="repeat the read-only check every 0.5 s")
    mode.add_argument("--run", action="store_true", help="enable torque and teleoperate")
    mode.add_argument("--directions", action="store_true",
                      help="read-only test of which joints move the wrong way, saves the inversions")
    mode.add_argument("--align", nargs="+", choices=NAMES, metavar="JOINT",
                      help="read-only: with leader and follower in the same pose, measure and save the "
                           "leader offset of these joints (e.g. --align joint_5)")
    p.add_argument("--fps", type=float, default=50.0)
    p.add_argument("--max-speed", type=float, default=30.0, help="per-joint speed cap, deg/s")
    p.add_argument("--approach-speed", type=float, default=10.0,
                   help="per-joint speed while moving to the leader's pose at start, deg/s")
    p.add_argument("--gain-scale", type=float, default=0.3, help="fraction of LeRobot's kp/kd")
    p.add_argument("--ramp", type=float, default=2.0, help="gain ramp-up duration, s")
    args = p.parse_args()
    stop_on_signals()

    arms = [Arm(side, *pair) for side, pair in (("left", args.left), ("right", args.right)) if pair]
    if not arms:
        p.error("give at least one of --left / --right")

    started = False
    try:
        for arm in arms:
            arm.connect()
        if args.watch:
            while True:
                watch_view(arms)
                time.sleep(0.5)
        if args.directions:
            direction_test(arms)
            return
        if args.align:
            align_offsets(arms, args.align)
            return
        if not args.run:
            for arm in arms:
                preflight(arm)
            return
        if not confirm_start(arms, args.approach_speed):
            return
        started = True
        run(arms, args.fps, args.max_speed, args.approach_speed, args.gain_scale, args.ramp)
    except KeyboardInterrupt:
        print("\nStopping.")
    except Exception as e:  # noqa: BLE001
        print(f"\nSAFETY STOP: {e}")
    finally:
        for arm in arms:
            arm.disconnect()
        if any(arm.enabled for arm in arms):
            print("WARNING: could not confirm torque off.")
        elif started:
            print("Torque disabled.")


if __name__ == "__main__":
    main()
