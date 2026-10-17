"""Read-only: measure a follower's real joint range by moving it by hand (torque must be off).

Move each listed joint slowly to both mechanical stops while it runs; the min/max seen are printed
and saved to calibration/measured_range_<side>.json. Never enables torque (Damiao refresh only).

  uv run python scripts/measure_range.py --side right --joints joint_3 joint_5 --seconds 60
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import can  # noqa: E402

from hardware.damiao import ARM_MOTORS, read_states  # noqa: E402

CAN = {"left": "can0", "right": "can1"}  # as in scripts/ports.sh


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--side", choices=sorted(CAN), required=True)
    p.add_argument("--joints", nargs="+", default=[n for n, _, _ in ARM_MOTORS])
    p.add_argument("--seconds", type=float, default=60.0)
    args = p.parse_args()

    bus = can.Bus(interface="socketcan", channel=CAN[args.side], fd=True)
    lo = {n: math.inf for n in args.joints}
    hi = {n: -math.inf for n in args.joints}
    try:
        first = read_states(bus, ARM_MOTORS, timeout=0.1)
        enabled = [n for n, s in first.items() if s.status == 0x1]
        if enabled:
            print(f"refused: {enabled} are ENABLED (torque on). Measure with torque off only.")
            return 1
        print(f"{args.side} follower on {CAN[args.side]}: move each joint to both stops, slowly. Ctrl+C ends early.")
        t0 = time.monotonic()
        while time.monotonic() - t0 < args.seconds:
            states = read_states(bus, ARM_MOTORS, timeout=0.05)
            parts = []
            for n in args.joints:
                if n in states:
                    deg = math.degrees(states[n].q)
                    lo[n], hi[n] = min(lo[n], deg), max(hi[n], deg)
                    parts.append(f"{n} {deg:7.1f} [{lo[n]:6.1f},{hi[n]:6.1f}]")
            print("\r" + "  ".join(parts) + f"  {args.seconds - (time.monotonic() - t0):4.0f}s ", end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        bus.shutdown()
    print()
    out = {n: [round(lo[n], 1), round(hi[n], 1)] for n in args.joints if lo[n] <= hi[n]}
    for n, (a, b) in out.items():
        print(f"  {n}: {a:+.1f} .. {b:+.1f} deg")
    path = ROOT / "calibration" / f"measured_range_{args.side}.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"saved {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
