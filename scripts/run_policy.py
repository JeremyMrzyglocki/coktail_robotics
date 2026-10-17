"""Run a trained policy (ACT) on the follower with the cautious start of teleop_safe.py, then hand over.

  1. load the policy (Hub repo or local pretrained_model dir) and check it expects these arms/cameras,
  2. preflight against the policy's first action, GO, gain ramp, slow move to that first action,
  3. the policy drives the arm (speed cap, joint limits, safety stops as in the teleop),
  4. the grasp is done when the policy's targets stay still for --settle-time (it learned to stop at
     the handoff pose), on Enter, or at --max-time,
  5. --then "CMD": keep holding the handoff pose with torque ON, close our CAN sockets without
     disabling the motors and run CMD (e.g. the scripted pour), which takes over the motors.
     Without --then: hold the pose until Enter, then release torque (the arm goes limp).

The follower's joints are sent and read exactly as recorded by record.py (same names and order).

Usage:
  uv run python scripts/run_policy.py --left can0 --right can1 --camera top=0 \
      --policy antonin-leroy/act-cocktail-grasp --then "uv run python pour.py"
  uv run python scripts/run_policy.py --sim --camera top=0 --policy outputs/train/<job>/checkpoints/last/pretrained_model
"""

import argparse
import shlex
import subprocess
import time

import numpy as np
import torch
from rig import (
    ROBOT_TYPE,
    add_rig_args,
    build_rig,
    drain,
    image_features,
    joint_keys,
    next_key,
    read_images,
    stdin_lines,
)
from teleop_safe import NAMES, Teleop, confirm_start, stop_on_signals

from lerobot.configs.policies import PreTrainedConfig
from lerobot.policies import prepare_observation_for_inference
from lerobot.policies.factory import get_policy_class, make_pre_post_processors


def pick_device(name: str) -> str:
    if name != "auto":
        return name
    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


