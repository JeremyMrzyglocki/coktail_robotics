# Robot context for coding agents

State of the cocktail robot as of 2026-10-17, measured on the hardware. Read this before writing
code that moves the robot or reads its joints. `CLAUDE.md` (project rules) and `docs/PIPELINE.md`
(robot-day steps) complement it.

## Task

Bimanual OpenArm v10 (Enactic). A policy (ACT, trained on teleop data) grasps a bottle and a glass
and stops in a fixed handoff pose; then `skills/pour` pours (closed loop on vision and torque).

## Safety rules (from the team, non-negotiable)

- Never enable torque or command motion without a human's explicit go for that step.
- Read-only checks first. Interactive steps with hands on the robot are run by the human.
- Zero calibration writes the motors' zero: only with explicit agreement (see Calibration).
- Disabling torque makes an arm fall and its gripper release: never disable while it holds
  something, and never in a handover between programs.

## Hardware

- Followers: 2 x (7 joints + gripper), Damiao motors. joint_1-2 DM8009, joint_3-4 DM4340,
  joint_5-7 + gripper DM4310. Send IDs 0x01-0x08, feedback 0x11-0x18, MIT mode.
- CAN: PEAK PCAN-USB Pro FD, CAN FD 1 Mbps / 5 Mbps, sample point 0.75, in an Ubuntu ARM64 VM
  (VMware Fusion on a Mac, 2 cores). `./scripts/setup_can.sh` after every reboot or replug.
- **Sides on this robot: right follower = `can1`, left follower = `can0`.** This is the opposite of
  the OpenArm SDK default (`right_arm` = can0). `skills/pour/robot_io.py` reads it from
  `skills/pour/config/openarm_cocktail.yaml`; other SDK code must pass
  `can_interfaces={"right_arm": "can1", "left_arm": "can0"}` or it drives the wrong arm.
- Leaders: OpenArm Mini (Feetech STS3215), by USB serial in `scripts/ports.sh`:
  right = `...58FA101582`, left = `...5876042927`. Their calibration files
  (`calibration/teleoperators/openarm_mini/my_openarm_mini_{right,left}.json`) match offsets stored
  in the servos: do not re-run `lerobot-calibrate` on them. The side is proven by the gripper: it
  reads 0 when closed only with the leader's own file.
- `scripts/ports.sh` is the single source for leaders, CAN channels, cameras and teleop tuning.

## Joint conventions

- Follower angles are the raw motor angle in degrees (LeRobot `openarm_follower` convention, zero
  = arm hanging straight down, gripper closed). Gripper: 0 = closed, about -65 = open.
- Joint limits (deg) are LeRobot's per side, e.g. joint_2 left [-90, 9], right [-9, 90],
  joint_4 [0, 135], joint_5 [-85, 85], joint_6 [-40, 40], joint_7 [-80, 80], gripper [-65, 0].
- Follower zeros were rewritten on 2026-10-17 (previous values in `calibration/backups/`):
  joint_5 on both arms (zero moved to the middle of its 180 deg travel) and joint_3 on both arms
  (about 8-10 deg). All 16 motors read within ~5 deg of 0 in the reference pose.
- Our zero is the motors' zero of 2026-10-18 03:43 (dataset, policies, home pose, limits). When
  another team calibrates the robot (LeRobot `openarm_follower` re-zeros every motor), do not
  re-zero by hand: `./scripts/zero_check.sh` (torque off; each joint to both stops, then the
  reference pose with the marks aligned, Enter) measures the shift against
  `calibration/zero_reference.json` and writes `calibration/zero_offsets.json` (read by `Arm` in
  `teleop_safe.py`: our angle = motor angle - offset) and the `joint_offsets` of the pour config.
  `zero_check.sh save` records the reference: only while the zeros are ours.
- `skills/pour` uses `openarm_driver`, whose default config `openarm_cell.yaml` subtracts Enactic
  jig offsets (J3 +90 deg, J4 -100 deg, ...). They do not match this robot (offsets are 0 here):
  or the poses and its limit checks are wrong. `skills/pour/config/openarm_cocktail.yaml` is this
  robot's config (zero offsets, can1 = right, the joint limits of `teleop_safe.py` in rad: keep it
  in sync with `calibration/joint_limits.json`); `robot_io.py` loads it for the driver and its own
  clipping.

