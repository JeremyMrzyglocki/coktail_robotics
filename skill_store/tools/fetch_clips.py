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
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_media import TIMEOUT, _get, _media_columns, ffmpeg_bin, lerobot_video_urls, viewer_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CLIPS = ROOT / "app" / "static" / "clips"
SOURCES = ROOT / "data" / "clip_sources.json"
START, LENGTH = 3.0, 6.0


def cut(url: str, dest: Path) -> tuple[bool, str]:
    """Cut LENGTH seconds at START, re-encoded to H.264. Returns (ok, stderr)."""
    if not ffmpeg_bin():
        return False, "ffmpeg not installed"
    cmd = [ffmpeg_bin(), "-nostdin", "-loglevel", "error", "-ss", str(START), "-t", str(LENGTH),
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
        cmd = [ffmpeg_bin(), "-nostdin", "-loglevel", "error", "-framerate", "10",
               "-i", str(Path(tmp) / "%04d.jpg"), "-vf", "scale=640:-2",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
               "-y", str(dest)]
        return subprocess.run(cmd, capture_output=True).returncode == 0


TAR_CAP = 800 * 1024 * 1024     # never pull more than this out of one shard


def first_tar(repo: str, token: str | None) -> str | None:
    """The first .tar shard in the repo, found by walking the tree two levels down."""
    def ls(path: str) -> list[dict]:
        url = f"https://huggingface.co/api/datasets/{repo}/tree/main/{path}".rstrip("/")
        try:
            return json.loads(_get(url, token))
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            return []
    frontier = [""]
    for _ in range(4):
        nxt = []
        for d in frontier[:3]:
            for f in ls(d):
                if f.get("type") == "file" and f.get("path", "").endswith(".tar"):
                    return f["path"]
                if f.get("type") == "directory":
                    nxt.append(f["path"])
        frontier = nxt
        if not frontier:
            break
    return None


def video_from_tar(repo: str, path: str, token: str | None, out: Path) -> tuple[str | None, str]:
    """Stream a tar shard only as far as its first video member and save that.

    Build AI's egocentric sets keep MP4s inside tar shards with no viewer, so a
    clip means reading one shard sequentially until the first video ends -- a
    few hundred MB at most, not the shard.
    """
    url = f"https://huggingface.co/datasets/{repo}/resolve/main/{path}"
    req = urllib.request.Request(url, headers={"user-agent": "skill-store/0.1"})
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
    except urllib.error.URLError as exc:
        return None, f"could not open {path}: {exc}"
    try:
        with tarfile.open(fileobj=resp, mode="r|") as tf:
            for m in tf:
                if not m.isfile() or not m.name.lower().endswith((".mp4", ".mkv", ".webm")):
                    continue
                if m.size > TAR_CAP:
                    return None, f"first video in {path} is {m.size >> 20} MB, over the cap"
                src = tf.extractfile(m)
                with open(out, "wb") as fh:
                    shutil.copyfileobj(src, fh, 1 << 20)
                return f"{path}::{m.name}", ""
    except (tarfile.TarError, OSError) as exc:
        return None, f"bad tar {path}: {exc}"
    return None, f"no video member in {path}"


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
    if ds.get("access") == "gated-auto" and not token:
        return {"kind": "none", "why": "gated -- accept the terms and set HF_TOKEN"}
    shard = first_tar(repo, token)
    if shard:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "first.mp4"
            member, err = video_from_tar(repo, shard, token, raw)
            if member:
                ok, ferr = cut(str(raw), dest)
                if ok:
                    return {"kind": "local", "path": f"clips/{dest.name}", "repo_id": repo,
                            "source": member, "start": START, "length": LENGTH}
                return {"kind": "none", "why": f"could not cut a clip: {ferr.strip()[:120]}"}
            return {"kind": "none", "why": err}
    return {"kind": "none", "why": "no video or images served"}


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
        have = out.get(ds["id"])
        if not args.only and have and have["kind"] == "local":
            continue                      # a local clip is final; streams and misses get another go
        print(f"{ds['id']:34}", end=" ", flush=True)
        info = fetch(ds, token)
        print(info["kind"], info.get("path") or info.get("why") or info.get("codec", ""), flush=True)
        # Save after every dataset, merging with whatever another run wrote
        # meanwhile: a long sweep can be stopped without losing its progress.
        out = json.loads(SOURCES.read_text()) if SOURCES.exists() else {}
        out[ds["id"]] = info
        SOURCES.write_text(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
