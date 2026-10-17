# Cocktail Robotics

Work in progress.

## Setup

```bash
uv sync
```

Installs [LeRobot](https://github.com/huggingface/lerobot) (pinned commit, with Feetech + Damiao motor support) and MuJoCo.

## Skills

| Skill | Folder | Role |
|---|---|---|
| pour | [`skills/pour/`](skills/pour/) | Scripted pouring of M&M's (30/60/90 g or a whole bottle) in closed loop with vision + motor torque. Bar state and LLM context for cocktails. |

Each skill takes the shared robot object from the orchestrator and never opens its own CAN
connection, e.g. `from skills.pour import pour` then `pour(robot, 60, "red", ...)`.
Run the pour skill in simulation from the repo root:

```bash
uv run --with-requirements skills/pour/requirements.txt python skills/pour/pour_skill.py --container red --grams 60
```

See [`skills/pour/README.md`](skills/pour/README.md) for details (in French).

## Calibration

`calibration/teleoperators/openarm_mini/` holds the calibration of our OpenArm Mini leader
(`my_openarm_mini_left.json`, `my_openarm_mini_right.json`). It only matches this physical
leader: the homing offsets are also stored in its servos.

Point LeRobot at it with `--teleop.calibration_dir=calibration/teleoperators/openarm_mini`
and `--teleop.id=my_openarm_mini` (bimanual) or `my_openarm_mini_left` / `my_openarm_mini_right` (single arm).
Do not re-run `lerobot-calibrate` on the leader unless needed: its grippers travel more than half a turn and
need a dedicated gripper calibration afterwards.
