"""Shared setup for record.py and run_policy.py: arms, cameras, fakes for --sim, keyboard input."""

import argparse
import logging
import math
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
# On the aarch64 VM torchcodec cannot load (no CUDA libs) and LeRobot falls back to pyav, after a
# multi-screen traceback that would bury real messages. Only that one warning is silenced.
logging.getLogger("lerobot.utils.import_utils").setLevel(logging.ERROR)

from teleop_safe import JOINT_LIMITS, NAMES, Arm, parse_pair  # noqa: E402

from hardware.damiao import MotorState  # noqa: E402
from lerobot.cameras import Cv2Rotation  # noqa: E402
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

    def command(self, cmd_deg, scale, vel_dps=None):
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

    def read_latest_depth(self):
        """Fake depth in mm (uint16, H x W x 1): a slope from 300 to 1500 mm."""
        ramp = np.linspace(300, 1500, self.width, dtype=np.uint16)
        return np.broadcast_to(ramp, (self.height, self.width))[..., None].copy()


@dataclass
class CameraSpec:
    """NAME=SOURCE[,rotate=DEG][,zoom=X][,depth] from the command line.

    SOURCE: an OpenCV index or /dev/video* path, or realsense[:SERIAL] (librealsense; the only
    way to get depth). The D455 colour stream also works as a plain OpenCV/UVC device, which needs
    no librealsense (its aarch64 wheels need glibc 2.38, i.e. Ubuntu 24.04).
    """

    name: str
    source: str
    rotate: int = 0
    depth: bool = False
    zoom: float = 1.0  # centre crop of 1/zoom of the image, resized back: same frame size

    @property
    def realsense(self) -> bool:
        return self.source.split(":")[0] == "realsense"

    def frame_shape(self, width: int, height: int) -> tuple[int, int]:
        """(H, W) of the frames after rotation."""
        return (width, height) if self.rotate in (90, 270) else (height, width)


def parse_camera(value: str) -> CameraSpec:
    name, sep, rest = value.partition("=")
    if not sep or not rest:
        raise argparse.ArgumentTypeError(
            "expected NAME=SOURCE[,rotate=180][,zoom=1.1][,depth], e.g. top=0, top=/dev/video4,rotate=180 "
            "or top=realsense,rotate=180,depth")
    source, *opts = rest.split(",")
    spec = CameraSpec(name, source)
    for opt in opts:
        key, _, val = opt.partition("=")
        if key == "rotate" and val in ("0", "90", "180", "270"):
            spec.rotate = int(val)
        elif key == "depth" and not val:
            spec.depth = True
        elif key == "zoom" and val.replace(".", "", 1).isdigit() and float(val) >= 1.0:
            spec.zoom = float(val)
        else:
            raise argparse.ArgumentTypeError(
                f"camera {name}: unknown option '{opt}' (rotate=0|90|180|270, zoom=X with X >= 1, depth)")
    if spec.depth and not spec.realsense:
        raise argparse.ArgumentTypeError(f"camera {name}: depth needs a realsense source")
    return spec


def make_camera(spec: CameraSpec, args):
    rotation = Cv2Rotation(-90 if spec.rotate == 270 else spec.rotate)
    if spec.realsense:
        # Imported here: pyrealsense2 only loads on glibc >= 2.38 on aarch64.
        from lerobot.cameras.realsense import RealSenseCamera, RealSenseCameraConfig

        serial = spec.source.partition(":")[2] or "Intel RealSense D455"
        return RealSenseCamera(RealSenseCameraConfig(
            serial_number_or_name=serial, fps=args.fps, width=args.cam_width, height=args.cam_height,
            rotation=rotation, use_depth=spec.depth))
    source = spec.source
    # OpenCV opens a /dev/video* path (or a /dev/v4l/by-id link) with its FFMPEG backend, which
    # refuses the capture size, and LeRobot then fails to set the width. Only an index uses V4L2.
    video = re.fullmatch(r"/dev/video(\d+)", str(Path(source).resolve())) if source.startswith("/dev/") else None
    if video:
        source = video.group(1)
    return OpenCVCamera(OpenCVCameraConfig(
        index_or_path=int(source) if source.isdigit() else Path(source),
        fps=args.fps, width=args.cam_width, height=args.cam_height, rotation=rotation))


def image_features(specs: list[CameraSpec], width: int, height: int) -> dict[str, tuple[int, int, int]]:
    """Camera features as hw_to_dataset_features expects them: name -> (H, W, C)."""
    out = {}
    for spec in specs:
        h, w = spec.frame_shape(width, height)
        out[spec.name] = (h, w, 3)
        if spec.depth:
            out[f"{spec.name}_depth"] = (h, w, 1)
    return out


def zoom_center(img: np.ndarray, factor: float, nearest: bool = False) -> np.ndarray:
    """Digital zoom: keep the central 1/factor of the image and resize it back to the same size."""
    if factor <= 1.0:
        return img
    import cv2

    h, w = img.shape[:2]
    ch, cw = round(h / factor), round(w / factor)
    y, x = (h - ch) // 2, (w - cw) // 2
    out = cv2.resize(img[y:y + ch, x:x + cw], (w, h), interpolation=cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR)
    return out.reshape(img.shape)


def read_images(cameras: dict, specs: list[CameraSpec]) -> dict:
    """{feature name: frame}: RGB for every camera, plus NAME_depth for depth cameras (zoom applied)."""
    out = {}
    for spec in specs:
        cam = cameras[spec.name]
        out[spec.name] = zoom_center(cam.read_latest(), spec.zoom)
        if spec.depth:
            out[f"{spec.name}_depth"] = zoom_center(cam.read_latest_depth(), spec.zoom, nearest=True)
    return out


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
                   help="NAME=SOURCE[,rotate=180][,depth], repeatable; SOURCE = OpenCV index or /dev/video*, or "
                        "realsense[:SERIAL] (see `uv run lerobot-find-cameras opencv`)")
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
        cameras = {spec.name: SimCamera(*spec.frame_shape(args.cam_width, args.cam_height)[::-1])
                   for spec in args.camera}
        return arms, cameras
    if not pairs:
        p.error("give --left and/or --right, or --sim")
    arms = [Arm(side, *pair) for side, pair in pairs]
    cameras = {spec.name: make_camera(spec, args) for spec in args.camera}
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
