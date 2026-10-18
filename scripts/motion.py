"""Teach a motion by moving the followers by hand, then replay it (hardcoded demos).

  ./scripts/motion.sh record pour_red                # torque off: move the arms by hand, Enter = stop
  ./scripts/motion.sh record pour_red --waypoints    # Enter = keep this pose, q + Enter = done
  ./scripts/motion.sh play pour_red                  # GO, slow move to the first pose, then the motion
  ./scripts/motion.sh play pour_red --speed 1.0      # recorded speed (default 0.5: half speed)
  ./scripts/motion.sh list

record is read-only (Damiao refresh only) and refuses motors that are enabled: torque must be off,
so support the arms while you move them. Positions are the followers' raw motor angles, saved in
motions/NAME.json. play reuses the teleop loop of teleop_safe.py: preflight against the first pose,
typed GO, gain ramp, approach at --approach-speed, then the motion with the --max-speed cap, the
measured joint limits and the usual safety stops. At the end it holds the last pose until Enter,
then releases torque (the arms go limp: hold them and the objects).
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rig import SimArm, drain, next_key, parse_can, stdin_lines  # noqa: E402
from teleop_safe import NAMES, Arm, Teleop, confirm_start, stop_on_signals  # noqa: E402

MOTIONS = Path(__file__).resolve().parent.parent / "motions"


def make_arms(args) -> list:
    if args.sim:
        return [SimArm(side) for side in ("left", "right")]
    pairs = [(side, pair) for side, pair in (("left", args.left), ("right", args.right)) if pair]
    if not pairs:
        sys.exit("give --left and/or --right CAN channels (./scripts/motion.sh does it), or --sim")
    return [Arm(side, *pair) for side, pair in pairs]


def connect(arms):
    for arm in arms:
        try:
            arm.connect()
        except OSError as e:
            sys.exit(f"{arm.side} arm: CAN channel {arm.can_channel} unavailable ({e.strerror}). Is the PCAN "
                     "attached to the VM (Parallels Devices > USB)? Then run ./scripts/setup_can.sh")


def read_pose(arms) -> dict:
    out = {}
    for arm in arms:
        states = arm.follower_states()
        missing = [n for n in NAMES if n not in states]
        if missing:
            raise RuntimeError(f"{arm.side}: no answer from {missing}")
        out[arm.side] = {n: round(math.degrees(states[n].q), 2) for n in NAMES}
    return out


def record(args) -> int:
    arms = make_arms(args)
    connect(arms)
    try:
        if not args.sim:
            for arm in arms:
                on = [n for n, s in arm.follower_states().items() if s.status == 0x1]
                if on:
                    print(f"refused: {arm.side} {on} are ENABLED (torque on). Record with torque off only.")
                    return 1
        keys = stdin_lines()
        frames, t0 = [], time.monotonic()
        if args.waypoints:
            print("Waypoints: put the arms in a pose, Enter = keep it; q + Enter = done.")
            while True:
                key = next_key(keys)
                if key == "q":
                    break
                if key is not None:
                    frames.append({"t": round(time.monotonic() - t0, 3), **read_pose(arms)})
                    print(f"  waypoint {len(frames)} saved")
                time.sleep(0.05)
        else:
            print(f"Recording at {args.hz:.0f} Hz: move the arms by hand (torque is off). Enter = stop.")
            dt = 1.0 / args.hz
            while next_key(keys) is None:
                start = time.monotonic()
                frames.append({"t": round(start - t0, 3), **read_pose(arms)})
                if len(frames) % int(args.hz) == 0:
                    print(f"\r  {frames[-1]['t']:5.1f} s, {len(frames)} samples", end="", flush=True)
                time.sleep(max(0.0, dt - (time.monotonic() - start)))
            print()
    finally:
        for arm in arms:
            arm.disconnect()
    if len(frames) < 2:
        print("Not saved: fewer than 2 poses.")
        return 1
    MOTIONS.mkdir(exist_ok=True)
    path = MOTIONS / f"{args.name}.json"
    path.write_text(json.dumps({"saved": datetime.now().isoformat(timespec="seconds"),
                                "kind": "waypoints" if args.waypoints else "trajectory",
                                "arms": [a.side for a in arms], "frames": frames}, indent=1) + "\n")
    print(f"Saved {len(frames)} {'waypoints' if args.waypoints else 'samples'} "
          f"({frames[-1]['t']:.1f} s) to {path.relative_to(MOTIONS.parent)}")
    return 0


def smooth(frames: list, window: int) -> list:
    """Centered moving average: removes the hand's jitter, keeps the timing."""
    if window <= 1:
        return frames
    out = []
    for i, f in enumerate(frames):
        lo, hi = max(0, i - window // 2), min(len(frames), i + window // 2 + 1)
        avg = {side: {n: sum(frames[k][side][n] for k in range(lo, hi)) / (hi - lo) for n in NAMES}
               for side in f if side != "t"}
        out.append({"t": f["t"], **avg})
    return out


def waypoints_to_trajectory(frames: list, sides: list, deg_per_s: float, dwell_s: float) -> list:
    """Straight joint-space moves between waypoints at deg_per_s (slowest joint sets the time)."""
    traj, t = [{"t": 0.0, **{s: frames[0][s] for s in sides}}], 0.0
    for a, b in zip(frames, frames[1:]):
        t += dwell_s
        traj.append({"t": t, **{s: a[s] for s in sides}})
        span = max(abs(b[s][n] - a[s][n]) for s in sides for n in NAMES)
        t += max(span / deg_per_s, 0.1)
        traj.append({"t": t, **{s: b[s] for s in sides}})
    traj.append({"t": t + dwell_s, **{s: frames[-1][s] for s in sides}})
    return traj


def pose_at(traj: list, t: float, sides: list) -> dict:
    """Linear interpolation of the trajectory at time t (clamped to its ends)."""
    if t <= traj[0]["t"]:
        return {s: dict(traj[0][s]) for s in sides}
    for a, b in zip(traj, traj[1:]):
        if t <= b["t"]:
            u = (t - a["t"]) / max(b["t"] - a["t"], 1e-9)
            return {s: {n: a[s][n] + u * (b[s][n] - a[s][n]) for n in NAMES} for s in sides}
    return {s: dict(traj[-1][s]) for s in sides}


def play(args) -> int:
    path = MOTIONS / f"{args.name}.json"
    if not path.exists():
        print(f"no {path.relative_to(MOTIONS.parent)}: ./scripts/motion.sh list")
        return 1
    data = json.loads(path.read_text())
    arms = make_arms(args)
    sides = [a.side for a in arms]
    missing = [s for s in sides if s not in data["arms"]]
    if missing:
        print(f"{path.name} has no {missing} arm (recorded: {data['arms']})")
        return 1
    if data["kind"] == "waypoints":
        traj = waypoints_to_trajectory(data["frames"], sides, args.wp_speed, args.dwell)
    else:
        traj = smooth(data["frames"], args.smooth)
    duration = traj[-1]["t"] / args.speed
    print(f"{path.name}: {data['kind']}, {len(data['frames'])} poses, {duration:.1f} s at x{args.speed}")

    current = pose_at(traj, 0.0, sides)
    started = False
    connect(arms)
    try:
        if not args.sim and not confirm_start(arms, args.approach_speed, targets=lambda arm: current[arm.side]):
            return 1
        started = True
        keys = stdin_lines()
        teleop = Teleop(arms, args.fps, args.max_speed, args.approach_speed, args.gain_scale, args.ramp,
                        targets=lambda arm: current[arm.side])
        teleop.start()
        while not teleop.synced:
            start = time.monotonic()
            teleop.step()
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))

        drain(keys)
        print("Playing. Enter = stop here (hold the pose), Ctrl+C = stop and release torque.")
        t0, reason = time.monotonic(), "end of the motion"
        while True:
            start = time.monotonic()
            t = (start - t0) * args.speed
            current.update(pose_at(traj, t, sides))
            teleop.step()
            if t > traj[-1]["t"]:
                break
            if next_key(keys) is not None:
                reason = "Enter"
                break
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))
        for _ in range(int(2.0 / teleop.dt)):  # let the follower reach the last target
            start = time.monotonic()
            teleop.step()
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))
        print(f"Stopped ({reason}).\n{teleop.summary()}")
        if args.sim:
            return 0
        drain(keys)
        print("Holding the last pose. Enter = release torque (the arms go limp: hold them and the objects).")
        while next_key(keys) is None:
            start = time.monotonic()
            teleop.hold()
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))
    except KeyboardInterrupt:
        print("\nStopping.")
    except Exception as e:  # noqa: BLE001
        print(f"\nSAFETY STOP: {e}")
    finally:
        for arm in arms:
            arm.disconnect()
        if started and not args.sim:
            print("Warning: could not confirm torque off." if any(a.enabled for a in arms) else "Torque disabled.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["record", "play", "list"])
    p.add_argument("name", nargs="?", help="motion name (motions/NAME.json)")
    p.add_argument("--left", type=parse_can, help="CAN channel of the left arm, e.g. can0")
    p.add_argument("--right", type=parse_can, help="CAN channel of the right arm, e.g. can1")
    p.add_argument("--sim", action="store_true", help="fake arms (no hardware)")
    p.add_argument("--waypoints", action="store_true", help="record: keep a pose on each Enter")
    p.add_argument("--hz", type=float, default=50.0, help="record: sampling rate")
    p.add_argument("--speed", type=float, default=0.5, help="play: time scale (1.0 = as recorded)")
    p.add_argument("--smooth", type=int, default=9, help="play: moving-average window, samples")
    p.add_argument("--wp-speed", type=float, default=20.0, help="play: deg/s between waypoints")
    p.add_argument("--dwell", type=float, default=0.5, help="play: pause on each waypoint, s")
    p.add_argument("--fps", type=float, default=60.0, help="play: control loop rate")
    p.add_argument("--max-speed", type=float, default=30.0, help="play: per-joint speed cap, deg/s")
    p.add_argument("--approach-speed", type=float, default=10.0)
    p.add_argument("--gain-scale", type=float, default=0.3)
    p.add_argument("--ramp", type=float, default=2.0)
    args = p.parse_args()
    stop_on_signals()
    if args.action == "list":
        for f in sorted(MOTIONS.glob("*.json")):
            d = json.loads(f.read_text())
            print(f"  {f.stem:20} {d['kind']:10} {len(d['frames']):5} poses  {d['frames'][-1]['t']:6.1f} s  "
                  f"arms {','.join(d['arms'])}  ({d['saved']})")
        return 0
    if not args.name:
        p.error("give a motion name")
    return record(args) if args.action == "record" else play(args)


if __name__ == "__main__":
    raise SystemExit(main())
