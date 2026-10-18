# Robot day: bring-up, recording, training, grasp + pour

Everything runs from the repo root in the Ubuntu VM. Hardware mapping (leaders by USB serial, CAN
channels, cameras) lives in `scripts/ports.sh`: edit it there, every wrapper reads it.

Before the robot comes back:
- VM disk: 23 GB, 98 % full. Grow it in VMware to 60 GB or more, then in Ubuntu
  `sudo growpart /dev/sda 3 && sudo lvextend -r -l +100%FREE /dev/ubuntu-vg/ubuntu-lv`
  (check the disk/partition with `lsblk` first).
- VM CPUs: 2. Recording encodes every camera while the control loop runs; give the VM 4+ cores.

## 1. Bring-up (read-only)

```bash
./scripts/setup_can.sh          # can0/can1 in CAN FD; redo after every reboot or PCAN replug
./scripts/teleop.sh both        # all 16 follower motors answer, no fault, within limits
./scripts/watch.sh              # live table; move each leader: its own column must change
```
If a leader drives the wrong column, swap `LEFT_LEADER` / `RIGHT_LEADER` in `scripts/ports.sh`.
Also check the sides: on this robot the right follower is on `can1` and the left on `can0`, the
opposite of the OpenArm SDK default; `skills/pour` gets it from
`skills/pour/config/openarm_cocktail.yaml`. Leader sides come from their gripper
calibration (closed reads 0 only with the leader's own file). The side picks the joint limits and
the leader's joint flips: a wrong side shows up as joints moving the mirrored way.

## 2. Joint directions (read-only)

```bash
./scripts/teleop.sh both --directions
```
Put each leader in its follower's pose, Enter; move a few joints 20-40 deg the same way on the leader
and on the follower, Enter. Joints reported `OPPOSITE` are inverted on `y` (saved in
`calibration/teleop_flips.json`, applied everywhere). Do joints 1-4, then rerun for 5-7 and the
gripper. `only one moved` on many joints = leader/follower pairs swapped (fix `ports.sh`).

## 3. First teleop

```bash
./scripts/teleop.sh left --run   # then right, then both
```
Type `GO`. The follower stiffens over 2 s, moves to the leader's pose at 10 deg/s (keep the leader
still), then follows at up to 30 deg/s. Ctrl+C (or closing the terminal) disables torque: the arm
goes limp, so bring it near its rest pose first.

## 4. Record

```bash
uv run lerobot-find-cameras opencv   # set CAMERAS=(...) in scripts/ports.sh
uv run scripts/usb_camera_preview.py --list                  # USB cameras + stable /dev/v4l/by-id paths
uv run scripts/usb_camera_preview.py /dev/video4,rotate=180  # check the image as recorded (q quits)
./scripts/record.sh --episodes 10 --episode-time 30 --push
```
- Same start as the teleop. While recording: Enter ends the episode, `r` + Enter redoes it,
  `q` + Enter saves and quits. Between episodes the teleop stays on, nothing is recorded: reset the
  scene, Enter.
- End every episode in the handoff pose and hold it ~2 s: the policy learns to stop there, which is
  how `grasp.sh` knows the grasp is done.
- More episodes later: `./scripts/record.sh --resume --push`. Keep cameras (names, placement,
  rotate / crop / zoom of `CAMERAS`) and `--task` identical for the whole dataset. `grasp.sh` reads
  the same `CAMERAS`, so the policy sees the frames preprocessed as in training. A crop added
  later can be applied to the episodes already recorded: `scripts/crop_dataset_camera.py`.
- The follower is controlled at `--control-hz` (default 60, a multiple of `--fps`) and one frame
  is recorded every control_hz / fps cycles, so the teleop is smoother than the 30 fps dataset.
- Each episode prints its slowest control cycle; it should stay under the 17 ms budget at 60 Hz.
  If it does not, use `--control-hz 30`, fewer cameras or more VM cores.
- The follower also gets the command's velocity (MIT `dq`), so its damping only resists the error
  to the intended motion instead of braking every move.
- Dataset `antonin-leroy/cocktail-grasp`: `observation.state` = follower joints (deg), `action` =
  command sent to the follower (deg), `observation.images.<camera>` (h264), names
  `left_joint_1.pos` ... `right_gripper.pos` as in LeRobot's `bi_openarm_follower`.
- Check an episode: `uv run lerobot-dataset-viz --repo-id antonin-leroy/cocktail-grasp --episode-index 0`.

Test without hardware: `uv run python scripts/record.py --sim --camera top=0 --repo-id local/sim-test
--episodes 2 --episode-time 3 --reset-time 1`.

