"""Preview a USB (UVC / OpenCV) camera as record.py sees it. Press q to quit.

Opens the camera with the same spec and LeRobot OpenCVCamera as the recordings, so the rotation,
resolution and frame rate shown here are what ends up in the dataset (`--camera` of record.py,
CAMERAS in scripts/ports.sh). For the D455 with depth, use realsense_preview.py.

Usage:
  uv run scripts/usb_camera_preview.py --list                        # cameras OpenCV can open
  uv run scripts/usb_camera_preview.py 0                             # index or /dev/videoN
  uv run scripts/usb_camera_preview.py /dev/video4,rotate=180        # same options as --camera
  uv run scripts/usb_camera_preview.py top=/dev/video4 --cam-width 1280 --cam-height 720

Run it in the VM's own terminal (needs a display). Prefer the /dev/v4l/by-id/... path printed by
--list: /dev/videoN can change after a replug.
"""

import argparse
import time
from collections import deque
from pathlib import Path

import cv2
from rig import make_camera, parse_camera

from lerobot.cameras.opencv import OpenCVCamera


def by_id_links() -> dict[str, str]:
    """/dev/videoN -> /dev/v4l/by-id/... (stable across replugs), Linux only."""
    links = {}
    for link in sorted(Path("/dev/v4l/by-id").glob("*")):
        links.setdefault(str(link.resolve()), str(link))
    return links


def list_cameras() -> None:
    cams = OpenCVCamera.find_cameras()
    if not cams:
        print("no camera OpenCV can open (USB passed through to the VM? lsusb ; ls /dev/video*)")
        return
    links = by_id_links()
    for cam in cams:
        p = cam["default_stream_profile"]
        name_file = Path("/sys/class/video4linux") / Path(str(cam["id"])).name / "name"
        label = name_file.read_text().strip() if name_file.exists() else ""
        print(f"{cam['id']!s:12} {p['width']}x{p['height']} @ {p['fps']:.0f} fps {p['fourcc']:4}  {label}")
        if str(cam["id"]) in links:
            print(f"{'':12} stable path: {links[str(cam['id'])]}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("camera", nargs="?", default="0",
                   help="[NAME=]SOURCE[,rotate=0|90|180|270], SOURCE = OpenCV index or /dev/video* path")
    p.add_argument("--list", action="store_true", help="list the cameras OpenCV can open, then quit")
    p.add_argument("--cam-width", type=int, default=640)
    p.add_argument("--cam-height", type=int, default=480)
    p.add_argument("--fps", type=int, default=30)
    args = p.parse_args()
    if args.list:
        list_cameras()
        return 0

    value = args.camera
    if "=" not in value.split(",")[0]:
        value = f"preview={value}"
    try:
        spec = parse_camera(value)
    except argparse.ArgumentTypeError as e:
        p.error(str(e))
    if spec.realsense:
        p.error("realsense source: use scripts/realsense_preview.py (or the D455 colour stream as /dev/videoN)")

    cam = make_camera(spec, args)
    try:
        cam.connect()
    except Exception as e:  # LeRobot raises ConnectionError / RuntimeError with the reason
        print(f"cannot open {spec.source} at {args.cam_width}x{args.cam_height} @ {args.fps} fps: {e}")
        print("check the source with --list, or try another --cam-width/--cam-height/--fps")
        return 1

    title = f"{spec.name}: {spec.source} rotate={spec.rotate}"
    stamps: deque[float] = deque(maxlen=30)
    try:
        while True:
            rgb = cam.async_read(timeout_ms=1000)  # waits for a new frame: the measured rate is real
            stamps.append(time.monotonic())
            fps = (len(stamps) - 1) / (stamps[-1] - stamps[0]) if len(stamps) > 1 else 0.0
            img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            h, w = img.shape[:2]
            cv2.putText(img, f"{w}x{h}  {fps:4.1f} fps (asked {args.fps})", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow(title, img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cam.disconnect()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
