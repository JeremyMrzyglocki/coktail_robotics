"""Keep our joint zero (the one of the dataset and policies) without relying on the motors' zero.

Another team calibrating the robot with LeRobot rewrites the zero stored in the motors. Instead of
writing it back by hand (never exactly the same, and they overwrite it again), we keep a reference
and measure, each time the robot comes back, how far the motors' zero is from ours:

  ./scripts/zero_check.sh save    # once, while the zeros are ours: record the reference
  ./scripts/zero_check.sh         # each time the robot comes back: measure the offsets

Torque off only (Damiao refresh, refuses enabled motors). While the live view runs, by hand:
  1. push each joint gently to both of its mechanical stops (the min/max seen are kept),
  2. put the arms in the reference pose (hanging, gripper closed, the marks on each joint
     aligned), then press Enter.
save writes calibration/zero_reference.json: that pose and the stops, in our frame (motor angle
minus the current offsets). The default run compares with it and writes the per-joint offset to
calibration/zero_offsets.json (read by every script that drives the arms, see teleop_safe.py) and
to the joint_offsets of skills/pour/config/openarm_cocktail.yaml. The motors are never written.

Offset of a joint = the stops' shift when both stops were reached and agree (repeatable to a
fraction of a degree), else the pose's shift (as good as the marks).
"""

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import can  # noqa: E402
from rig import next_key, stdin_lines  # noqa: E402
from teleop_safe import ZERO_FILE, load_zero_offsets  # noqa: E402

from hardware.damiao import ARM_MOTORS, read_states  # noqa: E402

NAMES = [n for n, _, _ in ARM_MOTORS]
REF_FILE = ROOT / "calibration" / "zero_reference.json"
POUR_CONFIG = ROOT / "skills" / "pour" / "config" / "openarm_cocktail.yaml"
STOPS_AGREE_DEG = 1.0  # both stops give the same shift: trust them over the pose
POSE_VS_STOPS_DEG = 3.0  # beyond this the pose (marks) and the stops disagree: warn


def measure(buses: dict[str, can.BusABC]) -> dict:
    """Live view until Enter; returns per side the final pose and the min/max seen (motor deg)."""
    for side, bus in buses.items():
        on = [n for n, s in read_states(bus, timeout=0.2).items() if s.status == 0x1]
        if on:
            sys.exit(f"refused: {side} {on} are ENABLED (torque on). Run it with torque off only.")
    lo = {s: {n: math.inf for n in NAMES} for s in buses}
    hi = {s: {n: -math.inf for n in NAMES} for s in buses}
    pose = {}
    keys = stdin_lines()
    print("Torque off, hold the arms. 1) each joint to both stops, gently; 2) reference pose; Enter.\n")
    lines = 0
    while True:
        for side, bus in buses.items():
            states = read_states(bus, timeout=0.1)
            missing = [n for n in NAMES if n not in states]
            if missing:
                sys.exit(f"\n{side}: no answer from {missing}")
            pose[side] = {n: math.degrees(states[n].q) for n in NAMES}
            for n in NAMES:
                lo[side][n] = min(lo[side][n], pose[side][n])
                hi[side][n] = max(hi[side][n], pose[side][n])
        if lines:
            print(f"\033[{lines}F", end="")
        out = [f"{'':6}" + "".join(f"{n:>10}" for n in NAMES)]
        for side in buses:
            out.append(f"{side:6}" + "".join(f"{pose[side][n]:10.1f}" for n in NAMES))
            out.append(f"{'  min':6}" + "".join(f"{lo[side][n]:10.1f}" for n in NAMES))
            out.append(f"{'  max':6}" + "".join(f"{hi[side][n]:10.1f}" for n in NAMES))
        print("\n".join(out), flush=True)
        lines = len(out)
        if next_key(keys) is not None:
            return {s: {"pose": pose[s], "min": lo[s], "max": hi[s]} for s in buses}
        time.sleep(0.05)


