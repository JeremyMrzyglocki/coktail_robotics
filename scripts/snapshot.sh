#!/usr/bin/env bash
# Read-only robot snapshot with the mapping of scripts/ports.sh (arms in the reference pose).
#   ./scripts/snapshot.sh --note "before handing over"
#   ./scripts/snapshot.sh --compare calibration/snapshots/<date>.json
cd "$(dirname "$0")/.." || exit 1
source scripts/ports.sh
source scripts/reset_leaders.sh
reset_leaders "$LEFT_LEADER" "$RIGHT_LEADER"
exec .venv/bin/python scripts/snapshot.py --left "$LEFT_LEADER:$LEFT_CAN" --right "$RIGHT_LEADER:$RIGHT_CAN" \
    "$@" 2> >(grep -v '^INFO' >&2)
