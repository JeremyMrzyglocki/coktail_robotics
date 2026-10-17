# Hardware mapping used by the wrapper scripts (sourced, not run). Edit here if an arm is swapped.
# Sides follow the OpenArm SDK used by skills/pour (right_arm = can0, left_arm = can1); the
# leader/follower pairs are the ones used so far (leader ...5876042927 drives can0).
# Not verified on the robot yet: check with ./scripts/watch.sh and ./scripts/teleop.sh both --directions.
# Leaders by USB serial number, so the mapping survives replugging (ttyACM0/1 can swap).
RIGHT_LEADER=/dev/serial/by-id/usb-1a86_USB_Single_Serial_5876042927-if00
LEFT_LEADER=/dev/serial/by-id/usb-1a86_USB_Single_Serial_58FA101582-if00
RIGHT_CAN=can0
LEFT_CAN=can1
# Cameras for record.sh / grasp.sh, NAME=INDEX_OR_PATH (`uv run lerobot-find-cameras opencv`).
# Use the same list for recording and for running the policy.
CAMERAS=(top=0)
