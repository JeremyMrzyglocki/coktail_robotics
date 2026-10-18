#!/usr/bin/env bash
# Our zero without writing the motors (scripts/zero_check.py). Torque off, read-only on the robot.
#   ./scripts/zero_check.sh save   # once, while the zeros are ours
#   ./scripts/zero_check.sh        # each time the robot comes back from another team
cd "$(dirname "$0")/.." || exit 1
source scripts/ports.sh
exec .venv/bin/python scripts/zero_check.py --left "$LEFT_CAN" --right "$RIGHT_CAN" "$@" 2> >(grep -v '^INFO' >&2)
