"""Policy server: observation in, the next chunk of actions out (one GPU, one request at a time).

The policy (POLICY env, Hub repo id) loads in the background at startup; /health says when it is
ready. /act runs the same pipeline as scripts/run_policy.py on the robot (prepare_observation_for_
inference, the policy's own pre/post processors) but returns the whole chunk, so the robot keeps
executing it while the next request travels.
"""

import base64
import io
import os
import threading
import time
import traceback

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
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


def load():
    try:
        if not POLICY:
            raise RuntimeError("no POLICY variable set on the Space")
        cfg = PreTrainedConfig.from_pretrained(POLICY)
        cfg.device = DEVICE
        policy = get_policy_class(cfg.type).from_pretrained(POLICY, config=cfg)
        policy.eval()
        pre, post = make_pre_post_processors(
            cfg, pretrained_path=POLICY, preprocessor_overrides={"device_processor": {"device": DEVICE}})
        model.update(cfg=cfg, policy=policy, pre=pre, post=post)
        # Warm-up on blank frames (CUDA kernels, tokenizer), so the first robot request is not slow.
        state = np.zeros(cfg.input_features["observation.state"].shape, dtype=np.float32)
        images = {k.removeprefix("observation.images."): np.zeros((f.shape[1], f.shape[2], 3), np.uint8)
                  for k, f in cfg.input_features.items() if k.startswith("observation.images.")}
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