## Leader -> follower mapping (teleop)

LeRobot's `OpenArmMini.get_action()` already applies per-side flips and swaps leader joint_6/7
with follower joint_7/6. On top of it, `scripts/teleop_safe.py` applies, per side, in this order:
1. `calibration/teleop_swaps.json`: both sides `[["joint_6", "joint_7"]]`, which undoes
   LeRobot's 6/7 swap. Needed because the wrist roll zeros of leader and follower are ~90 deg
   apart, which turns the wrist pitch axis into the yaw axis.
2. `calibration/teleop_flips.json`: left `["joint_6"]` (sign inverted).
3. `calibration/teleop_offsets.json`: joint_5 +87.5 deg left, +103.5 deg right (leader reading +
   offset = follower angle in a matched pose).
4. Unwrap: a leader joint crossing +-180 deg stays continuous instead of jumping.
Tools (read-only): `./scripts/teleop.sh both --directions` (fixes flips), `--align JOINT...`
(measures offsets, elbow bent so joint_3 and joint_5 are not ambiguous), `./scripts/watch.sh`.

## Teleop controller (`scripts/teleop_safe.py`)

- Not LeRobot's `openarm_follower`: its `connect()` enables torque and jumps to the target at full
  gains, and its calibration zeroes all motors when no file exists.
- Start: preflight (all motors answer, no fault, follower within limits +-5 deg, target not >20 deg
  past a limit), typed `GO`, gains ramp from 0 over 2 s holding the pose, slow approach to the
  target at 10 deg/s, then tracking with a per-joint speed cap and the command velocity sent as MIT
  `dq` (feedforward).
- Tuning in `ports.sh`: `MAX_SPEED=60` deg/s, `GAIN_SCALE=0.5` (of LeRobot kp/kd
  [240, 240, 240, 240, 24, 31, 25, 25] / [5, 5, 3, 5, 0.3, 0.3, 0.3, 0.3]). Measured with both arms:
  mean tracking error <= 2 deg (right gripper ~4 deg), speed cap hit <= 2 % of cycles.
- Safety stops (torque off): motor silent 0.5 s, motor fault code, > 80 C, tracking error > 60 deg,
  target jump > 45 deg in one cycle, Ctrl+C, SIGTERM/SIGHUP.
- The `Teleop` class is reused by `record.py` and `run_policy.py` with any target source.

## Data and policy

- `scripts/record.py` (`./scripts/record.sh`): LeRobotDataset v3 `antonin-leroy/cocktail-grasp`,
  `robot_type` `bi_openarm_follower`, 30 fps, control loop at 60 Hz. Vectors of 16, left arm first:
  `left_joint_1.pos` ... `right_gripper.pos`. `observation.state` = follower deg, `action` =
  command sent (deg), `observation.images.<camera>` (h264, cameras from `ports.sh`).
- `scripts/train_act.sh`: ACT with `lerobot-train` on a GPU box (AWS g5.xlarge), pushes the policy.
- `scripts/run_policy.py` (`./scripts/grasp.sh <policy>`): same cautious start, the policy drives,
  done when its targets stay still 2 s, then `--then "CMD"` keeps torque ON and closes our CAN
  sockets without disabling so CMD (the pour) takes over. Checked only in `--sim` so far.
- `--sim` (in `record.py`, `run_policy.py`) fakes arms and cameras for tests without hardware.

## Handover to `skills/pour`

`./scripts/cocktail.sh MODEL_LINK --container red --grams 60` (Claude Code: `/cocktail <link>`,
`.claude/skills/cocktail/`) = `grasp.sh MODEL --then` the pour skill, after checking that the pour
environment (`~/venvs/pour`, `POUR_PYTHON`) imports `openarm_driver`. Cameras are released before
the pour starts.

- `openarm_driver.SingleArmDriver.start()` enables and holds the measured pose (no disable first)
  and `robot_io` skips the start trajectory, so taking over a holding arm is possible. Only the
  pouring arm is taken over; the other keeps our last MIT command. Measured 2026-10-17: the Damiao
  CAN timeout (RID 9) is 0 on all 16 motors (they hold their last command forever) and
  CTRL_MODE is 1 (MIT).
- To check on the robot: the SDK drives the gripper in POS_FORCE mode with a torque limit, which
  may loosen the grip on the bottle at takeover.
