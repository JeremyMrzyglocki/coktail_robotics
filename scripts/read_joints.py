"""Read-only check: print the state of every OpenArm motor on each PCAN channel.

Never enables torque. Usage:  .venv/bin/python scripts/read_joints.py
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hardware.damiao import ARM_MOTORS, open_bus, read_states  # noqa: E402

CHANNELS = ["PCAN_USBBUS1", "PCAN_USBBUS2"]


def main():
    for channel in CHANNELS:
        print(f"\n=== {channel} ===")
        try:
            bus = open_bus(channel)
        except Exception as e:  # noqa: BLE001
            print(f"  cannot open: {e}")
            continue
        try:
            states = read_states(bus, timeout=0.2)
            print(f"  {'motor':<9}{'pos rad':>9}{'pos deg':>9}{'vel':>8}{'torque':>8}"
                  f"{'T mos':>7}{'T rot':>7}  status")
            for name, _, _ in ARM_MOTORS:
                s = states.get(name)
                if s is None:
                    print(f"  {name:<9}  -- no answer --")
                    continue
                print(f"  {name:<9}{s.q:>9.3f}{math.degrees(s.q):>9.1f}{s.dq:>8.2f}{s.tau:>8.2f}"
                      f"{s.t_mos:>7}{s.t_rotor:>7}  {s.status_name}")
        finally:
            bus.shutdown()


if __name__ == "__main__":
    main()
