"""Reference ("home") pose of the 4 arms: save it once, then check you are back in it. Read-only.

  ./scripts/home.sh --save      # record the current pose of leaders and followers as home
  ./scripts/home.sh             # live view: every joint should read ~0 (delta to home), Ctrl+C
  ./scripts/home.sh --once      # one reading; exit code 0 if every joint is within --tol (15 deg)

Followers are stored as raw motor angles and leaders as raw readings (before flips/offsets), so
changing the teleop calibration does not move the home pose. Never enables torque.
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from teleop_safe import NAMES, Arm, parse_pair  # noqa: E402

HOME_FILE = Path(__file__).resolve().parent.parent / "calibration" / "home_pose.json"


def read(arms: list[Arm], seconds: float = 0.5) -> dict:
    """Average over `seconds`: {side: {"follower": {joint: deg}, "leader": {joint: raw}}}."""
    sums = {a.side: {"follower": {n: 0.0 for n in NAMES}, "leader": {n: 0.0 for n in NAMES}} for a in arms}
    count = 0
    t0 = time.monotonic()
    while count == 0 or time.monotonic() - t0 < seconds:
        for a in arms:
            states, raw = a.follower_states(), a.leader.get_action()
            for n in NAMES:
                sums[a.side]["follower"][n] += math.degrees(states[n].q)
                sums[a.side]["leader"][n] += raw[f"{n}.pos"]
        count += 1
        time.sleep(0.05)
    return {s: {k: {n: round(v / count, 1) for n, v in d.items()} for k, d in parts.items()}
            for s, parts in sums.items()}


def wrap(d: float) -> float:
    return (d + 180.0) % 360.0 - 180.0


def table(now: dict, home: dict, tol: float) -> bool:
    ok = True
    print(f"{'':10}" + "".join(f"{s + ' ' + k:>18}" for s in now for k in ("follower", "leader")))
    for n in NAMES:
        cells = []
        for s in now:
            for k in ("follower", "leader"):
                d = wrap(now[s][k][n] - home[s][k][n])
                bad = abs(d) > tol
                ok &= not bad
                cells.append(f"{d:+8.1f}{' <--' if bad else '    '}      ")
        print(f"{n:10}" + "".join(cells))
    print(("ALL AT HOME" if ok else f"not at home: move the joints marked <-- toward 0") + f" (tolerance {tol:.0f} deg)")
    return ok


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--left", type=parse_pair, help="LEADER_PORT:CAN_CHANNEL of the left arm")
    p.add_argument("--right", type=parse_pair, help="LEADER_PORT:CAN_CHANNEL of the right arm")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--save", action="store_true", help="record the current pose as home")
    mode.add_argument("--once", action="store_true", help="one reading, exit 0 if at home")
    p.add_argument("--tol", type=float, default=15.0, help="deg, per joint")
    p.add_argument("--note", default="", help="free text saved with --save")
    args = p.parse_args()

    arms = [Arm(side, *pair) for side, pair in (("left", args.left), ("right", args.right)) if pair]
    if not arms:
        p.error("give --left and/or --right (./scripts/home.sh does it from ports.sh)")
    for a in arms:
        a.connect()
    try:
        if args.save:
            pose = read(arms, 1.0)
            HOME_FILE.write_text(json.dumps({"saved": datetime.now().isoformat(timespec="seconds"),
                                             "note": args.note, **pose}, indent=2) + "\n")
            print(f"home pose saved to {HOME_FILE.relative_to(HOME_FILE.parent.parent)}")
            for s in pose:
                print(f"  {s} follower: " + "  ".join(f"{n[-1] if n != 'gripper' else 'g'}={v:+.1f}"
                                                      for n, v in pose[s]["follower"].items()))
            return 0
        if not HOME_FILE.exists():
            print(f"no {HOME_FILE.name} yet: run ./scripts/home.sh --save in the reference pose")
            return 1
        home = json.loads(HOME_FILE.read_text())
        print(f"home pose of {home['saved']} {home.get('note', '')}\n")
        if args.once:
            return 0 if table(read(arms), home, args.tol) else 2
        print("\033[2J", end="")  # clear once, then redraw in place: no flicker
        while True:
            now = read(arms, 1.0)
            print("\033[H", end="")
            print(f"Delta to the home pose of {home['saved']} (deg), refreshed every second. Ctrl+C to stop.\n")
            table(now, home, args.tol)
            print("\033[J", end="", flush=True)
    except KeyboardInterrupt:
        return 0
    finally:
        for a in arms:
            a.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
