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
"""

import argparse
import math
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
JOINT_LIMITS = {"left": LEFT_DEFAULT_JOINTS_LIMITS, "right": RIGHT_DEFAULT_JOINTS_LIMITS}
NAMES = [name for name, _, _ in ARM_MOTORS]
# LeRobot openarm_follower position gains, scaled down by --gain-scale.
KP = dict(zip(NAMES, [240.0, 240.0, 240.0, 240.0, 24.0, 31.0, 25.0, 25.0]))
KD = dict(zip(NAMES, [5.0, 5.0, 3.0, 5.0, 0.3, 0.3, 0.3, 0.3]))

ALIGN_TOL_DEG = 10.0  # leader/follower gaps above this are flagged; closed at the approach speed
LIMIT_MARGIN_DEG = 5.0  # follower may start this far outside its limits: brought back at approach speed
TRACKING_ERROR_DEG = 25.0  # commanded vs measured gap that triggers a stop while running
LEADER_JUMP_DEG = 15.0  # leader change in one cycle no hand can make (bad read, angle wrap): stop
MAX_TEMP_C = 65
MAX_MISSED_CYCLES = 5


class Arm:
    def __init__(self, side: str, leader_port: str, can_channel: str):
        self.side = side
        self.can_channel = can_channel
        self.limits = JOINT_LIMITS[side]
        self.leader = OpenArmMini(OpenArmMiniConfig(
            port=leader_port, side=side, id=f"my_openarm_mini_{side}", calibration_dir=LEADER_CALIBRATION))
        self.bus: can.BusABC | None = None
        self.enabled = False

    def connect(self):
        # Ping + reads only: no configure(), no calibration write, the leader stays as it is.
        self.leader.bus.connect()
        self.bus = can.Bus(interface="socketcan", channel=self.can_channel, fd=True)

    def disconnect(self):
        if self.bus is not None:
            if self.enabled:
                self.disable()
            self.bus.shutdown()
        if self.leader.bus.is_connected:
            self.leader.bus.disconnect(disable_torque=False)

    def leader_targets(self) -> dict[str, float]:
        action = self.leader.get_action()
        return {n: action[f"{n}.pos"] for n in NAMES}

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

    def command(self, cmd_deg: dict[str, float], scale: float):
        for name, send_id, mtype in ARM_MOTORS:
            send_mit(self.bus, send_id, mtype, math.radians(cmd_deg[name]),
                     kp=KP[name] * scale, kd=KD[name] * max(scale, 0.2))
        return collect_states(self.bus, ARM_MOTORS, timeout=0.01)

    def disable(self):
        for _, send_id, _ in ARM_MOTORS:
            send_disable(self.bus, send_id)
        self.enabled = False


def preflight(arm: Arm) -> tuple[bool, dict[str, float]]:
    """Read-only check of one arm. Returns (ok, follower positions in degrees)."""
    states = arm.follower_states()
    leader = arm.leader_targets()
    ok = True
    biggest = ("", 0.0)
    print(f"\n[{arm.side}] leader {arm.leader.config.port} -> follower {arm.can_channel}")
    print(f"  {'joint':<9}{'follower':>9}{'leader':>9}{'gap':>7}  limits         problem")
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
        if not lo - LIMIT_MARGIN_DEG <= f <= hi + LIMIT_MARGIN_DEG:
            problems.append("follower outside limits")
        if not lo <= leader[name] <= hi:
            problems.append("leader outside limits (clipped)")
        if max(s.t_mos, s.t_rotor) > MAX_TEMP_C:
            problems.append("hot")
        ok &= not problems or all("clipped" in p for p in problems)
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


def run(arms: list[Arm], fps: float, max_speed: float, approach_speed: float, gain_scale: float,
        ramp_s: float):
    dt = 1.0 / fps
    max_step = max_speed * dt
    approach_step = approach_speed * dt
    cmd: dict[str, dict[str, float]] = {}
    missed = {arm.side: {n: 0 for n in NAMES} for arm in arms}

    def check(arm: Arm, states):
        for name in NAMES:
            s = states.get(name)
            if s is None:
                missed[arm.side][name] += 1
                if missed[arm.side][name] > MAX_MISSED_CYCLES:
                    raise RuntimeError(f"{arm.side} {name}: no answer")
                continue
            missed[arm.side][name] = 0
            if s.status != 0x1:
                raise RuntimeError(f"{arm.side} {name}: {s.status_name}")
            if max(s.t_mos, s.t_rotor) > MAX_TEMP_C:
                raise RuntimeError(f"{arm.side} {name}: temperature {max(s.t_mos, s.t_rotor)} C")
            err = cmd[arm.side][name] - math.degrees(s.q)
            if abs(err) > TRACKING_ERROR_DEG:
                raise RuntimeError(f"{arm.side} {name}: tracking error {err:.1f} deg")

    # Phase 1: hold the current pose while the gains ramp up from 0.
    for arm in arms:
        states = arm.follower_states()
        cmd[arm.side] = {n: math.degrees(states[n].q) for n in NAMES}
        arm.enable_and_hold(cmd[arm.side], 0.0)
    print(f"Torque on, holding pose; gains ramping over {ramp_s:.1f} s...")
    t0 = time.monotonic()
    while (elapsed := time.monotonic() - t0) < ramp_s:
        scale = gain_scale * elapsed / ramp_s
        for arm in arms:
            check(arm, arm.command(cmd[arm.side], scale))
        time.sleep(dt)

    # Phase 2: reach the leader's pose at approach_speed, then follow it at max_speed.
    print(f"Moving to the leader's pose at {approach_speed:.0f} deg/s. Keep the leader still.")
    synced = False
    last_target = {arm.side: arm.leader_targets() for arm in arms}
    while True:
        step = max_step if synced else approach_step
        reached = True
        start = time.monotonic()
        for arm in arms:
            target = arm.leader_targets()
            for name in NAMES:
                if abs(target[name] - last_target[arm.side][name]) > LEADER_JUMP_DEG:
                    raise RuntimeError(f"{arm.side} leader {name} jumped "
                                       f"{last_target[arm.side][name]:.1f} -> {target[name]:.1f} deg")
            last_target[arm.side] = target
            for name in NAMES:
                goal = arm.clip(name, target[name])
                prev = cmd[arm.side][name]
                cmd[arm.side][name] = prev + min(max(goal - prev, -step), step)
                reached &= abs(goal - prev) <= step
            check(arm, arm.command(cmd[arm.side], gain_scale))
        if reached and not synced:
            synced = True
            print(f"In sync. Teleop running ({max_speed:.0f} deg/s cap, gains x{gain_scale}). "
                  "Ctrl+C to stop.")
        time.sleep(max(0.0, dt - (time.monotonic() - start)))


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
    p.add_argument("--fps", type=float, default=50.0)
    p.add_argument("--max-speed", type=float, default=30.0, help="per-joint speed cap, deg/s")
    p.add_argument("--approach-speed", type=float, default=10.0,
                   help="per-joint speed while moving to the leader's pose at start, deg/s")
    p.add_argument("--gain-scale", type=float, default=0.3, help="fraction of LeRobot's kp/kd")
    p.add_argument("--ramp", type=float, default=2.0, help="gain ramp-up duration, s")
    args = p.parse_args()

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
        checks = [preflight(arm) for arm in arms]
        ok = all(arm_ok for arm_ok, _ in checks)
        if not args.run:
            return
        if not ok:
            print("\nPreflight failed: not enabling torque.")
            return
        for arm, (_, (name, gap)) in zip(arms, checks):
            print(f"[{arm.side}] biggest startup move: {name} {gap:+.1f} deg, "
                  f"~{abs(gap) / args.approach_speed:.1f} s at {args.approach_speed:.0f} deg/s")
        # Prompt on stdout ourselves: input() may write it to stderr, which watch/teleop.sh filter.
        print("\nTorque will be enabled on the follower. Type GO and press Enter to start: ",
              end="", flush=True)
        if input().strip() != "GO":
            print("Aborted, torque was never enabled.")
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