## 5. Train ACT on AWS EC2

Instance `g5.xlarge` (A10G 24 GB, ~1 $/h), AMI "Deep Learning Base OSS Nvidia Driver GPU AMI
(Ubuntu 22.04)", 100 GB disk. AMI id for a region:
`aws ssm get-parameter --region eu-central-1 --name /aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-22.04/latest/ami-id --query Parameter.Value --output text`.

```bash
ssh ubuntu@<instance>
nvidia-smi                           # driver >= 570 (the locked torch is built for CUDA 12.8)
git clone https://github.com/antonin-leroy/coktail_robotics.git && cd coktail_robotics
export HF_TOKEN=hf_...               # write token
tmux new -s train                    # survives an SSH disconnect
./scripts/train_act.sh antonin-leroy/cocktail-grasp antonin-leroy/act-cocktail-grasp
```
- Env overrides `STEPS` (100000), `BATCH_SIZE` (8), `WANDB=true`; extra args go to `lerobot-train`.
- Resume: `uv run lerobot-train --config_path=outputs/train/<job>/checkpoints/last/pretrained_model/train_config.json --resume=true`.
- Hub permissions: a personal account cannot share private repos or let someone else push into it.
  If the partner trains, either make the dataset public and push the model to their namespace, or
  use a shared Hugging Face organization for both.
- Stop the instance when done.

## 6. Grasp with the policy, then pour

```bash
./scripts/grasp.sh antonin-leroy/act-cocktail-grasp                     # grasp only
./scripts/cocktail.sh https://huggingface.co/antonin-leroy/act-cocktail-grasp \
    --container red --grams 60                                          # grasp, then pour
```
`cocktail.sh` takes the model's Hub link (or repo id, or a local dir), checks the pour environment
(`~/venvs/pour`, `POUR_PYTHON`) before anything moves, then runs `grasp.sh MODEL --then` with
`skills/pour/pour_skill.py --backend openarm` and the arguments after the link. In Claude Code,
`/cocktail <link> [colour] [grams]` runs the read-only checks (model inputs vs `CAMERAS`, CAN,
motors, SDK) and gives you that command.
1. Loads the policy and refuses to start if it was trained with other arms or cameras.
2. Preflight against the policy's first action, `GO`, gain ramp, slow move to that first action.
3. The policy drives both arms with the teleop's speed cap, joint limits and safety stops.
4. Done when its targets stay still for 2 s (`--settle-time`), on Enter, or after `--max-time` (60 s).
5. With `--then`: the follower keeps holding the handoff pose with torque ON, our CAN sockets close
   without disabling the motors, the cameras are released, and the command runs and takes over
   the motors.
   Without `--then`: it holds until Enter, then releases torque (take the objects first).

On the VM CPU, ACT replans every 100 steps and that cycle takes ~0.2 s: the arm pauses briefly
(it holds its last command, no jump). A faster machine or GPU removes the pause.

Handover to `skills/pour` (read from openarm-driver 0.5.1, not tried on the robot yet):
- Its `Robot.enable()` calls `SingleArmDriver.start()`, which enables the motors and holds the
  measured pose (no disable first); `robot_io` skips the start trajectory. Only the pouring arm
  (`PourConfig.arm`, right by default) is taken over; the other arm keeps holding our last command.
- The motors hold that last command only while their Damiao CAN timeout allows it (0 = forever).
- `skills/pour/robot_io.py` uses `skills/pour/config/openarm_cocktail.yaml` (SDK's
  `openarm_cell_higher_pd_zero_offset.yaml` with right arm = can1, zero offsets, and the joint
  limits of `teleop_safe.py`): the SDK default `openarm_cell.yaml` has Enactic jig offsets
  (J3 +90 deg, J4 -100 deg, ...) and limits of +-90 deg on J3/J5, which would clip this robot's
  poses (both the SDK and `robot_io` clip the whole target vector to them).
- To settle before chaining them on the robot:
  - The SDK drives the gripper in POS_FORCE mode with a torque limit: check on the robot that the
    takeover does not loosen the grip on the bottle.
  - `openarm_can` + `openarm-driver` must be installed in this VM (see
    `skills/pour/setup_robot_vm.sh`): only one VM can own the PCAN adapter.
- LeRobot's `OpenArmFollower.connect()` would not work for a takeover: its `configure()` disables
  then re-enables torque, and the arm would drop the bottle.

Test without hardware: `uv run python scripts/run_policy.py --sim --camera top=0 --policy <dir>`
with any ACT checkpoint trained on a `--sim` dataset.
