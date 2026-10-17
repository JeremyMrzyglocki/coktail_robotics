"""Shared setup for record.py and run_policy.py: arms, cameras, fakes for --sim, keyboard input."""

import argparse
import logging
import math
import queue
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
# On the aarch64 VM torchcodec cannot load (no CUDA libs) and LeRobot falls back to pyav, after a
# multi-screen traceback that would bury real messages. Only that one warning is silenced.
logging.getLogger("lerobot.utils.import_utils").setLevel(logging.ERROR)

from teleop_safe import JOINT_LIMITS, NAMES, Arm, parse_pair  # noqa: E402

from hardware.damiao import MotorState  # noqa: E402
from lerobot.cameras.opencv import OpenCVCamera, OpenCVCameraConfig  # noqa: E402

ROBOT_TYPE = "bi_openarm_follower"
SIM_HZ = 0.05  # fake leader: 20 deg sine at 0.05 Hz peaks at ~6 deg/s, below the approach speed


class SimArm(Arm):
    """Fake arm: the leader draws slow sine waves, the follower tracks the commands exactly."""

    def __init__(self, side: str):
        self.side = side
        self.can_channel = "sim"
        self.limits = JOINT_LIMITS[side]
        self.leader = SimpleNamespace(config=SimpleNamespace(port="sim"))
        self.flips = set()
        self.enabled = False
        self.q = {n: 0.0 for n in NAMES}
        self.t0 = time.monotonic()

    def connect(self):
        pass

    def disconnect(self, keep_torque: bool = False):
        self.enabled = self.enabled and keep_torque

    def leader_targets(self):
        t = time.monotonic() - self.t0
        out = {n: 20.0 * math.sin(2 * math.pi * SIM_HZ * t + i) for i, n in enumerate(NAMES)}
        out["joint_4"] = 20.0 + 20.0 * math.sin(2 * math.pi * SIM_HZ * t)
        out["gripper"] = -30.0 + 30.0 * math.cos(2 * math.pi * SIM_HZ * t)
        return out

    def follower_states(self):
        return {n: MotorState(math.radians(self.q[n]), 0.0, 0.0, 30, 30, 0x1 if self.enabled else 0x0)
                for n in NAMES}

    def enable_and_hold(self, hold_deg, scale):
        self.enabled = True
        return self.command(hold_deg, scale)

    def command(self, cmd_deg, scale):
        self.q.update(cmd_deg)
        return self.follower_states()

    def disable(self):
        self.enabled = False


class SimCamera:
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.i = 0

    def connect(self):
        pass

    def disconnect(self):
        pass

    def read_latest(self):
        self.i += 1
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        img[:, :, 0] = (np.arange(self.width) + self.i * 4) % 256
        img[:, :, 1] = (np.arange(self.height)[:, None] + self.i * 2) % 256
        return img


def parse_camera(value: str) -> tuple[str, str]:
    name, sep, index = value.partition("=")
    if not sep:
        raise argparse.ArgumentTypeError("expected NAME=INDEX_OR_PATH, e.g. top=0 or wrist=/dev/video2")
    return name, index


def parse_can(value: str) -> tuple[None, str]:
    return None, value


def add_rig_args(p: argparse.ArgumentParser, with_leader: bool = True):
    if with_leader:
        p.add_argument("--left", type=parse_pair, help="LEADER_PORT:CAN_CHANNEL of the left arm")
        p.add_argument("--right", type=parse_pair, help="LEADER_PORT:CAN_CHANNEL of the right arm")
    else:
        p.add_argument("--left", type=parse_can, help="CAN channel of the left arm, e.g. can0")
        p.add_argument("--right", type=parse_can, help="CAN channel of the right arm, e.g. can1")
    p.add_argument("--sim", action="store_true", help="fake arms and cameras (no hardware)")
    p.add_argument("--camera", type=parse_camera, action="append", default=[],
                   help="NAME=INDEX_OR_PATH, repeatable (see `uv run lerobot-find-cameras opencv`)")
    p.add_argument("--cam-width", type=int, default=640)
    p.add_argument("--cam-height", type=int, default=480)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--max-speed", type=float, default=30.0, help="per-joint speed cap, deg/s")
    p.add_argument("--approach-speed", type=float, default=10.0,
                   help="per-joint speed while moving to the first target, deg/s")
    p.add_argument("--gain-scale", type=float, default=0.3, help="fraction of LeRobot's kp/kd")
    p.add_argument("--ramp", type=float, default=2.0, help="gain ramp-up duration, s")


def build_rig(p: argparse.ArgumentParser, args) -> tuple[list[Arm], dict]:
    """Arms and cameras from the parsed args (fakes with --sim). Nothing is connected yet."""
    pairs = [(side, pair) for side, pair in (("left", args.left), ("right", args.right)) if pair]
    if args.sim:
        arms = [SimArm(side) for side in ("left", "right")]
        cameras = {name: SimCamera(args.cam_width, args.cam_height) for name, _ in args.camera}
        return arms, cameras
    if not pairs:
        p.error("give --left and/or --right, or --sim")
    arms = [Arm(side, *pair) for side, pair in pairs]
    cameras = {name: OpenCVCamera(OpenCVCameraConfig(
        index_or_path=int(index) if index.isdigit() else Path(index),
        fps=args.fps, width=args.cam_width, height=args.cam_height)) for name, index in args.camera}
    return arms, cameras


def joint_keys(arms: list[Arm]) -> list[str]:
    """Dataset/policy vector order: bi_openarm_follower names, left arm first."""
    return [f"{arm.side}_{n}.pos" for arm in arms for n in NAMES]


def stdin_lines() -> queue.Queue:
    """Collect typed lines in the background so the control loop never blocks on the keyboard."""
    q: queue.Queue = queue.Queue()

    def reader():
        for line in sys.stdin:
            q.put(line.strip().lower())

    threading.Thread(target=reader, daemon=True).start()
    return q


def next_key(keys: queue.Queue) -> str | None:
    try:
        return keys.get_nowait()
    except queue.Empty:
        return None


def drain(keys: queue.Queue):
    """Drop lines typed earlier (e.g. an Enter pressed while the arm was still approaching)."""
    while next_key(keys) is not None:
        pass
