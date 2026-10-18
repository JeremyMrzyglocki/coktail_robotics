"""Run the policy on a Hugging Face GPU (a private Docker Space) instead of the VM's CPU.

  .venv/bin/python scripts/remote_policy.py deploy lleeoogg/pi0-5-cocktail-grasp-20261018-042906   # create / update
  .venv/bin/python scripts/remote_policy.py status          # build stage, GPU, policy loaded?
  .venv/bin/python scripts/remote_policy.py test            # latency of /act from here (no robot)
  .venv/bin/python scripts/remote_policy.py pause           # stop the GPU (billing stops)
  ./scripts/grasp.sh antonin-leroy/pi05-cocktail-grasp --remote NAMESPACE/cocktail-policy

POLICY: OWNER/REPO, OWNER/REPO/checkpoints/003000/pretrained_model, or the repo of a training pushed
with --save_checkpoint_to_hub (its last checkpoint at the Space's start: restart for a newer one).

deploy uploads remote/policy_space/ (Dockerfile + server.py, built by Hugging Face), sets the POLICY
variable and the HF_TOKEN secret (gated PaliGemma tokenizer of pi0.5) and requests --hardware. The
first build takes ~10 min, then each start ~2-4 min (download + load + warm-up). The Space sleeps
after --sleep s without requests; pause stops it at once.

Token: HF_COMPUTE_TOKEN, else the file ~/.hf_compute_token (the account that pays for the GPU), else
the default Hugging Face login. RemotePolicy is the client used by run_policy.py --remote.
"""

import argparse
import base64
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from huggingface_hub import HfApi, get_token

SPACE_DIR = Path(__file__).resolve().parent.parent / "remote" / "policy_space"
DEFAULT_SPACE = "cocktail-policy"


def compute_token() -> str | None:
    if os.environ.get("HF_COMPUTE_TOKEN"):
        return os.environ["HF_COMPUTE_TOKEN"].strip()
    path = Path.home() / ".hf_compute_token"
    return path.read_text().strip() if path.exists() else get_token()


def space_id(api: HfApi, name: str) -> str:
    return name if "/" in name else f"{api.whoami()['name']}/{name}"


def space_url(name_or_url: str, token: str | None) -> str:
    if name_or_url.startswith("http"):
        return name_or_url.rstrip("/")
    api = HfApi(token=token)
    host = getattr(api.space_info(space_id(api, name_or_url)), "host", None)
    if host:
        return host.rstrip("/")
    owner, name = space_id(api, name_or_url).split("/")
    return f"https://{owner}-{name}.hf.space".lower().replace("_", "-").replace(".", "-")


