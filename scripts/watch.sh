#!/usr/bin/env bash
# Live read-only view of leader and follower positions (no torque). Ctrl+C to stop.
cd "$(dirname "$0")/.." && exec .venv/bin/python scripts/teleop_safe.py \
    --left /dev/ttyACM0:can0 --right /dev/ttyACM1:can1 --watch "$@" 2> >(grep -v '^INFO' >&2)
