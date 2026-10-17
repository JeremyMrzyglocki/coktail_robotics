"""Zero calibration of some or all motors of one OpenArm arm over socketcan. Never enables torque.

Reference pose (same as LeRobot's openarm_follower): arm hanging straight down, gripper closed,
each joint in the middle of its travel. With --joints only those motors get a new zero, e.g. a
wrist whose zero sits at one end of its travel:

  uv run python scripts/calibrate_zero.py --can can0 --joints joint_5

Shows the selected joints live while you place the arm by hand (torque off), then writes the new
zero only after you type ZERO. The previous positions are saved in calibration/backups/.
"""

import argparse
import json
import math
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import can  # noqa: E402

from hardware.damiao import ARM_MOTORS, collect_states, read_states, send_disable, send_set_zero  # noqa: E402

NAMES = [name for name, _, _ in ARM_MOTORS]
ZERO_TOLERANCE_DEG = 1.0


def print_states(states, names):
    for name in names:
        s = states.get(name)
        print(f"  {name:<9} -- no answer --" if s is None else
              f"  {name:<9}{math.degrees(s.q):>8.1f} deg   {s.status_name}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--can", required=True, help="CAN channel of the arm, e.g. can0")
    p.add_argument("--joints", nargs="+", choices=NAMES, default=NAMES, help="motors to zero (default: all 8)")
    args = p.parse_args()
    selected = [n for n in NAMES if n in args.joints]
    motors = [m for m in ARM_MOTORS if m[0] in selected]

    bus = can.Bus(interface="socketcan", channel=args.can, fd=True)
    try:
        # Disable is a no-op on an idle motor and guarantees torque is off; it also returns state.
        for _, send_id, _ in ARM_MOTORS:
            send_disable(bus, send_id)
        before = collect_states(bus, ARM_MOTORS, timeout=0.3)
        print(f"\nCurrent positions ({args.can}, torque OFF):")
        print_states(before, NAMES)
        missing = [n for n in selected if n not in before]
        faults = [n for n in selected if n in before and before[n].status >= 0x8]
        if missing or faults:
            print(f"\nAbort: missing={missing} faults={faults}. Nothing was written.")
            return 1

        print(f"\nPlace {', '.join(selected)} at the reference pose by hand (middle of the travel; "
              "arm hanging, gripper closed). Live values below; press Enter when in place.")
        done = threading.Event()
        threading.Thread(target=lambda: (input(), done.set()), daemon=True).start()
        while not done.is_set():
            states = read_states(bus, motors, timeout=0.1)
            live = "  ".join(f"{n} {math.degrees(states[n].q):7.1f}" if n in states else f"{n} --" for n in selected)
            print(f"\r  {live}   ", end="", flush=True)
            time.sleep(0.2)
        before = read_states(bus, motors, timeout=0.3)

        print(f"\nThis overwrites the zero stored in: {', '.join(selected)} on {args.can}.")
        if input("Type ZERO to write, anything else to abort: ").strip() != "ZERO":
            print("Aborted. Nothing was written.")
            return 0

        backup = ROOT / "calibration" / "backups" / f"{args.can}_before_zero_{datetime.now():%Y%m%d_%H%M%S}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps({n: {"rad": s.q, "deg": math.degrees(s.q)} for n, s in before.items()},
                                     indent=2))

        for _, send_id, _ in motors:
            send_set_zero(bus, send_id)
            time.sleep(0.05)
        while bus.recv(timeout=0.2) is not None:  # drain replies
            pass

        after = read_states(bus, timeout=0.3)
        print("\nPositions after zeroing:")
        print_states(after, NAMES)
        off = [n for n in selected if n in after and abs(math.degrees(after[n].q)) > ZERO_TOLERANCE_DEG]
        missing = [n for n in selected if n not in after]
        if off or missing:
            print(f"\nCheck needed: not at zero={off} missing={missing}")
            return 1
        print(f"\nDone. Previous positions saved to {backup.relative_to(ROOT)}")
        return 0
    finally:
        bus.shutdown()


if __name__ == "__main__":
    sys.exit(main())
