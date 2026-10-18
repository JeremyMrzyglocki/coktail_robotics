#!/usr/bin/env bash
# Robot side of the skill store web app (skill_store/): every plan deployed from the web page runs
# our policy end to end with grasp.sh, in this terminal (GO, Enter and Ctrl+C work as usual).
#   ./scripts/skillstore_runner.sh lleeoogg/act-cocktail-grasp-20261018-0415
#   ./scripts/skillstore_runner.sh lleeoogg/pi0-5-cocktail-grasp-20261018-042906 --remote cocktail-policy
#   ./scripts/skillstore_runner.sh MODEL --grasp-args=--sim            # no robot
# API: SKILLSTORE_API (default: the Mac on the Parallels network). Secret: ROBOT_SHARED_SECRET or
# ~/.skillstore_secret, the value of skill_store/.env on the Mac.
cd "$(dirname "$0")/.." || exit 1
MODEL="${1:?usage: $0 MODEL [--remote SPACE] [--max-time S] [--grasp-args=\"...\"]}"
shift
export SKILLSTORE_API="${SKILLSTORE_API:-http://10.211.55.2:8000}"
if [ -z "${ROBOT_SHARED_SECRET:-}" ] && [ -f ~/.skillstore_secret ]; then
    ROBOT_SHARED_SECRET="$(cat ~/.skillstore_secret)"
    export ROBOT_SHARED_SECRET
fi
exec python3 skill_store/runner/runner.py --openarm --model "$MODEL" --retries 0 "$@"
