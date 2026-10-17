---
name: cocktail
description: Run the trained grasp model from its Hugging Face link, then the pour skill (grasp the bottle and the glass, stop in the handoff pose, pour). Use when the user gives a model link or repo id to run on the robot, e.g. "/cocktail https://huggingface.co/antonin-leroy/act-cocktail-grasp red 60".
argument-hint: <hf model link or user/name> [container] [grams]
---

# Run grasp + pour with a model link

Arguments: `$ARGUMENTS` (model link or repo id, then optionally the bottle colour and the grams).
Defaults: container `red`, grams `60`. Containers and cocktails: `skills/pour/containers.yaml`.

Rules (CLAUDE.md, AGENTS.md): you never start motion yourself. Everything below is read-only; the
user runs the final command, which asks them to type GO before any torque.

## 1. Read-only checks (stop at the first failure and say how to fix it)

1. Model id: a URL `https://huggingface.co/<user>/<name>[/...]` becomes `<user>/<name>`
   (`scripts/cocktail.sh` does the same). A `datasets/` link is not a model.
2. The model exists and its inputs match the robot: fetch its `config.json`
   (`curl -sfL https://huggingface.co/<id>/resolve/main/config.json`, with
   `-H "Authorization: Bearer $(cat ~/.cache/huggingface/token)"` if private). Check:
   - `input_features` has `observation.state` of shape [16] and one `observation.images.<name>` per
     camera in `CAMERAS=(...)` of `scripts/ports.sh`, same names (e.g. `front`, `back`);
   - `output_features.action` has shape [16].
   A mismatch means the model was trained with other cameras: say which, do not edit `ports.sh`
   to fit unless the user agrees (it changes what the next recordings contain).
3. CAN up: `ip -details link show can0` / `can1` show `ERROR-ACTIVE`; otherwise
   `./scripts/setup_can.sh` (sends nothing).
4. Followers answer, no fault, none left enabled: `./scripts/teleop.sh both` (read-only check).
   Only the follower column, faults and "already ENABLED" matter here: the gaps are to the
   leaders, and the run repeats the check against the model's first pose.
5. Pour environment: `${POUR_PYTHON:-~/venvs/pour/bin/python} -c "import openarm_driver, yaml, cv2"`.
   Missing: `skills/pour/setup_robot_vm.sh --skip-can`.
6. The pour skill reads `skills/pour/config/openarm_cocktail.yaml` (right arm = can1, zero offsets,
   measured limits): check it exists and that its `can_interface` matches `RIGHT_CAN`/`LEFT_CAN` in
   `scripts/ports.sh`.

## 2. Give the command to the user

```
./scripts/cocktail.sh <model-id> --container <colour> --grams <grams>
```

Add `--sensor none` if no camera watches the glass (pulses weighed by torque, needs
`skills/pour/config/torque_calib.json`), `--camera N` for the glass camera otherwise. Suggest
typing it as `! ./scripts/cocktail.sh ...` so the output lands in the conversation.

Tell them what will happen: preflight table, they type GO, gains ramp up, slow approach to the
model's first pose, the model grasps (Enter stops it and holds), then torque stays ON while the
pour skill takes over the bottle arm. Ctrl+C during the grasp releases torque (arms fall, objects
drop): keep a hand ready to catch them.

## 3. After the run

Read the output: preflight problems, "Grasp done (...)" reason, the pour JSON (`success`,
`poured_g`, `reason`). If the pour did not start, the arms are still holding with torque on (CAN
timeout 0): the user must support the objects before anything disables torque.
