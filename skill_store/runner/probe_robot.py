#!/usr/bin/env python3
"""Run this in your first ten minutes of robot access.

The SDK API reference does not publish observation keys or the action schema, so
introspect them instead of reading. Paste the output into runner/moz1.py.

    python runner/probe_robot.py --structure dualarm --no-camera
"""
from __future__ import annotations

import argparse
import os


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--structure", default="dualarm",
                    choices=["dualarm", "wholebody_without_base", "wholebody"])
    ap.add_argument("--no-camera", action="store_true",
                    help="skip RealSense init (faster, and works without serials)")
    ap.add_argument("--serials", default=os.environ.get("REALSENSE_SERIALS", ""),
                    help="head,left_wrist,right_wrist")
    ap.add_argument("--hz", type=int, default=120)
    args = ap.parse_args()

    try:
        from mozrobot import MOZ1Robot, MOZ1RobotConfig
    except ImportError:
        print("mozrobot is not installed in this interpreter.")
        print("It must live OUTSIDE the openpi uv env -- system python or the")
        print("examples/moz1_real Docker image. See docs.spirit-ai.com/open-resources/pi.html")
        return 1

    cfg = MOZ1RobotConfig(
        realsense_serials=args.serials or "0000000000,0000000000,0000000000",
        camera_resolutions="640*480,640*480,640*480",
        structure=args.structure,
        robot_control_hz=args.hz,
        no_camera=args.no_camera,
    )
    robot = MOZ1Robot(cfg)
    robot.connect()
    print(f"connected={robot.is_robot_connected}  control_hz={robot.control_hz}")
    print(f"structure={args.structure}  cameras={'off' if args.no_camera else 'on'}")

    obs = robot.capture_observation()
    print(f"\ncapture_observation() -> {type(obs).__name__} with {len(obs)} keys\n")
    for key in sorted(obs):
        val = obs[key]
        shape = getattr(val, "shape", None)
        if shape is not None:
            desc = f"array{tuple(shape)} dtype={getattr(val, 'dtype', '?')}"
        elif isinstance(val, (list, tuple)):
            desc = f"{type(val).__name__}[{len(val)}] e.g. {list(val)[:4]}"
        else:
            desc = f"{type(val).__name__} = {val!r}"
        print(f"  {key:<42} {desc}")

    print("\nMap these into _to_policy_obs / _to_action in runner/moz1.py.")
    print("Units are SI: radians, metres, seconds. Rotations are rotation vectors.")
    robot.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
