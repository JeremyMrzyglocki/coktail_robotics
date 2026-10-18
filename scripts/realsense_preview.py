"""Show RealSense RGB + depth side by side. Press q to quit.

Usage:  uv run scripts/realsense_preview.py
"""

import cv2
import numpy as np
import pyrealsense2 as rs

ZOOM = 1.10  # same digital zoom as the recordings (CAMERAS in scripts/ports.sh: front=...,zoom=1.1)


def zoom_center(img, factor, interpolation=cv2.INTER_LINEAR):
    """Keep the central 1/factor of the image and resize it back to the same size."""
    h, w = img.shape[:2]
    ch, cw = round(h / factor), round(w / factor)
    y, x = (h - ch) // 2, (w - cw) // 2
    return cv2.resize(img[y:y + ch, x:x + cw], (w, h), interpolation=interpolation)


pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
pipeline.start(config)
align = rs.align(rs.stream.color)  # put depth pixels on top of the colour pixels

try:
    while True:
        frames = align.process(pipeline.wait_for_frames())
        rgb = np.asanyarray(frames.get_color_frame().get_data())
        depth = np.asanyarray(frames.get_depth_frame().get_data())  # uint16, millimetres

        # The camera is mounted upside down: rotate RGB and depth by 180°.
        # Recordings must do the same, e.g. in LeRobot: RealSenseCameraConfig(..., rotation=Cv2Rotation.ROTATE_180)
        # (CLI: --robot.cameras='{... rotation: 180 ...}').
        rgb = cv2.rotate(rgb, cv2.ROTATE_180)
        depth = cv2.rotate(depth, cv2.ROTATE_180)
        rgb = zoom_center(rgb, ZOOM)
        depth = zoom_center(depth, ZOOM, cv2.INTER_NEAREST)

        depth_color = cv2.applyColorMap(cv2.convertScaleAbs(depth, alpha=255 / 2000), cv2.COLORMAP_JET)  # 0-2 m
        cv2.imshow("RealSense", np.hstack([rgb, depth_color]))
        if cv2.waitKey(1) == ord("q"):
            break
finally:
    pipeline.stop()
    cv2.destroyAllWindows()
