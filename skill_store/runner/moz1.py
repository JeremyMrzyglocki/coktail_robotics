"""Spirit AI Moz1 executor: openpi policy server + mozrobot control loop.

Topology (all on the robot laptop):

    serve_policy.py  :8000   one process per CHECKPOINT (not per skill)
          ^ websocket
    Moz1Executor             owns the 120 Hz loop via mozrobot
          | CAT6, 172.16.0.x
    Moz1 industrial PC

A skill is a (checkpoint, prompt) pair, so several skills share one server and
differ only by the language prompt sent with each observation. Start one server
per distinct checkpoint and map them in POLICY_ENDPOINTS.

The network never sits between the policy and the arm: inference is a localhost
websocket, and action interpolation happens here. A wifi hiccup can delay a job;
it cannot jerk the arm mid-motion.

BEFORE FIRST USE: run `python runner/probe_robot.py` to print the real observation
keys and action schema, then fill in _to_policy_obs / _to_action below. The docs
do not publish them, so they are deliberately left as a single explicit failure
point rather than guessed.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from .executor import Outcome

# checkpoint path -> "host:port" of the serve_policy.py process holding it
POLICY_ENDPOINTS: dict[str, str] = json.loads(
    os.environ.get("POLICY_ENDPOINTS", "{}")
) or {
    "checkpoints/pi05_moz_bartender/30000": "127.0.0.1:8000",
    "checkpoints/pi05_moz_wipe/30000": "127.0.0.1:8001",
}

CONTROL_HZ = int(os.environ.get("ROBOT_CONTROL_HZ", "120"))
POLICY_HZ = 30                      # RealSense / pi0.5 action rate
ACTION_HORIZON = int(os.environ.get("ACTION_HORIZON", "150"))  # docs suggest 100-200

RESET_POSE = {
    # Fill from a known-good pose. reset_robot_positions takes SI units (radians).
    "left_arm_joints": None,
    "right_arm_joints": None,
    "torso_joints": None,
    "gripper_positions": None,
}


class NotConfigured(RuntimeError):
    pass


class Moz1Executor:
    # One mozrobot send_action carries the whole body, and each pi0.5 checkpoint
    # was trained to drive both arms. Running two skills at once therefore needs a
    # merge layer that takes the left-arm block from one policy and the right-arm
    # block from the other at 120 Hz -- real, but not something to improvise during
    # a demo. Until that exists the runner executes waves in order and says so, and
    # the schedule the UI shows remains a plan rather than a measured result.
    supports_parallel = False

    def __init__(self, structure: str = "dualarm", realsense_serials: str | None = None,
                 dry_run: bool = False) -> None:
        self.structure = structure
        self.dry_run = dry_run
        self.serials = realsense_serials or os.environ.get("REALSENSE_SERIALS", "")
        self.robot = None
        self.clients: dict[str, Any] = {}
        self.step_prompt: str | None = None
        self.endpoint: str | None = None
        self._stopped = False

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> None:
        from mozrobot import MOZ1Robot, MOZ1RobotConfig  # noqa: PLC0415

        if not self.serials:
            raise NotConfigured(
                "REALSENSE_SERIALS is unset. Ask the organizers for the three camera "
                "serials in order: head, left wrist, right wrist."
            )
        cfg = MOZ1RobotConfig(
            realsense_serials=self.serials,
            camera_resolutions="640*480,640*480,640*480",
            structure=self.structure,
            robot_control_hz=CONTROL_HZ,
        )
        self.robot = MOZ1Robot(cfg)
        self.robot.connect()
        if not self.robot.is_robot_connected:
            raise RuntimeError("MOZ1Robot.connect() returned but is_robot_connected is False")
        # Mandatory before any send_action, and easy to forget.
        self.robot.enable_external_following_mode()
        print(f"[moz1] connected, control_hz={self.robot.control_hz}")

    def _policy(self, checkpoint: str):
        """Websocket client for the server holding this checkpoint."""
        if checkpoint in self.clients:
            return self.clients[checkpoint]
        addr = POLICY_ENDPOINTS.get(checkpoint)
        if not addr:
            raise NotConfigured(
                f"no policy server mapped for checkpoint {checkpoint!r}. "
                f"Start serve_policy.py for it and add it to POLICY_ENDPOINTS."
            )
        host, _, port = addr.partition(":")
        from openpi_client import websocket_client_policy  # noqa: PLC0415

        client = websocket_client_policy.WebsocketClientPolicy(host=host, port=int(port))
        self.clients[checkpoint] = client
        return client

    def load(self, step: dict[str, Any]) -> None:
        ckpt = step.get("checkpoint")
        if not ckpt:
            raise NotConfigured(
                f"skill {step['skill_id']} has no checkpoint -- it is catalog-only "
                f"and should never have been queued."
            )
        prompt = step.get("prompt") or ""
        for k, v in (step.get("params") or {}).items():
            prompt = prompt.replace("{" + str(k) + "}", str(v))
        self.step_prompt = prompt
        self.endpoint = ckpt
        client = self._policy(ckpt)
        # First inference triggers torch.compile and can time out. Pre-warm here so
        # it never happens while a judge is watching.
        if self.robot is not None and not self.dry_run:
            try:
                self._infer(client, self._to_policy_obs(self.robot.capture_observation()))
            except Exception as exc:  # noqa: BLE001
                print(f"[moz1] warm-up inference failed (continuing): {exc}")

    # -- the bits that need the real schema --------------------------------
    def _to_policy_obs(self, obs: dict[str, Any]) -> dict[str, Any]:
        """mozrobot observation -> the dict the policy server expects.

        Run probe_robot.py, then map the printed keys here. Typical pi0.5 shape:
            {"observation/image": <head rgb>,
             "observation/wrist_image_left": ..., "observation/wrist_image_right": ...,
             "observation/state": <concatenated joint + gripper vector>,
             "prompt": self.step_prompt}
        """
        raise NotConfigured(
            "_to_policy_obs is not mapped yet. Run `python runner/probe_robot.py`, "
            "then fill in the observation key mapping in runner/moz1.py. "
            "Until then use the mock executor: `python runner/runner.py --mock`."
        )

    def _to_action(self, policy_action: Any, frame: int) -> dict[str, Any]:
        """One policy action frame -> the dict send_action expects.

        SI units throughout (radians, metres, seconds). Each structure uses joint
        space OR Cartesian space, never both in one call.
        """
        raise NotConfigured(
            "_to_action is not mapped yet -- see _to_policy_obs."
        )

    @staticmethod
    def _infer(client: Any, obs: dict[str, Any]) -> Any:
        return client.infer(obs)

    # -- execution ---------------------------------------------------------
    def run(self, step: dict[str, Any], timeout_s: float) -> Outcome:
        if self.robot is None:
            raise RuntimeError("connect() first")
        client = self._policy(step["checkpoint"])
        t0 = time.time()
        period = 1.0 / CONTROL_HZ
        upsample = max(CONTROL_HZ // POLICY_HZ, 1)
        frames_sent = 0

        while time.time() - t0 < timeout_s and not self._stopped:
            obs = self.robot.capture_observation()
            chunk = self._infer(client, self._to_policy_obs(obs))
            # pi0.5 returns ~50 frames at 30 Hz; interpolate up to the control rate.
            for i, act in enumerate(chunk["actions"][:ACTION_HORIZON]):
                for sub in range(upsample):
                    if self._stopped or time.time() - t0 > timeout_s:
                        break
                    tick = time.time()
                    self.robot.send_action(self._to_action(act, sub))
                    frames_sent += 1
                    slack = period - (time.time() - tick)
                    if slack > 0:
                        time.sleep(slack)
            if frames_sent >= ACTION_HORIZON * upsample:
                break

        dur = round(time.time() - t0, 2)
        if self._stopped:
            return Outcome(False, dur, "stopped")
        # Success detection: wire a real postcondition check here (the chalk-coverage
        # scorer, verify_surface_clean, or a VLM call). Timeout alone is not success.
        return Outcome(True, dur, f"sent {frames_sent} frames @ {CONTROL_HZ}Hz")

    def home(self) -> None:
        if self.robot is None:
            return
        self.robot.reset_robot_positions(**RESET_POSE)
        # Returns when the command is SENT, not when motion completes.
        time.sleep(4.0)

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        if self.robot is not None:
            try:
                self.robot.disconnect()
            finally:
                self.robot = None
