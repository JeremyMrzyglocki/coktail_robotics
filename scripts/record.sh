#!/usr/bin/env bash
# Record episodes with both arms and the cameras of scripts/ports.sh. Extra args go to record.py,
# e.g. ./scripts/record.sh --episodes 10 --push    or    ./scripts/record.sh --resume --push
cd "$(dirname "$0")/.." || exit 1
source scripts/ports.sh
CAMS=()
for c in "${CAMERAS[@]}"; do CAMS+=(--camera "$c"); done
exec .venv/bin/python scripts/record.py --left "$LEFT_LEADER:$LEFT_CAN" --right "$RIGHT_LEADER:$RIGHT_CAN" \
    "${CAMS[@]}" "$@" 2> >(grep -v '^INFO' >&2)
