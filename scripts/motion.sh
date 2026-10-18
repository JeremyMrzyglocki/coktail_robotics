#!/usr/bin/env bash
# Teach by hand / replay a motion with the CAN channels of scripts/ports.sh (see scripts/motion.py).
#   ./scripts/motion.sh record NAME [--waypoints]   |   ./scripts/motion.sh play NAME [--speed 1.0]
cd "$(dirname "$0")/.." || exit 1
source scripts/ports.sh
exec .venv/bin/python scripts/motion.py "$@" --left "$LEFT_CAN" --right "$RIGHT_CAN" \
    --max-speed "$MAX_SPEED" --gain-scale "$GAIN_SCALE" 2> >(grep -v '^INFO' >&2)
