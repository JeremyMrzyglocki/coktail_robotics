"""Policy server: observation in, the next chunk of actions out (one GPU, one request at a time).

The policy (POLICY env: OWNER/REPO, OWNER/REPO/SUBFOLDER, or a repo of a training pushed with
--save_checkpoint_to_hub, whose last checkpoints/N/pretrained_model is used) loads in the background
at startup; /health says when it is ready. Cameras arrive under the robot's names (front, back): the
policy's own rename step maps them, and its empty cameras are left out (the policy pads them). /act runs the same pipeline as scripts/run_policy.py on the robot (prepare_observation_for_
inference, the policy's own pre/post processors) but returns the whole chunk, so the robot keeps
executing it while the next request travels.
"""

import base64
import io
import json
import os
import threading
import time
import traceback

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from huggingface_hub import HfApi, snapshot_download
from PIL import Image
from pydantic import BaseModel

from lerobot.configs.policies import PreTrainedConfig
from lerobot.policies import prepare_observation_for_inference
from lerobot.policies.factory import get_policy_class, make_pre_post_processors

POLICY = os.environ.get("POLICY", "")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
app = FastAPI()
status: dict = {"state": "loading", "policy": POLICY, "device": DEVICE,
                "gpu": torch.cuda.get_device_name(0) if DEVICE == "cuda" else None}
model: dict = {}
lock = threading.Lock()


class Observation(BaseModel):
    state: list[float]
    images: dict[str, str]  # camera name (without observation.images.) -> base64 JPEG, RGB
    task: str = ""
    robot_type: str = ""


def infer(state: np.ndarray, images: dict[str, np.ndarray], task: str, robot_type: str) -> np.ndarray:
    cfg, policy, pre, post = model["cfg"], model["policy"], model["pre"], model["post"]
    obs = {"observation.state": state.astype(np.float32)}
    obs.update({f"observation.images.{k}": v for k, v in images.items()})
    obs = prepare_observation_for_inference(obs, torch.device(DEVICE), task, robot_type)
    with torch.inference_mode():
        policy.reset()  # stateless: each request is a fresh observation
        chunk = policy.predict_action_chunk(pre(obs))[:, : cfg.n_action_steps]
        actions = post(chunk.squeeze(0))  # (steps, action dim), unnormalized
    return actions.float().cpu().numpy()


def resolve(spec: str) -> tuple[str, str]:
    """POLICY -> (local pretrained_model dir, OWNER/REPO/SUBFOLDER it came from)."""
    if os.path.isdir(spec):
        return spec, spec
    parts = spec.strip("/").split("/")
    repo, sub = "/".join(parts[:2]), "/".join(parts[2:])
    if not sub:
        files = HfApi().list_repo_files(repo)
        if "config.json" not in files:
            steps = sorted({f.split("/")[1] for f in files if f.startswith("checkpoints/")
                            and f.endswith("/pretrained_model/config.json")}, key=lambda x: (x.isdigit(), x))
            if not steps:
                raise RuntimeError(f"{repo}: no config.json and no checkpoints/*/pretrained_model")
            sub = f"checkpoints/{steps[-1]}/pretrained_model"
    local = snapshot_download(repo, allow_patterns=[f"{sub}/*"] if sub else ["*.json", "*.safetensors", "tokenizer/*"])
    return os.path.join(local, sub), f"{repo}/{sub}" if sub else repo


def robot_cameras(cfg, path: str) -> dict[str, list[int]]:
    """Camera names the robot sends (before the policy's rename step) -> [C, H, W]."""
    rename = {}
    with open(os.path.join(path, "policy_preprocessor.json")) as f:
        for step in json.load(f)["steps"]:
            if step.get("registry_name") == "rename_observations_processor":
                rename = step["config"]["rename_map"]
    inverse = {v: k for k, v in rename.items()}
    return {inverse.get(k, k).removeprefix("observation.images."): list(f.shape)
            for k, f in cfg.input_features.items()
            if k.startswith("observation.images.") and ".empty_camera_" not in k}


def load():
    try:
        if not POLICY:
            raise RuntimeError("no POLICY variable set on the Space")
        path, source = resolve(POLICY)
        status.update(checkpoint=source)
        cfg = PreTrainedConfig.from_pretrained(path)
        cfg.device = DEVICE
        policy = get_policy_class(cfg.type).from_pretrained(path, config=cfg)
        policy.eval()
        pre, post = make_pre_post_processors(
            cfg, pretrained_path=path, preprocessor_overrides={"device_processor": {"device": DEVICE}})
        cameras = robot_cameras(cfg, path)
        model.update(cfg=cfg, policy=policy, pre=pre, post=post, cameras=cameras)
        # Warm-up on blank frames (CUDA kernels, tokenizer), so the first robot request is not slow.
        state = np.zeros(cfg.input_features["observation.state"].shape, dtype=np.float32)
        images = {k: np.zeros((s[1], s[2], 3), np.uint8) for k, s in cameras.items()}
        t0 = time.perf_counter()
        for _ in range(2):
            infer(state, images, "warm-up", "")
        status.update(state="ready", type=cfg.type, warmup_ms=round((time.perf_counter() - t0) * 500, 1))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        status.update(state="error", error=f"{type(e).__name__}: {e}")


threading.Thread(target=load, daemon=True).start()


@app.get("/")
@app.get("/health")
def health():
    return status


@app.get("/info")
def info():
    if status["state"] != "ready":
        raise HTTPException(503, status)
    cfg = model["cfg"]
    return {**status,
            "input_features": {k: list(f.shape) for k, f in cfg.input_features.items()},
            "output_features": {k: list(f.shape) for k, f in cfg.output_features.items()},
            "cameras": model["cameras"],
            "chunk_size": getattr(cfg, "chunk_size", None), "n_action_steps": cfg.n_action_steps}


@app.post("/act")
def act(obs: Observation):
    if status["state"] != "ready":
        raise HTTPException(503, status)
    images = {k: np.asarray(Image.open(io.BytesIO(base64.b64decode(v))).convert("RGB"))
              for k, v in obs.images.items()}
    with lock:
        t0 = time.perf_counter()
        actions = infer(np.asarray(obs.state, dtype=np.float32), images, obs.task, obs.robot_type)
        ms = (time.perf_counter() - t0) * 1000
    return {"actions": actions.round(4).tolist(), "infer_ms": round(ms, 1)}
