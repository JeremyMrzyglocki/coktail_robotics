#!/usr/bin/env bash
# Whole run: the grasp policy (from its Hugging Face link), then the pour skill on the arm that
# holds the bottle, with torque kept on in between (scripts/run_policy.py --then).
#   ./scripts/cocktail.sh https://huggingface.co/antonin-leroy/act-cocktail-grasp --container red --grams 60
#   ./scripts/cocktail.sh antonin-leroy/act-cocktail-grasp --container red --grams 30 --sensor none
# MODEL: a Hub model URL, a repo id (user/name) or a local pretrained_model dir. Everything after
# it goes to skills/pour/pour_skill.py (--container, --grams, --sensor, --camera, ...).
# The pour runs in the OpenArm SDK environment (skills/pour/setup_robot_vm.sh), POUR_PYTHON to
# override it. Grasp only: ./scripts/grasp.sh MODEL.
cd "$(dirname "$0")/.." || exit 1
if [[ $# -lt 1 ]]; then sed -n 2,10p "$0"; exit 1; fi

model=$1
shift
if [[ ! -d $model ]]; then
    # https://huggingface.co/user/name[/tree/main/...] -> user/name
    id=${model#http*://}
    id=${id#huggingface.co/}
    id=${id#hf.co/}
    if [[ $id == datasets/* || $id == spaces/* ]]; then
        echo "$model is a dataset or a Space, not a model."; exit 1
    fi
    IFS=/ read -r user name _ <<< "$id"
    if [[ -z $user || -z $name ]]; then echo "Cannot read a model id (user/name) from: $model"; exit 1; fi
    model=$user/$name
fi

POUR_PYTHON=${POUR_PYTHON:-$HOME/venvs/pour/bin/python}
# Checked before the grasp: once the bottle is held, a pour that cannot start leaves the arms holding.
if ! "$POUR_PYTHON" -c "import openarm_driver, yaml, cv2" 2>/dev/null; then
    echo "The pour environment ($POUR_PYTHON) lacks openarm_driver, yaml or cv2:"
    echo "run skills/pour/setup_robot_vm.sh --skip-can, or set POUR_PYTHON."
    exit 1
fi
pour="$POUR_PYTHON skills/pour/pour_skill.py --backend openarm --i-understand-motors-will-be-armed"
for a in "$@"; do pour+=" $(printf '%q' "$a")"; done

echo "Model: $model"
echo "Then:  $pour"
exec ./scripts/grasp.sh "$model" --then "$pour"