class RemotePolicy:
    """HTTP client of remote/policy_space/server.py."""

    def __init__(self, space: str, token: str | None = None, timeout: float = 10.0):
        self.token = token or compute_token()
        self.url = space_url(space, self.token)
        self.timeout = timeout
        self.session = requests.Session()
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"

    def health(self) -> dict:
        r = self.session.get(f"{self.url}/health", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def wait_ready(self, max_wait: float = 600.0) -> dict:
        """Wakes the Space up if it sleeps and waits for the policy; returns /info."""
        t0, last = time.monotonic(), None
        while True:
            try:
                h = self.health()
                state = h.get("state")
            except (requests.RequestException, ValueError) as e:
                h, state = {}, f"not reachable yet ({type(e).__name__})"
            if state == "ready":
                r = self.session.get(f"{self.url}/info", timeout=self.timeout)
                r.raise_for_status()
                return r.json()
            if state == "error":
                raise RuntimeError(f"policy server error: {h.get('error')}")
            if time.monotonic() - t0 > max_wait:
                raise RuntimeError(f"policy server not ready after {max_wait:.0f} s ({state})")
            if state != last:
                print(f"  policy server {self.url}: {state}... (scripts/remote_policy.py status)")
                last = state
            time.sleep(5.0)

    def act(self, state: np.ndarray, images: dict[str, np.ndarray], task: str, robot_type: str,
            quality: int = 95) -> tuple[np.ndarray, float]:
        """images: RGB uint8 (H, W, 3) per camera name. Returns (actions (steps, dim), infer ms)."""
        jpegs = {}
        for name, img in images.items():
            ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ok:
                raise RuntimeError(f"JPEG encoding of {name} failed")
            jpegs[name] = base64.b64encode(buf.tobytes()).decode()
        r = self.session.post(f"{self.url}/act", timeout=self.timeout, json={
            "state": [float(x) for x in state], "images": jpegs, "task": task, "robot_type": robot_type})
        r.raise_for_status()
        out = r.json()
        return np.asarray(out["actions"], dtype=np.float32), out["infer_ms"]


def deploy(api: HfApi, args) -> None:
    repo = space_id(api, args.space)
    token = api.token
    exists = api.repo_exists(repo, repo_type="space")
    if not exists:
        api.create_repo(repo, repo_type="space", space_sdk="docker", private=True,
                        space_hardware=args.hardware, space_sleep_time=args.sleep)
        print(f"created private Space {repo}")
    api.add_space_secret(repo, "HF_TOKEN", token, description="downloads the policy and gated models")
    api.add_space_variable(repo, "POLICY", args.policy)
    api.upload_folder(repo_id=repo, repo_type="space", folder_path=SPACE_DIR,
                      commit_message=f"policy server for {args.policy}")
    if exists:
        api.request_space_hardware(repo, args.hardware, sleep_time=args.sleep)
        api.restart_space(repo)
    print(f"{repo}: POLICY={args.policy}, hardware {args.hardware}, sleeps after {args.sleep} s idle.\n"
          f"https://huggingface.co/spaces/{repo} (build logs). Then: scripts/remote_policy.py status")


def status(api: HfApi, args) -> None:
    repo = space_id(api, args.space)
    rt = api.get_space_runtime(repo)
    print(f"{repo}: {rt.stage}, hardware {rt.hardware} (requested {rt.requested_hardware}), "
          f"sleep {rt.sleep_time} s")
    if rt.stage == "RUNNING":
        print(RemotePolicy(repo, api.token).health())


def test(api: HfApi, args) -> None:
    client = RemotePolicy(space_id(api, args.space), api.token)
    info = client.wait_ready()
    print(f"policy {info['checkpoint']} ({info['type']}) on {info['gpu'] or info['device']}, "
          f"{info['n_action_steps']} actions per chunk, cameras {sorted(info['cameras'])}")
    state = np.zeros(info["input_features"]["observation.state"], dtype=np.float32)
    rng = np.random.default_rng(0)
    images = {k: rng.integers(0, 255, (s[1], s[2], 3), dtype=np.uint8) for k, s in info["cameras"].items()}
    rtt, infer = [], []
    for _ in range(args.n):
        t0 = time.perf_counter()
        actions, ms = client.act(state, images, "test", "bi_openarm_follower")
        rtt.append((time.perf_counter() - t0) * 1000)
        infer.append(ms)
    rtt, infer = np.array(rtt[1:] or rtt), np.array(infer[1:] or infer)
    chunk_ms = len(actions) / args.fps * 1000
    print(f"actions {actions.shape}; round trip p50 {np.median(rtt):.0f} ms, p95 {np.percentile(rtt, 95):.0f} ms "
          f"(GPU {np.median(infer):.0f} ms, network+encoding {np.median(rtt - infer):.0f} ms)")
    print(f"a chunk lasts {chunk_ms:.0f} ms at {args.fps:.0f} fps: "
          + ("OK, the next one arrives well before the end." if np.percentile(rtt, 95) < chunk_ms / 2
             else "tight: raise --refill of run_policy.py or use a faster GPU."))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["deploy", "status", "test", "pause", "restart"])
    p.add_argument("policy", nargs="?", help="deploy: policy repo id on the Hub")
    p.add_argument("--space", default=DEFAULT_SPACE, help="Space name or NAMESPACE/NAME (default: your account)")
    p.add_argument("--hardware", default="l4x1", help="l4x1 (24 GB), a10g-large, l40sx1, a100-large, ...")
    p.add_argument("--sleep", type=int, default=3600, help="seconds without requests before the Space sleeps")
    p.add_argument("-n", type=int, default=20, help="test: number of requests")
    p.add_argument("--fps", type=float, default=30.0, help="test: control rate, to judge the latency")
    args = p.parse_args()
    api = HfApi(token=compute_token())
    if args.action == "deploy":
        if not args.policy:
            p.error("deploy needs the policy repo id")
        deploy(api, args)
    elif args.action == "status":
        status(api, args)
    elif args.action == "test":
        test(api, args)
    elif args.action == "pause":
        api.pause_space(space_id(api, args.space))
        print("paused: the GPU is off and not billed (deploy or restart to start it again)")
    else:
        api.restart_space(space_id(api, args.space))
        print("restarting (scripts/remote_policy.py status)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
