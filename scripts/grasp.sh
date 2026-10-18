#!/usr/bin/env bash
# Run the grasp policy on both arms with the cameras of scripts/ports.sh, then optionally hand over.
#   ./scripts/grasp.sh antonin-leroy/act-cocktail-grasp
#   ./scripts/grasp.sh antonin-leroy/act-cocktail-grasp --then "uv run python pour.py"
cd "$(dirname "$0")/.." || exit 1
source scripts/ports.sh
if [[ $# -lt 1 ]]; then echo "usage: $0 <policy repo or dir> [run_policy.py args]"; exit 1; fi
POLICY=$1
shift
CAMS=()
for c in "${CAMERAS[@]}"; do CAMS+=(--camera "$c"); done
exec .venv/bin/python scripts/run_policy.py --left "$LEFT_CAN" --right "$RIGHT_CAN" "${CAMS[@]}" \
    --policy "$POLICY" --task "$TASK" --max-speed "$MAX_SPEED" --gain-scale "$GAIN_SCALE" "$@" 2> >(grep -v '^INFO' >&2)