class PolicyDriver:
    """Observation (follower degrees + camera frames) -> policy -> {side: {joint: deg}}."""

    def __init__(self, path: str, device: str, arms, cameras, specs, task: str):
        self.cfg = PreTrainedConfig.from_pretrained(path)
        self.cfg.device = device
        self.device = torch.device(device)
        self.policy = get_policy_class(self.cfg.type).from_pretrained(path, config=self.cfg)
        self.policy.eval()
        self.pre, self.post = make_pre_post_processors(
            self.cfg, pretrained_path=path, preprocessor_overrides={"device_processor": {"device": device}})
        self.arms, self.cameras, self.specs, self.task = arms, cameras, specs, task
        self.keys = joint_keys(arms)
        self._check_features()

    def _check_features(self):
        """Fail before any motion if the policy was trained on other arms or cameras."""
        want_images = {k.removeprefix("observation.images.") for k in self.cfg.input_features
                       if k.startswith("observation.images.")}
        state = self.cfg.input_features.get("observation.state")
        action = self.cfg.output_features.get("action")
        problems = []
        have_images = set(image_features(self.specs, 0, 0))
        if have_images != want_images:
            problems.append(f"cameras: policy wants {sorted(want_images)}, got {sorted(have_images)}")
        if state is None or tuple(state.shape) != (len(self.keys),):
            problems.append(f"observation.state: policy wants {state and tuple(state.shape)}, "
                            f"got ({len(self.keys)},) for arms {[a.side for a in self.arms]}")
        if action is None or tuple(action.shape) != (len(self.keys),):
            problems.append(f"action: policy outputs {action and tuple(action.shape)}, need ({len(self.keys)},)")
        if problems:
            raise SystemExit("Policy does not match this setup:\n  " + "\n  ".join(problems))

    def reset(self):
        self.policy.reset()

    def act(self, follower_deg: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        obs = {"observation.state": np.array(
            [follower_deg[a.side][n] for a in self.arms for n in NAMES], dtype=np.float32)}
        for name, img in read_images(self.cameras, self.specs).items():
            obs[f"observation.images.{name}"] = img
        obs = prepare_observation_for_inference(obs, self.device, self.task, ROBOT_TYPE)
        with torch.inference_mode():
            action = self.post(self.policy.select_action(self.pre(obs)))
        vec = action.squeeze(0).cpu().numpy()
        out = {a.side: {} for a in self.arms}
        for key, value in zip(self.keys, vec):
            side, joint = key.removesuffix(".pos").split("_", 1)
            out[side][joint] = float(value)
        return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_rig_args(p, with_leader=False)
    p.add_argument("--policy", required=True, help="Hub repo id or local pretrained_model dir")
    p.add_argument("--device", default="auto", help="auto, cuda, mps or cpu")
    p.add_argument("--task", default="Grasp the bottle and the glass and bring them to the handoff pose")
    p.add_argument("--max-time", type=float, default=60.0, help="stop the policy after this many s")
    p.add_argument("--min-time", type=float, default=3.0, help="no 'done' detection before this many s")
    p.add_argument("--settle-time", type=float, default=2.0,
                   help="done when the policy's targets move less than --settle-deg for this long, s")
    p.add_argument("--settle-deg", type=float, default=1.0)
    p.add_argument("--then", help="command to run after the grasp, torque kept on (e.g. the pour script)")
    args = p.parse_args()
    stop_on_signals()

    arms, cameras = build_rig(p, args)
    device = pick_device(args.device)
    print(f"Loading policy {args.policy} on {device}...")
    driver = PolicyDriver(args.policy, device, arms, cameras, args.camera, args.task)

    started, handed_over = False, False
    try:
        for arm in arms:
            arm.connect()
        for cam in cameras.values():
            cam.connect()

        # First action from the current pose: the arm will first move there slowly.
        states = {arm.side: arm.follower_states() for arm in arms}
        missing = [f"{s} {n}" for s, st in states.items() for n in NAMES if n not in st]
        if missing:
            raise RuntimeError(f"no answer from {missing}")
        driver.reset()
        first = driver.act({s: {n: float(np.degrees(st[n].q)) for n in NAMES} for s, st in states.items()})
        if not args.sim and not confirm_start(arms, args.approach_speed, targets=lambda arm: first[arm.side]):
            return
        started = True
        keys = stdin_lines()

        teleop = Teleop(arms, args.fps, args.max_speed, args.approach_speed, args.gain_scale, args.ramp,
                        targets=lambda arm: first[arm.side])
        teleop.start()
        while not teleop.synced:
            start = time.monotonic()
            teleop.step()
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))

        # Live policy, replanned from the pose actually reached.
        driver.reset()
        current = driver.act(teleop.measured)
        teleop.retarget(lambda arm: current[arm.side])
        drain(keys)
        print("Policy running. Enter = stop here (hold the pose), Ctrl+C = stop and release torque.")
        t0 = time.monotonic()
        still_since, last = t0, {s: dict(v) for s, v in current.items()}
        worst_tick, reason = 0.0, "max time"
        while time.monotonic() - t0 < args.max_time:
            start = time.monotonic()
            current.update(driver.act(teleop.measured))
            teleop.step()
            now = time.monotonic()
            worst_tick = max(worst_tick, now - start)
            moved = max(abs(current[s][n] - last[s][n]) for s in current for n in NAMES)
            if moved > args.settle_deg:
                still_since, last = now, {s: dict(v) for s, v in current.items()}
            if now - t0 > args.min_time and now - still_since > args.settle_time:
                reason = "policy settled"
                break
            if next_key(keys) is not None:
                reason = "Enter"
                break
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))
        print(f"Grasp done ({reason}) after {time.monotonic() - t0:.1f} s; "
              f"slowest cycle {worst_tick * 1000:.0f} ms (budget {teleop.dt * 1000:.0f} ms).")

        # Let the follower finish reaching the last target, then hold it.
        for _ in range(int(2.0 / teleop.dt)):
            start = time.monotonic()
            teleop.step()
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))

        if args.then:
            teleop.hold()
            for arm in arms:
                arm.disconnect(keep_torque=True)
            for cam in cameras.values():  # free them: the next script may use the same camera
                cam.disconnect()
            cameras.clear()
            handed_over = True
            print(f"Torque kept ON at the handoff pose. Running: {args.then}")
            result = subprocess.run(shlex.split(args.then))
            print(f"'{args.then}' exited with code {result.returncode}. "
                  "The motors are still in whatever state that script left them.")
            return
        drain(keys)
        print("Holding the handoff pose. Enter = release torque (the arm goes limp, hold the objects).")
        while next_key(keys) is None:
            start = time.monotonic()
            teleop.hold()
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))
    except KeyboardInterrupt:
        print("\nStopping.")
    except Exception as e:  # noqa: BLE001
        print(f"\nSAFETY STOP: {e}")
    finally:
        if not handed_over:
            for arm in arms:
                arm.disconnect()
        for cam in cameras.values():
            cam.disconnect()
        if started and not args.sim and not handed_over:
            print("Warning: could not confirm torque off." if any(a.enabled for a in arms) else "Torque disabled.")


if __name__ == "__main__":
    main()
