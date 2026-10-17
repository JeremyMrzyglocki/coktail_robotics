#!/usr/bin/env bash
# Reference pose of the 4 arms (read-only): ./scripts/home.sh --save | ./scripts/home.sh | --once
cd "$(dirname "$0")/.." || exit 1
source scripts/ports.sh
source scripts/reset_leaders.sh
reset_leaders "$LEFT_LEADER" "$RIGHT_LEADER"
exec .venv/bin/python scripts/home.py --left "$LEFT_LEADER:$LEFT_CAN" --right "$RIGHT_LEADER:$RIGHT_CAN" "$@" \
    2> >(grep -v '^INFO' >&2)
