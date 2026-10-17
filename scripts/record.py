"""Record teleoperated episodes as a LeRobotDataset v3, with the cautious teleop of teleop_safe.py.

Features use LeRobot's bi_openarm_follower names (left_joint_1.pos, ..., right_gripper.pos), so a
policy trained on the dataset can be run by scripts/run_policy.py (or LeRobot's own tools).
  observation.state           follower joint positions (deg)
  action                      position command sent to the follower (deg)
  observation.images.<name>   one video per --camera

Flow: preflight + GO (as in teleop_safe --run), the follower moves slowly to the leader's pose, then
for each episode: record until --episode-time or Enter, then a reset phase (the teleop keeps
running, nothing is recorded) until Enter. Type r + Enter while recording to redo the episode,
q + Enter to save what was recorded and quit (also works during the reset phase).

--sim replaces the arms and cameras by fakes: no hardware, used to test the pipeline end to end.

Usage:
  uv run python scripts/record.py --left /dev/ttyACM0:can0 --right /dev/ttyACM1:can1 \
      --camera top=0 --task "Grasp the bottle and the glass" --episodes 10 --episode-time 30 --push
  uv run python scripts/record.py --sim --camera top=0 --repo-id local/sim-test --episodes 2 \
      --episode-time 3 --reset-time 1
"""

import argparse
import shutil
import time
from pathlib import Path

import numpy as np
from rig import ROBOT_TYPE, add_rig_args, build_rig, drain, joint_keys, next_key, stdin_lines
from teleop_safe import NAMES, Teleop, confirm_start, stop_on_signals

from lerobot.configs.video import RGBEncoderConfig
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.utils.feature_utils import hw_to_dataset_features

