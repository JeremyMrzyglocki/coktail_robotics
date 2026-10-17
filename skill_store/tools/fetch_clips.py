#!/usr/bin/env python3
"""Short video previews of each dataset, for the detail popups.

A clip is a few seconds of the real demonstration data, cut from the Hub without
downloading the whole file (ffmpeg range-reads the URL). Where that is not
possible the clip falls back, in order:

  1. local   -- transcoded to H.264 into app/static/clips/<id>.mp4, plays anywhere
  2. stream  -- LeRobot v3 videos are AV1 and this ffmpeg cannot decode them, so
                the popup streams that segment straight from the Hub instead.
                Chrome plays AV1; Safari only on M3-or-newer Macs. `brew install
                ffmpeg` (built with libdav1d) turns these into local clips.
  3. frames  -- image-only datasets: consecutive frames stitched into a clip
  4. none    -- gated, private or off-Hub; the popup says so

Every clip is recorded with its exact source in data/clip_sources.json, so the UI
can say where it came from.

    python tools/fetch_clips.py                 # every dataset on the Hub
    python tools/fetch_clips.py --only droid    # one
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_media import _get, _media_columns, lerobot_video_urls, viewer_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CLIPS = ROOT / "app" / "static" / "clips"
SOURCES = ROOT / "data" / "clip_sources.json"
START, LENGTH = 3.0, 6.0


def cut(url: str, dest: Path) -> tuple[bool, str]:
    """Cut LENGTH seconds at START, re-encoded to H.264. Returns (ok, stderr)."""
    if not shutil.which("ffmpeg"):
        return False, "ffmpeg not installed"
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", str(START), "-t", str(LENGTH),
           "-i", url, "-an", "-vf", "scale=640:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "28", "-movflags", "+faststart", "-y", str(dest)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        return False, "timed out"
    ok = proc.returncode == 0 and dest.exists() and dest.stat().st_size > 10_000
    if not ok:
        dest.unlink(missing_ok=True)
    return ok, proc.stderr.decode(errors="replace")[-300:]


def frames_clip(srcs: list[str], dest: Path, token: str | None) -> bool:
    """Stitch consecutive viewer frames into a clip at 10 fps."""
    with tempfile.TemporaryDirectory() as tmp:
        n = 0
        for src in srcs:
            try:
                (Path(tmp) / f"{n:04d}.jpg").write_bytes(_get(src, token))
                n += 1
            except (urllib.error.URLError, TimeoutError):
                continue
        if n < 10:
            return False
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-framerate", "10",
               "-i", str(Path(tmp) / "%04d.jpg"), "-vf", "scale=640:-2",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
               "-y", str(dest)]
        return subprocess.run(cmd, capture_output=True).returncode == 0


def fetch(ds: dict, token: str | None) -> dict:
    repo = ds.get("repo_id")
    if not repo:
        return {"kind": "none", "why": f"not on the Hub ({ds.get('access')})"}
    dest = CLIPS / f"{ds['id']}.mp4"
    rows = viewer_rows(repo, token)
    videos: list[str] = []
    images: list[str] = []
    for row in rows:
        imgs, vids = _media_columns(row)
        videos += vids
        images += imgs
    videos = videos[:1] or lerobot_video_urls(repo, token)[:1]

    if videos:
        url = videos[0]
        ok, err = cut(url, dest)
        if ok:
            return {"kind": "local", "path": f"clips/{dest.name}", "repo_id": repo,
                    "source": url, "start": START, "length": LENGTH}
        if "av1" in err.lower() or "decoder" in err.lower():
            return {"kind": "stream", "url": url, "repo_id": repo, "source": url,
                    "start": START, "length": LENGTH, "codec": "av1"}
        return {"kind": "none", "why": f"could not cut a clip: {err.strip()[:120]}"}
    if images and frames_clip(images[:60], dest, token):
        return {"kind": "local", "path": f"clips/{dest.name}", "repo_id": repo,
                "source": f"first {min(len(images), 60)} frames of the viewer", "start": 0,
                "length": min(len(images), 60) / 10}
    why = "gated -- accept the terms and set HF_TOKEN" if ds.get("access") == "gated-auto" \
        else "no video or images served"
    return {"kind": "none", "why": why}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one dataset id")
    args = ap.parse_args()
    token = os.environ.get("HF_TOKEN") or None
    CLIPS.mkdir(parents=True, exist_ok=True)
    datasets = json.loads((ROOT / "data" / "datasets.json").read_text())
    out = json.loads(SOURCES.read_text()) if SOURCES.exists() else {}
    for ds in datasets:
        if args.only and ds["id"] != args.only:
            continue
        print(f"{ds['id']:34}", end=" ", flush=True)
        out[ds["id"]] = fetch(ds, token)
        info = out[ds["id"]]
        print(info["kind"], info.get("path") or info.get("why") or info.get("codec", ""))
    SOURCES.write_text(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