- `openarm_can` + `openarm-driver` are not installed in this VM yet (`skills/pour/setup_robot_vm.sh`).
  Only one VM can own the PCAN adapter.

## Detecting changes made by another team

`./scripts/snapshot.sh --note "..."` (read-only, arms in the reference pose) saves
`calibration/snapshots/<date>.json`: follower angles and Damiao parameters, the calibration stored
in the leader servos (Homing_Offset, limits), what the leaders map to, mapping files, USB devices
and CAN settings. `./scripts/snapshot.sh --compare calibration/snapshots/<date>.json` lists every
difference. Leader servo calibration on 2026-10-17 matched `my_openarm_mini_{left,right}.json`
exactly. The Damiao SN parameter is identical on all motors, so it cannot detect swapped arms:
check the sides with `watch.sh` (move one follower by hand).

Reference snapshot before handing the robot to the next team: `calibration/snapshots/20261017_173713.json`
(pose: arms hanging, joint_3 ~+84 and joint_5 ~-82 deg on both arms, grippers closed, followers
aligned with leaders). When the robot comes back, put it in that pose and run
`./scripts/snapshot.sh --compare calibration/snapshots/20261017_173713.json`.

On 2026-10-17 all 16 motors were found ENABLED and holding with no program running in this VM
(likely enabled from another machine, e.g. `lerobot-setup-can --mode=test`, or a teleop cut off by
a USB drop). With CAN timeout 0 they hold forever. The preflight now flags "already ENABLED".

## Known limits

- VM: 2 cores, disk ~98 % full (grow it before long recording sessions).
- ACT on the VM CPU replans every 100 steps in ~0.2 s: brief pause, no jump.
- The PCAN once dropped off the VM's USB (xhci errors): rerun `setup_can.sh`.
- `hardware/damiao.py` carries a macOS PCAN `open_bus`; on Linux the scripts open socketcan.

## Second VM (Parallels, 2026-10-17)

- Ubuntu 26.04 ARM64 in Parallels Desktop (Standard edition: no `prlctl exec`, no USB controller
  setting), 4 cores / 8 GB. Same repo and `uv sync`; pyrealsense2 loads (glibc 2.43).
- Leaders over Parallels USB: the first open after a plug works, every later open finds no servo
  ("Missing motor IDs") with `xhci_hcd ... not part of TD` in `journalctl -k`. The wrappers that
  open the leaders (`teleop.sh`, `watch.sh`, `record.sh`, `snapshot.sh`) now reset them over USB
  first (`scripts/reset_leaders.sh`, needs a NOPASSWD sudoers rule for `/usr/bin/usbreset`; skipped
  without it). Measured: 3/3 checks OK in a row with the reset, 1/2 without.
- Cameras: `front` = D455 by serial, `rotate=180`, 640x480 RGB at 30 fps over USB 2;
  `back` = HBV HD CAMERA (0ac8:0346) by `/dev/v4l/by-id`, only ~11 fps in the VM whatever the
  format or exposure.
- Camera preprocessing (`rig.preprocess`, specs in `CAMERAS` of `ports.sh`, applied by
  `record.py` and `run_policy.py` alike): capture 640x480 at 30 fps, rotate (in the camera
  reader), crop, zoom, every output resized back to 640x480 RGB uint8.
  `front`: rotate 180, zoom x1.1 (centre 582x436 box). `back` (top view): crop 512x384 from
  x=16, y=40 (mat and grippers, laptop on the right left out). Episodes 0-47 of
  `antonin-leroy/cocktail-grasp` were recorded uncropped on `back` and cropped afterwards with
  `scripts/crop_dataset_camera.py` (2026-10-18; backup in `~/datasets_backup/` on the VM).
  Changing a camera's spec, placement or name invalidates the dataset and the trained policies.
- Home pose: `calibration/home_pose.json` (team's start pose, leaders held with the upper arm
  turned half a turn). `./scripts/home.sh` shows every joint's delta to it (live, read-only):
  bring leaders and followers back until all read ~0 (`--once`: exit 0 when within 15 deg).
  `--save` records a new one.
- Damiao check on 2026-10-17 with arms hanging: all 16 motors answer, no fault, none left
  enabled, followers within 5 deg of 0.
