#!/usr/bin/env bash
# Usage: ./scripts/teleop.sh left|right|both [--run]
# Without --run: read-only check. With --run: check, then torque on after you type GO.
cd "$(dirname "$0")/.." || exit 1
LEFT=(--left /dev/ttyACM0:can0)
RIGHT=(--right /dev/ttyACM1:can1)
case "$1" in
    left) ARMS=("${LEFT[@]}") ;;
    right) ARMS=("${RIGHT[@]}") ;;
    both) ARMS=("${LEFT[@]}" "${RIGHT[@]}") ;;
    *) echo "usage: $0 left|right|both [--run]"; exit 1 ;;
esac
shift
exec .venv/bin/python scripts/teleop_safe.py "${ARMS[@]}" "$@" 2> >(grep -v '^INFO' >&2)
