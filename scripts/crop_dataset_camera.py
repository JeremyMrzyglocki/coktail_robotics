"""Apply a camera's crop / zoom to the episodes already recorded in a local LeRobot dataset.

  .venv/bin/python scripts/crop_dataset_camera.py antonin-leroy/cocktail-grasp \
      "back=/dev/v4l/by-id/usb-HBV_HD_CAMERA_HBV_HD_CAMERA-video-index0,crop=16:40:512:384" --push

Takes the camera spec of scripts/ports.sh (only its crop and zoom are used; the frames are already
rotated) and re-encodes every video file of observation.images.NAME in place with the same encoder
settings, frame count and timestamps, so the episode index does not change. The per-episode and
global image stats of that camera are recomputed like LeRobot does while recording. The dataset is
copied to ~/datasets_backup/ first. Run it once: the crop is applied again on every run.
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rig import parse_camera, preprocess  # noqa: E402

from lerobot.configs import encoder_config_from_video_info
from lerobot.datasets.compute_stats import RunningQuantileStats, aggregate_stats, auto_downsample_height_width
from lerobot.datasets.io_utils import load_stats, write_stats
from lerobot.utils.constants import HF_LEROBOT_HOME


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("repo_id")
    p.add_argument("camera", type=parse_camera, help="NAME=SOURCE[,crop=X:Y:W:H][,zoom=X] as in scripts/ports.sh")
    p.add_argument("--push", action="store_true", help="push the dataset to the Hub afterwards")
    args = p.parse_args()
    spec = args.camera
    if spec.crop is None and spec.zoom <= 1.0:
        p.error("the camera spec has no crop and no zoom: nothing to do")

    root = HF_LEROBOT_HOME / args.repo_id
    key = f"observation.images.{spec.name}"
    info = json.loads((root / "meta/info.json").read_text())
    if key not in info["features"]:
        p.error(f"{key} not in {root}/meta/info.json")
    fps = info["fps"]
    encoder = encoder_config_from_video_info(info["features"][key]["info"])

    backup = Path.home() / "datasets_backup" / f"{root.name}_{datetime.now():%Y%m%d_%H%M%S}"
    print(f"backup: {backup}")
    shutil.copytree(root, backup)

    ep_files = sorted((root / "meta/episodes").glob("*/*.parquet"))
    tables = {f: pq.read_table(f) for f in ep_files}
    episodes = []  # (parquet file, row, episode_index, chunk, file, first frame in the video file, length)
    for f, t in tables.items():
        cols = t.to_pydict()
        for row, ep in enumerate(cols["episode_index"]):
            first = round(cols[f"videos/{key}/from_timestamp"][row] * fps)
            episodes.append((f, row, ep, cols[f"videos/{key}/chunk_index"][row],
                             cols[f"videos/{key}/file_index"][row], first, cols["length"][row]))

    ep_stats = {}
    for chunk, file in sorted({(e[3], e[4]) for e in episodes}):
        path = root / info["video_path"].format(video_key=key, chunk_index=chunk, file_index=file)
        in_file = [e for e in episodes if (e[3], e[4]) == (chunk, file)]
        trackers = {e[2]: RunningQuantileStats() for e in in_file}
        frame_ep = {}
        for e in in_file:
            frame_ep.update({i: e[2] for i in range(e[5], e[5] + e[6])})
        tmp = path.with_suffix(".crop.mp4")
        n = 0
        with av.open(str(path)) as src, av.open(str(tmp), "w", options={"movflags": "faststart"}) as dst:
            out = None
            for frame in src.decode(video=0):
                rgb = preprocess(frame.to_ndarray(format="rgb24"), spec)
                if out is None:
                    out = dst.add_stream(encoder.vcodec, fps, options=encoder.get_codec_options(None, as_strings=True))
                    out.pix_fmt, out.width, out.height = encoder.pix_fmt, rgb.shape[1], rgb.shape[0]
                    out.time_base = Fraction(1, fps)
                vf = av.VideoFrame.from_ndarray(rgb, format="rgb24")
                vf.pts, vf.time_base = n, Fraction(1, fps)
                dst.mux(out.encode(vf))
                if n in frame_ep:
                    chw = auto_downsample_height_width(rgb.transpose(2, 0, 1))
                    trackers[frame_ep[n]].update(chw.transpose(1, 2, 0).reshape(-1, chw.shape[0]))
                n += 1
            dst.mux(out.encode())
        with av.open(str(tmp)) as check:
            m = sum(1 for _ in check.decode(video=0))
        if m != n or n < max(frame_ep) + 1:
            tmp.unlink()
            sys.exit(f"{path.name}: {m} frames written for {n} read (episodes need {max(frame_ep) + 1}); "
                     "nothing replaced in this file")
        tmp.replace(path)
        for ep, tr in trackers.items():
            ep_stats[ep] = {k: v if k == "count" else np.squeeze(v.reshape(1, -1, 1, 1) / 255.0, axis=0)
                            for k, v in tr.get_statistics().items()}
        print(f"  {path.relative_to(root)}: {n} frames, episodes {sorted(trackers)}")

    for f, t in tables.items():
        cols = {c: t.column(c).to_pylist() for c in t.column_names if c.startswith(f"stats/{key}/")}
        for e in (e for e in episodes if e[0] == f):
            for stat, v in ep_stats[e[2]].items():
                cols[f"stats/{key}/{stat}"][e[1]] = np.asarray(v).tolist()
        for c, values in cols.items():
            t = t.set_column(t.column_names.index(c), c, pa.array(values, type=t.schema.field(c).type))
        pq.write_table(t, f)

    stats = load_stats(root)
    stats[key] = aggregate_stats([{key: s} for s in ep_stats.values()])[key]
    write_stats(stats, root)
    print(f"{key}: {len(ep_stats)} episodes cropped, stats recomputed (mean {np.ravel(stats[key]['mean']).round(3)})")

    if args.push:
        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        LeRobotDataset(args.repo_id, root=root).push_to_hub()
        print(f"pushed https://huggingface.co/datasets/{args.repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
