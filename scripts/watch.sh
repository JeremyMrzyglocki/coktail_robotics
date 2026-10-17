#!/usr/bin/env bash
# Live read-only view of leader and follower positions (no torque). Ctrl+C to stop.
exec "$(dirname "$0")/teleop.sh" both --watch "$@"
