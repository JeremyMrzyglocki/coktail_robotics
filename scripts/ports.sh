# Hardware mapping used by the wrapper scripts (sourced, not run). Edit here if an arm is swapped.
# Follower sides as seen on this robot: right arm on can1, left on can0 (moving the right leader
# drove the left follower with can0 as right). The OpenArm SDK default used by skills/pour is the
# opposite (right_arm = can0): it needs can_interfaces={'right_arm': 'can1', 'left_arm': 'can0'}.
# Leader sides follow their calibration files: only my_openarm_mini_right.json reads the gripper of
# ...58FA101582 correctly (closed = 0), so that one is the right leader.
# Check the pairs with ./scripts/watch.sh and ./scripts/teleop.sh both --directions.
# Leaders by USB serial number, so the mapping survives replugging (ttyACM0/1 can swap).
RIGHT_LEADER=/dev/serial/by-id/usb-1a86_USB_Single_Serial_58FA101582-if00
RIGHT_CAN=can1
LEFT_LEADER=/dev/serial/by-id/usb-1a86_USB_Single_Serial_5876042927-if00
LEFT_CAN=can0
# Cameras for record.sh / grasp.sh, NAME=SOURCE[,rotate=DEG][,depth] (see rig.py; find them with
# `uv run lerobot-find-cameras realsense|opencv` or scripts/usb_camera_preview.py --list).
# Use the same list for recording and for running the policy: NAME is the dataset key.
# front = RealSense D455 (serial 151422253450), mounted upside down, digital zoom x1.1, RGB only
# (PI0.5 ignores depth).
# back = HBV HD CAMERA (USB, by-id path survives replugs); ~11 fps measured in the VM.
CAMERAS=(front=realsense:151422253450,rotate=180,zoom=1.1 back=/dev/v4l/by-id/usb-HBV_HD_CAMERA_HBV_HD_CAMERA-video-index0)

# Task text of the dataset (record.sh --task): keep it identical for every episode, PI0.5 reads it.
TASK="Pick up the tea bag with the right arm, pick up the cup with the left arm, and put the tea bag in the cup"

# Follower tuning for teleop.sh, record.sh and grasp.sh (a command-line option still wins).
# Raise step by step once the joint directions are validated, reading the tracking summary printed
# at the end of each run / episode:
#   MAX_SPEED   per-joint speed cap, deg/s: 30 -> 60 -> 90 if "at cap" is often high.
#   GAIN_SCALE  fraction of LeRobot's kp/kd: 0.3 -> 0.5 -> 0.7 if "err" exceeds a few deg
#               (sag under gravity, lag), e.g. while holding the bottle.
# The slow approach at start (10 deg/s) does not depend on these.
MAX_SPEED=60  # 30 capped the right wrist 13-15 % of the time (first both-arm session)
GAIN_SCALE=0.5  # 0.3 left the right gripper 13 deg behind on average