# Encoders fast enough to run next to the control loop. h264 costs far less CPU than LeRobot's
# default AV1 (libsvtav1), which matters on the 2-core VM; both decode fine for training.
ENCODERS = {
    "h264": RGBEncoderConfig(vcodec="h264", preset="ultrafast", crf=23, g=2),
    "av1": RGBEncoderConfig(),
}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_rig_args(p)
    p.add_argument("--repo-id", default="antonin-leroy/cocktail-grasp", help="<hf_user>/<dataset_name>")
    p.add_argument("--root", type=Path, help="local dataset dir (default: ~/.cache/huggingface/lerobot/<repo-id>)")
    p.add_argument("--resume", action="store_true", help="append episodes to an existing local dataset")
    p.add_argument("--overwrite", action="store_true", help="delete an existing local dataset first")
    p.add_argument("--task", default="Grasp the bottle and the glass and bring them to the handoff pose")
    p.add_argument("--episodes", type=int, default=10)
    p.add_argument("--episode-time", type=float, default=30.0, help="max episode duration, s")
    p.add_argument("--reset-time", type=float, default=0.0,
                   help="reset phase duration, s (0: wait for Enter)")
    p.add_argument("--control-hz", type=float, default=60.0,
                   help="follower control rate, a multiple of --fps; one frame is recorded every "
                        "control_hz / fps cycles (default 60: smoother teleop, dataset still at --fps)")
    p.add_argument("--push", action="store_true", help="push the dataset to the Hugging Face Hub at the end")
    p.add_argument("--private", action="store_true")
    p.add_argument("--vcodec", choices=sorted(ENCODERS), default="h264", help="video codec (default h264)")
    args = p.parse_args()
    stop_on_signals()

    arms, cameras = build_rig(p, args)
    keys_order = joint_keys(arms)
    hw = {k: float for k in keys_order}
    features = {
        **hw_to_dataset_features(hw, "action"),
        **hw_to_dataset_features({**hw, **{c: (args.cam_height, args.cam_width, 3) for c in cameras}},
                                 "observation"),
    }

    root = args.root or Path.home() / ".cache" / "huggingface" / "lerobot" / args.repo_id
    if root.exists() and args.overwrite:
        shutil.rmtree(root)
    if root.exists() and not args.resume:
        p.error(f"{root} already exists: pass --resume to append or --overwrite to start over")
    if args.resume:
        dataset = LeRobotDataset.resume(args.repo_id, root=root, streaming_encoding=True,
                                        rgb_encoder=ENCODERS[args.vcodec])
        expected = {k: (v["dtype"], tuple(v["shape"])) for k, v in features.items()}
        found = {k: (v["dtype"], tuple(v["shape"])) for k, v in dataset.features.items() if k in expected
                 or k.startswith("observation.") or k == "action"}
        if expected != found or dataset.fps != args.fps:
            p.error(f"--resume: arms/cameras/fps differ from the dataset.\n  dataset: {found}, "
                    f"fps {dataset.fps}\n  now:     {expected}, fps {args.fps}")
    else:
        dataset = LeRobotDataset.create(args.repo_id, args.fps, features, root=root, robot_type=ROBOT_TYPE,
                                        # Encode videos while recording: no temporary PNG per frame.
                                        use_videos=True, streaming_encoding=True,
                                        rgb_encoder=ENCODERS[args.vcodec])

    started = False
    record_every = round(args.control_hz / args.fps)
    if record_every < 1 or abs(record_every * args.fps - args.control_hz) > 1e-6:
        p.error(f"--control-hz must be a multiple of --fps ({args.fps}), e.g. {2 * args.fps}")
    teleop = Teleop(arms, args.control_hz, args.max_speed, args.approach_speed, args.gain_scale, args.ramp)
    try:
        for arm in arms:
            arm.connect()
        for cam in cameras.values():
            cam.connect()
        if not args.sim and not confirm_start(arms, args.approach_speed):
            return
        started = True
        keys = stdin_lines()
        teleop.start()

        def tick():
            start = time.monotonic()
            teleop.step()
            return start

        def wait(start):
            time.sleep(max(0.0, teleop.dt - (time.monotonic() - start)))

        while not teleop.synced:
            wait(tick())

        saved, stop = 0, False
        while saved < args.episodes and not stop:
            drain(keys)
            print(f"\nEpisode {dataset.num_episodes} ({saved + 1}/{args.episodes}) recording. "
                  "Enter = end, r = redo, q = save and quit")
            t0, redo = time.monotonic(), False
            worst, late = 0.0, 0
            teleop.reset_stats()
            cycle_i = 0
            while time.monotonic() - t0 < args.episode_time:
                start = tick()
                if cycle_i % record_every == 0:  # control runs faster than the dataset fps
                    images = {c: cam.read_latest() for c, cam in cameras.items()}
                    state = {f"{a.side}_{n}.pos": teleop.measured[a.side][n] for a in arms for n in NAMES}
                    action = {f"{a.side}_{n}.pos": teleop.cmd[a.side][n] for a in arms for n in NAMES}
                    dataset.add_frame({
                        "observation.state": np.array([state[k] for k in keys_order], dtype=np.float32),
                        "action": np.array([action[k] for k in keys_order], dtype=np.float32),
                        **{f"observation.images.{c}": img for c, img in images.items()},
                        "task": args.task,
                    })
                cycle_i += 1
                cycle = time.monotonic() - start
                worst, late = max(worst, cycle), late + (cycle > teleop.dt)
                key = next_key(keys)
                if key is not None:
                    redo, stop = key == "r", key == "q"
                    break
                wait(start)
            timing = f"slowest cycle {worst * 1000:.0f} ms, {late} over the {teleop.dt * 1000:.0f} ms budget"
            if redo:
                dataset.clear_episode_buffer()
                print(f"Discarded, it will be recorded again ({timing}).")
            else:
                dataset.save_episode()
                saved += 1
                print(f"Saved ({time.monotonic() - t0:.1f} s, {timing}).\n{teleop.summary()}")
            if stop or saved == args.episodes:
                break
            print("Reset the scene (teleop still on, not recording). "
                  + ("Enter = next episode, q = quit." if args.reset_time <= 0 else "q = quit."))
            t0 = time.monotonic()
            while True:
                start = tick()
                key = next_key(keys)
                if key == "q":
                    stop = True
                    break
                if args.reset_time > 0 and time.monotonic() - t0 >= args.reset_time:
                    break
                if args.reset_time <= 0 and key is not None:
                    break
                wait(start)
    except KeyboardInterrupt:
        print("\nStopping.")
    except Exception as e:  # noqa: BLE001
        print(f"\nSAFETY STOP: {e}")
    finally:
        for arm in arms:
            arm.disconnect()
        for cam in cameras.values():
            cam.disconnect()
        if started and not args.sim:
            print("Warning: could not confirm torque off." if any(a.enabled for a in arms) else "Torque disabled.")
        if dataset.has_pending_frames():
            dataset.clear_episode_buffer()
        dataset.finalize()
        print(f"Dataset: {root} ({dataset.num_episodes} episodes)")

    if args.push and dataset.num_episodes:
        dataset.push_to_hub(private=args.private)
        print(f"Pushed to https://huggingface.co/datasets/{args.repo_id}")


if __name__ == "__main__":
    main()
