# Cocktail Robotics

Work in progress.

## Setup

```bash
uv sync
```

Installs [LeRobot](https://github.com/huggingface/lerobot) (pinned commit, with Feetech + Damiao motor support) and MuJoCo.

## Calibration

`calibration/teleoperators/openarm_mini/` holds the calibration of our OpenArm Mini leader
(`my_openarm_mini_left.json`, `my_openarm_mini_right.json`). It only matches this physical
leader: the homing offsets are also stored in its servos.

Point LeRobot at it with `--teleop.calibration_dir=calibration/teleoperators/openarm_mini`
and `--teleop.id=my_openarm_mini` (bimanual) or `my_openarm_mini_left` / `my_openarm_mini_right` (single arm).
Do not re-run `lerobot-calibrate` on the leader unless needed: its grippers travel more than half a turn and
need a dedicated gripper calibration afterwards.
