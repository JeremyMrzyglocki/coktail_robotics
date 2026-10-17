#!/usr/bin/env python3
"""Pull real thumbnails for skills and datasets from the Hugging Face Hub.

Images come from the demonstration data a skill is trained on, not from stock art.
That keeps the storefront honest: the picture on the card is a frame of the thing
the robot actually learned from, and a skill with no data has no picture.

Three sources, tried in order:
  1. Hub dataset-viewer image columns  -- a direct JPEG URL, no auth, no ffmpeg
  2. A video column + ffmpeg           -- seeks over HTTPS, downloads only what it reads
  3. Nothing                           -- the card renders a "no demonstration data"
                                          placeholder, which is the point

    python tools/fetch_media.py --only trained      # the ones that matter, fast
    python tools/fetch_media.py                     # everything it can get
    python tools/fetch_media.py --datasets          # cover images for the Data tab

Needs no Hub token for open datasets. Gated ones (Egocentric-10K/100K) need
HF_TOKEN set after accepting their terms once on the dataset page.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THUMBS = ROOT / "app" / "static" / "thumbs"
VIEWER = "https://datasets-server.huggingface.co/first-rows"
TIMEOUT = 40


def _get(url: str, token: str | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"user-agent": "skill-store/0.1"})
    if token:
        req.add_header("authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def viewer_rows(repo_id: str, token: str | None) -> list[dict]:
    url = (f"{VIEWER}?dataset={urllib.parse.quote(repo_id, safe='')}"
           f"&config=default&split=train")
    try:
        body = json.loads(_get(url, token))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []
    return [r.get("row", {}) for r in body.get("rows", [])]


def _media_columns(row: dict) -> tuple[list[str], list[str]]:
    """Split a viewer row into (image srcs, video srcs)."""
    images, videos = [], []
    for value in row.values():
        src = value.get("src") if isinstance(value, dict) else None
        if not src:
            continue
        (videos if src.lower().endswith((".mp4", ".mkv", ".webm")) else images).append(src)
    return images, videos


TREE = "https://huggingface.co/api/datasets/{repo}/tree/main?recursive=1"
RESOLVE = "https://huggingface.co/datasets/{repo}/resolve/main/{path}"


def lerobot_video_urls(repo_id: str, token: str | None) -> list[str]:
    """LeRobot v3 keeps videos as files, not viewer columns. Find them directly.

    These are usually AV1, so extraction needs an ffmpeg built with libdav1d.
    """
    try:
        tree = json.loads(_get(TREE.format(repo=repo_id), token))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []
    return [RESOLVE.format(repo=repo_id, path=f["path"])
            for f in tree
            if f.get("type") == "file" and f.get("path", "").endswith(".mp4")]


# When a skill's own dataset serves no media (EgoDex is off-Hub; LeRobot v3 is
# AV1), borrow a representative frame from one of these and credit it in the UI.
THUMB_FALLBACK = {
    "egocentric": "Voxel51/Egocentric_10K_subset",
    "teleop": "lerobot/aloha_sim_insertion_human_image",
}


def grab_frame(video_url: str, dest: Path, offset: float) -> bool:
    """Extract one frame. ffmpeg range-reads the URL rather than downloading it all."""
    if not shutil.which("ffmpeg"):
        return False
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{offset:.1f}",
           "-i", video_url, "-frames:v", "1", "-q:v", "4",
           "-vf", "scale=480:-2", str(dest), "-y"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False
    if proc.returncode != 0 and b"codec av1" in proc.stderr.lower():
        print("      ffmpeg lacks an AV1 decoder (LeRobot v3 videos are AV1). "
              "Install an ffmpeg built with libdav1d, e.g. `brew install ffmpeg`.")
    return dest.exists() and dest.stat().st_size > 1000


def fetch_thumb(name: str, repo_id: str, dest: Path, salt: str,
                token: str | None) -> str:
    """Return the source used: 'image', 'video', or '' when nothing worked."""
    rows = viewer_rows(repo_id, token)
    if not rows:
        return ""
    # Deterministic per-skill pick, so cards differ instead of all showing frame 0.
    seed = int(hashlib.sha256(salt.encode()).hexdigest()[:8], 16)
    row = rows[seed % len(rows)]
    images, videos = _media_columns(row)

    if images:
        try:
            dest.write_bytes(_get(images[seed % len(images)], token))
            if dest.stat().st_size > 1000:
                return "image"
        except (urllib.error.URLError, TimeoutError):
            pass
    for video in videos:
        if grab_frame(video, dest, offset=1.0 + (seed % 9)):
            return "video"
    for video in lerobot_video_urls(repo_id, token)[:2]:
        if grab_frame(video, dest, offset=1.0 + (seed % 9)):
            return "video"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["trained", "beta", "catalog"],
                    help="limit to skills with this status")
    ap.add_argument("--skills", action="store_true",
                    help=("also fetch per-skill frames. OFF by default: until a "
                          "skill has its own recorded episodes, any frame is from "
                          "someone else's data and misrepresents it. The UI draws "
                          "a schematic from the manifest instead."))
    ap.add_argument("--datasets", action="store_true", default=True,
                    help="fetch one cover image per dataset (default)")
    ap.add_argument("--force", action="store_true", help="refetch existing files")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    THUMBS.mkdir(parents=True, exist_ok=True)
    datasets = {d["id"]: d for d in json.loads((ROOT / "data" / "datasets.json").read_text())}
    skills = json.loads((ROOT / "data" / "seed_skills.json").read_text())

    if not args.skills:
        skills = []
    if args.only:
        skills = [s for s in skills if s["status"] == args.only]
    if args.limit:
        skills = skills[: args.limit]

    credits_path = ROOT / "data" / "thumb_sources.json"
    credits = json.loads(credits_path.read_text()) if credits_path.exists() else {}
    got = skipped = failed = 0
    for skill in skills:
        dest = THUMBS / f"{skill['id']}.jpg"
        if dest.exists() and not args.force:
            skipped += 1
            continue
        ds = datasets.get((skill.get("dataset") or {}).get("id") or "")
        repo = (ds or {}).get("repo_id")
        if not repo:
            alt = THUMB_FALLBACK.get((ds or {}).get("kind", ""), "")
            source = fetch_thumb(skill["name"], alt, dest, skill["id"], token) if alt else ""
            if source:
                print(f"  {skill['id']:<24} {source:<6} <- {alt}  (representative; "
                      f"{(ds or {}).get('name','?')} is not on the Hub)")
                credits[skill["id"]] = {"repo_id": alt, "source": source,
                                        "representative": True}
                got += 1
            else:
                print(f"  {skill['id']:<24} no hub dataset ({(ds or {}).get('name','-')})")
                failed += 1
            continue
        if ds.get("access") == "gated-auto" and not token:
            print(f"  {skill['id']:<24} {ds['name']} is gated -- set HF_TOKEN")
            failed += 1
            continue
        source = fetch_thumb(skill["name"], repo, dest, skill["id"], token)
        used = repo
        if not source:
            alt = THUMB_FALLBACK.get(ds.get("kind", ""), "")
            if alt and alt != repo:
                source = fetch_thumb(skill["name"], alt, dest, skill["id"], token)
                used = alt
        if source:
            via = "" if used == repo else "  (representative)"
            print(f"  {skill['id']:<24} {source:<6} <- {used}{via}")
            credits[skill["id"]] = {"repo_id": used, "source": source,
                                    "representative": used != repo}
            got += 1
        else:
            dest.unlink(missing_ok=True)
            print(f"  {skill['id']:<24} no media available from {repo}")
            failed += 1

    if args.datasets:
        print("\ndataset covers:")
        for ds in datasets.values():
            if not ds.get("repo_id"):
                continue
            dest = THUMBS / f"ds_{ds['id']}.jpg"
            if dest.exists() and not args.force:
                continue
            if ds.get("access") == "gated-auto" and not token:
                print(f"  {ds['id']:<24} gated -- set HF_TOKEN")
                continue
            source = fetch_thumb(ds["name"], ds["repo_id"], dest, ds["id"], token)
            print(f"  {ds['id']:<24} {source or 'none'}")
            if not source:
                dest.unlink(missing_ok=True)

    credits_path.write_text(json.dumps(credits, indent=2, sort_keys=True) + "\n")
    print(f"\n{got} fetched, {skipped} already present, {failed} without media.")
    print("Skills with no image render a 'no demonstration data' placeholder -- "
          "that gap is the point, not a bug.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
