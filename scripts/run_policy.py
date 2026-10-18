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
  ./scripts/grasp.sh antonin-leroy/pi05-cocktail-grasp --remote NAMESPACE/cocktail-policy   # GPU Space

--remote runs the policy on a Hugging Face GPU (scripts/remote_policy.py deploys it): the robot
executes each chunk while the next one is computed from a fresh observation, sent --refill s before
the end; the steps that went by during the round trip are skipped. If no chunk arrives the arm holds
its last target, and after --remote-timeout s the run stops as on Enter (pose held, torque on).
"""

import argparse
import shlex
import subprocess
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

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

    def observe(self, follower_deg: dict[str, dict[str, float]]) -> tuple[np.ndarray, dict]:
        state = np.array([follower_deg[a.side][n] for a in self.arms for n in NAMES], dtype=np.float32)
        return state, read_images(self.cameras, self.specs)

    def to_sides(self, vec) -> dict[str, dict[str, float]]:
        out = {a.side: {} for a in self.arms}
        for key, value in zip(self.keys, vec):
            side, joint = key.removesuffix(".pos").split("_", 1)
            out[side][joint] = float(value)
        return out

    def act(self, follower_deg: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        state, images = self.observe(follower_deg)
        obs = {"observation.state": state, **{f"observation.images.{k}": v for k, v in images.items()}}
        obs = prepare_observation_for_inference(obs, self.device, self.task, ROBOT_TYPE)
        with torch.inference_mode():
            action = self.post(self.policy.select_action(self.pre(obs)))
        return self.to_sides(action.squeeze(0).cpu().numpy())


class RemoteDriver(PolicyDriver):
    """Same interface as PolicyDriver, the policy runs on a GPU Space (scripts/remote_policy.py).

    act() is called at the control rate and never waits once the first chunk is in: it pops the
    next action and, when --refill s are left, sends the current observation in a background
    thread. A chunk computed from the observation of tick k is applied from the current tick on.
    """

    def __init__(self, space: str, path: str, arms, cameras, specs, task: str, fps: float, refill_s: float):
        from remote_policy import RemotePolicy

        self.cfg = PreTrainedConfig.from_pretrained(path)  # config.json only: the feature check
        self.arms, self.cameras, self.specs, self.task = arms, cameras, specs, task
        self.keys = joint_keys(arms)
        self._check_features()
        self.client = RemotePolicy(space)
        info = self.client.wait_ready()
        if info["policy"] != path:
            raise SystemExit(f"the Space serves {info['policy']}, not {path}: "
                             f"scripts/remote_policy.py deploy {path}")
        print(f"Remote policy {info['type']} on {info['gpu'] or info['device']} ({self.client.url})")
        self.refill = max(1, round(refill_s * fps))
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.round_trips: list[float] = []
        self.last = None  # only the very first chunk is waited for: later on, a missing one holds this
        self.reset()

    def reset(self):
        self.queue, self.pending, self.tick, self.starved_since = deque(), None, 0, None

    def _send(self, follower_deg):
        state, images = self.observe(follower_deg)
        t0 = time.monotonic()
        self.pending = (self.tick, t0, self.pool.submit(self.client.act, state, images, self.task, ROBOT_TYPE))

    def _receive(self, wait: bool):
        sent_tick, t0, future = self.pending
        if not wait and not future.done():
            return
        self.pending = None
        try:
            actions, _ = future.result()
        except Exception as e:  # noqa: BLE001  network / server error: hold, retry on the next tick
            print(f"\n  remote policy: {type(e).__name__}: {e}")
            if wait:
                raise
            return
        self.round_trips.append(time.monotonic() - t0)
        self.queue = deque(actions[self.tick - sent_tick:])  # the steps that went by are skipped

    @property
    def starved_s(self) -> float:
        return 0.0 if self.starved_since is None else time.monotonic() - self.starved_since

    def act(self, follower_deg: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        if self.pending is None and len(self.queue) <= self.refill:
            self._send(follower_deg)
        if self.pending is not None:
            self._receive(wait=self.last is None)  # the very first chunk: wait for it
        if self.queue:
            self.last, self.starved_since = self.queue.popleft(), None
        elif self.starved_since is None:
            self.starved_since = time.monotonic()
        self.tick += 1
        return self.to_sides(self.last)

    def summary(self) -> str:
        if not self.round_trips:
            return "no remote chunk received"
        rt = np.array(self.round_trips) * 1000
        return f"{len(rt)} remote chunks, round trip p50 {np.median(rt):.0f} ms, max {rt.max():.0f} ms"


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
    p.add_argument("--remote", metavar="SPACE",
                   help="run the policy on this GPU Space (NAMESPACE/NAME or URL, scripts/remote_policy.py)")
    p.add_argument("--refill", type=float, default=0.6,
                   help="--remote: ask for the next chunk when this many s of actions are left")
    p.add_argument("--remote-timeout", type=float, default=3.0,
                   help="--remote: stop (holding the pose) after this many s without actions")
    args = p.parse_args()
    stop_on_signals()

    arms, cameras = build_rig(p, args)
    if args.remote:
        print(f"Connecting to the remote policy {args.policy} on {args.remote}...")
        driver = RemoteDriver(args.remote, args.policy, arms, cameras, args.camera, args.task,
                              args.fps, args.refill)
    else:
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
            if getattr(driver, "starved_s", 0.0) > args.remote_timeout:
                reason = f"no remote action for {args.remote_timeout:.0f} s"
                break
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))
        print(f"Grasp done ({reason}) after {time.monotonic() - t0:.1f} s; "
              f"slowest cycle {worst_tick * 1000:.0f} ms (budget {teleop.dt * 1000:.0f} ms).")
        if args.remote:
            print(driver.summary())

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
