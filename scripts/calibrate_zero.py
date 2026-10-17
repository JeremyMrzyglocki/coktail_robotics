"""Zero calibration of one OpenArm arm (the one on PCAN CAN1). Never enables torque.

Same reference pose as LeRobot's openarm_follower calibration:
arm hanging straight down, gripper closed.

Usage:  .venv/bin/python scripts/calibrate_zero.py --arm right
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hardware.damiao import (  # noqa: E402
    ARM_MOTORS, collect_states, open_bus, read_states, send_disable, send_set_zero,
)

CHANNEL = "PCAN_USBBUS1"
ZERO_TOLERANCE_DEG = 1.0


def print_states(states):
    for name, _, _ in ARM_MOTORS:
        s = states.get(name)
        if s is None:
            print(f"  {name:<9} -- no answer --")
        else:
            print(f"  {name:<9}{math.degrees(s.q):>8.1f} deg   {s.status_name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=["left", "right"], required=True)
    args = parser.parse_args()

    bus = open_bus(CHANNEL)
    try:
        # Disable is a no-op on an idle motor and guarantees torque is off; it also returns state.
        for _, send_id, _ in ARM_MOTORS:
            send_disable(bus, send_id)
        before = collect_states(bus, ARM_MOTORS, timeout=0.3)

        print(f"\nCurrent positions ({args.arm} arm, torque OFF):")
        print_states(before)

        missing = [n for n, _, _ in ARM_MOTORS if n not in before]
        faults = [n for n, s in before.items() if s.status >= 0x8]
        if missing or faults:
            print(f"\nAbort: missing={missing} faults={faults}. Nothing was written.")
            return 1

        print("\nPlace the arm hanging straight down, gripper fully closed.")
        print("This overwrites the zero stored in all 8 motors of this arm.")
        if input("Type ZERO to write, anything else to abort: ").strip() != "ZERO":
            print("Aborted. Nothing was written.")
            return 0

        backup = ROOT / "calibration" / "backups" / f"{args.arm}_before_zero_{datetime.now():%Y%m%d_%H%M%S}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps({n: s.q for n, s in before.items()}, indent=2))

        for _, send_id, _ in ARM_MOTORS:
            send_set_zero(bus, send_id)
            time.sleep(0.05)
        bus.recv(timeout=0.2)  # drain replies

        after = read_states(bus, timeout=0.3)
        print("\nPositions after zeroing:")
        print_states(after)
        off = [n for n, s in after.items() if abs(math.degrees(s.q)) > ZERO_TOLERANCE_DEG]
        missing = [n for n, _, _ in ARM_MOTORS if n not in after]
        if off or missing:
            print(f"\nCheck needed: not at zero={off} missing={missing}")
            return 1
        print(f"\nDone. Previous positions saved to {backup.relative_to(ROOT)}")
        return 0
    finally:
        bus.shutdown()


if __name__ == "__main__":
    sys.exit(main())