def write_pour_offsets(offsets: dict) -> None:
    """joint_offsets of the pour config (rad, J1..J7 then gripper), comments kept."""
    text = POUR_CONFIG.read_text()
    for side in offsets:
        values = ", ".join(f"{math.radians(offsets[side].get(n, 0.0)):.5f}" for n in NAMES)
        text, n = re.subn(rf"(joint_offsets:(?:\n\s+\w+_arm: \[.*\])*?\n\s+{side}_arm: )\[.*\]",
                          rf"\g<1>[{values}]", text, count=1)
        if n != 1:
            sys.exit(f"{POUR_CONFIG}: no joint_offsets {side}_arm line, nothing written there")
    POUR_CONFIG.write_text(text)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", nargs="?", choices=["check", "save"], default="check")
    p.add_argument("--left", help="CAN channel of the left arm, e.g. can0")
    p.add_argument("--right", help="CAN channel of the right arm, e.g. can1")
    args = p.parse_args()
    channels = {s: c for s, c in (("left", args.left), ("right", args.right)) if c}
    if not channels:
        p.error("give --left and/or --right (./scripts/zero_check.sh does it)")
    if args.action == "check" and not REF_FILE.exists():
        p.error(f"no {REF_FILE.relative_to(ROOT)}: run 'save' first, while the zeros are ours")

    buses = {s: can.Bus(interface="socketcan", channel=c, fd=True) for s, c in channels.items()}
    try:
        seen = measure(buses)
    finally:
        for bus in buses.values():
            bus.shutdown()

    current = load_zero_offsets()
    if args.action == "save":
        ref = json.loads(REF_FILE.read_text()) if REF_FILE.exists() else {}
        ref["saved"] = datetime.now().isoformat(timespec="seconds")
        for side, m in seen.items():
            off = current.get(side, {})
            ref[side] = {k: {n: round(v[n] - off.get(n, 0.0), 2) for n in NAMES} for k, v in m.items()}
        REF_FILE.write_text(json.dumps(ref, indent=1) + "\n")
        print(f"\nReference saved to {REF_FILE.relative_to(ROOT)} (pose + stops, our frame).")
        return 0

    ref = json.loads(REF_FILE.read_text())
    offsets = {k: v for k, v in current.items() if k not in seen}
    warn = []
    print(f"\nOffsets vs the reference of {ref['saved']} (motor angle - ours, deg):")
    print(f"{'':16}{'pose':>8}{'stop lo':>9}{'stop hi':>9}{'used':>8}")
    for side, m in seen.items():
        r = ref[side]
        offsets[side] = {}
        for n in NAMES:
            d_pose = m["pose"][n] - r["pose"][n]
            d_lo, d_hi = m["min"][n] - r["min"][n], m["max"][n] - r["max"][n]
            stops = abs(d_lo - d_hi) <= STOPS_AGREE_DEG
            used = (d_lo + d_hi) / 2 if stops else d_pose
            if stops and abs(used - d_pose) > POSE_VS_STOPS_DEG:
                warn.append(f"{side} {n}: stops say {used:+.1f}, pose {d_pose:+.1f}")
            offsets[side][n] = round(used, 2)
            print(f"  {side:6}{n:<9}{d_pose:+8.1f}{d_lo:+9.1f}{d_hi:+9.1f}{used:+8.1f} "
                  f"{'(stops)' if stops else '(pose)'}")
    if warn:
        print("\nWarning: the reference pose and the stops disagree (marks misaligned?):\n  " + "\n  ".join(warn))
    offsets["saved"] = datetime.now().isoformat(timespec="seconds")
    if ZERO_FILE.exists():
        backup = ROOT / "calibration" / "backups" / f"zero_offsets_{datetime.now():%Y%m%d_%H%M%S}.json"
        backup.write_text(ZERO_FILE.read_text())
    ZERO_FILE.write_text(json.dumps(offsets, indent=1) + "\n")
    write_pour_offsets({s: offsets[s] for s in seen})
    print(f"\nWritten to {ZERO_FILE.relative_to(ROOT)} and {POUR_CONFIG.relative_to(ROOT)} "
          "(joint_offsets). Motors not written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
