#!/usr/bin/env bash
# Usage: ./scripts/teleop.sh left|right|both [--run | --watch | --directions | --align JOINT...]
# Without a mode: read-only check. --run: check, then torque on after you type GO.
cd "$(dirname "$0")/.." || exit 1
source scripts/ports.sh
LEFT=(--left "$LEFT_LEADER:$LEFT_CAN")
RIGHT=(--right "$RIGHT_LEADER:$RIGHT_CAN")
case "$1" in
    left) ARMS=("${LEFT[@]}") ;;
    right) ARMS=("${RIGHT[@]}") ;;
    both) ARMS=("${LEFT[@]}" "${RIGHT[@]}") ;;
    *) echo "usage: $0 left|right|both [--run | --watch | --directions]"; exit 1 ;;
esac
shift
exec .venv/bin/python scripts/teleop_safe.py "${ARMS[@]}" --max-speed "$MAX_SPEED" --gain-scale "$GAIN_SCALE" "$@" 2> >(grep -v '^INFO' >&2)
