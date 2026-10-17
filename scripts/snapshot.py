"""Read-only snapshot of the robot, to detect what someone else changed (zeros, servo calibration,
cabling, motor settings, mapping files). Never enables torque, never writes to a motor.

  ./scripts/snapshot.sh                          # save calibration/snapshots/<date>.json
  ./scripts/snapshot.sh --compare calibration/snapshots/<date>.json

Put the 4 arms in the reference pose first (hanging straight down, grippers closed): follower and
leader angles are only comparable between snapshots taken in the same pose.

Saved:
- followers, per CAN channel: angle, status and temperature of the 8 motors, plus Damiao
  parameters read with the 0x33 query (CAN timeout, control mode, IDs, firmware, PMAX/VMAX/TMAX;
  the SN parameter is the same on all 16 motors here, so it does not tell the arms apart);
- leaders, per USB serial: the calibration stored in the servos (Homing_Offset, position limits),
  raw positions, and the follower targets they map to (with teleop_swaps/flips/offsets);
- the mapping files, scripts/ports.sh, USB devices and CAN link settings.
"""

import argparse
import json
import math
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from teleop_safe import NAMES, ROOT, Arm, parse_pair  # noqa: E402

from hardware.damiao import ARM_MOTORS, collect_states, read_states  # noqa: E402

SNAP_DIR = ROOT / "calibration" / "snapshots"
QUERY_PARAM = 0x33
PARAM_ID = 0x7FF
# Damiao RIDs (lerobot.motors.damiao.tables.MotorVariable); the uint32 ones, the rest are float32.
PARAMS = {"MST_ID": 7, "ESC_ID": 8, "TIMEOUT": 9, "CTRL_MODE": 10, "SW_VER": 14, "SN": 15,
          "PMAX": 21, "VMAX": 22, "TMAX": 23, "CAN_BR": 35}
UINT_PARAMS = {"MST_ID", "ESC_ID", "TIMEOUT", "CTRL_MODE", "SW_VER", "SN", "CAN_BR"}
ANGLE_TOL_DEG = 3.0
FILES = ["calibration/teleop_swaps.json", "calibration/teleop_flips.json",
         "calibration/teleop_offsets.json", "scripts/ports.sh"]


def shell(cmd: str) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def query_params(bus, send_id: int, feedback_id: int) -> dict:
    """Damiao 0x33 parameter query (read-only), one RID at a time."""
    out = {}
    for name, rid in PARAMS.items():
        while bus.recv(timeout=0.005) is not None:  # nothing else must be in flight
            pass
        bus.send(can_message(PARAM_ID, [send_id & 0xFF, send_id >> 8, QUERY_PARAM, rid, 0, 0, 0, 0]))
        deadline = time.monotonic() + 0.1
        while (left := deadline - time.monotonic()) > 0:
            msg = bus.recv(timeout=left)
            if msg is None:
                break
            d = msg.data
            if msg.arbitration_id == feedback_id and len(d) >= 8 and d[2] == QUERY_PARAM and d[3] == rid:
                raw = bytes(d[4:8])
                out[name] = struct.unpack("<I", raw)[0] if name in UINT_PARAMS else round(
                    struct.unpack("<f", raw)[0], 4)
                break
        else:
            out[name] = None
        out.setdefault(name, None)
    return out


def can_message(arb_id, data):
    import can

    return can.Message(arbitration_id=arb_id, data=bytes(data), is_extended_id=False, is_fd=True,
                       bitrate_switch=True)


def follower_snapshot(arm: Arm) -> dict:
    states = read_states(arm.bus, timeout=0.3)
    motors = {}
    for name, send_id, _ in ARM_MOTORS:
        s = states.get(name)
        motors[name] = {
            "deg": None if s is None else round(math.degrees(s.q), 2),
            "status": None if s is None else s.status_name,
            "temp_mos": None if s is None else s.t_mos,
            "params": query_params(arm.bus, send_id, send_id + 0x10),
        }
    collect_states(arm.bus, ARM_MOTORS, timeout=0.05)  # drain stragglers
    return {"can": arm.can_channel, "motors": motors}


def leader_snapshot(arm: Arm) -> dict:
    bus = arm.leader.bus
    calib = bus.read_calibration()
    raw = bus.sync_read("Present_Position", normalize=False)
    targets = arm.leader_targets()
    return {
        "port": arm.leader.config.port,
        "servo_calibration": {m: {"homing_offset": c.homing_offset, "range_min": c.range_min,
                                  "range_max": c.range_max, "drive_mode": c.drive_mode}
                              for m, c in calib.items()},
        "raw_position": {m: int(v) for m, v in raw.items()},
        "follower_targets_deg": {n: round(targets[n], 2) for n in NAMES},
    }


def take(arms: list[Arm]) -> dict:
    snap = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "usb": shell("lsusb"),
        "serial_by_id": shell("ls -l /dev/serial/by-id/"),
        "can_links": {ch: shell(f"ip -details link show {ch}") for ch in ("can0", "can1")},
        "files": {f: (ROOT / f).read_text() if (ROOT / f).exists() else None for f in FILES},
        "git": shell(f"git -C {ROOT} log -1 --format='%h %s'"),
        "arms": {},
    }
    for arm in arms:
        print(f"Reading {arm.side} (leader {Path(arm.leader.config.port).name}, follower {arm.can_channel})...")
        snap["arms"][arm.side] = {"follower": follower_snapshot(arm), "leader": leader_snapshot(arm)}
    return snap


def compare(old: dict, new: dict) -> int:
    """Print what changed. Exact for settings and servo calibration; angles with a tolerance."""
    issues = 0

    def report(msg):
        nonlocal issues
        issues += 1
        print(f"  CHANGED  {msg}")

    print(f"\nComparing {old['date']} -> {new['date']}")
    for side in sorted(set(old["arms"]) | set(new["arms"])):
        o, n = old["arms"].get(side), new["arms"].get(side)
        if o is None or n is None:
            report(f"{side}: arm missing in one snapshot")
            continue
        of, nf = o["follower"], n["follower"]
        if of["can"] != nf["can"]:
            report(f"{side} follower channel {of['can']} -> {nf['can']}")
        for m in NAMES:
            om, nm = of["motors"][m], nf["motors"][m]
            for p in PARAMS:
                if om["params"].get(p) != nm["params"].get(p):
                    report(f"{side} follower {m} {p}: {om['params'].get(p)} -> {nm['params'].get(p)}")
            if om["deg"] is not None and nm["deg"] is not None and abs(om["deg"] - nm["deg"]) > ANGLE_TOL_DEG:
                report(f"{side} follower {m} angle {om['deg']} -> {nm['deg']} deg "
                       "(zero rewritten, or not the same pose)")
        ol, nl = o["leader"], n["leader"]
        if ol["port"] != nl["port"]:
            report(f"{side} leader port {ol['port']} -> {nl['port']}")
        for m, oc in ol["servo_calibration"].items():
            nc = nl["servo_calibration"].get(m)
            if oc != nc:
                report(f"{side} leader {m} servo calibration {oc} -> {nc} (recalibrated?)")
        for m in NAMES:
            a, b = ol["follower_targets_deg"][m], nl["follower_targets_deg"][m]
            if abs(a - b) > ANGLE_TOL_DEG:
                report(f"{side} leader {m} reads {a} -> {b} deg (moved, recalibrated or mapping changed)")
    for f in FILES:
        if old["files"].get(f) != new["files"].get(f):
            report(f"{f} differs")
    for ch in ("can0", "can1"):
        def bitrates(text):
            return [line.strip() for line in (text or "").splitlines() if "bitrate" in line]
        if bitrates(old["can_links"].get(ch)) != bitrates(new["can_links"].get(ch)):
            report(f"{ch} bitrate settings differ (run ./scripts/setup_can.sh?)")
    print(f"\n{issues} difference(s)." if issues else "  No difference.")
    return 1 if issues else 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--left", type=parse_pair, help="LEADER_PORT:CAN_CHANNEL of the left arm")
    p.add_argument("--right", type=parse_pair, help="LEADER_PORT:CAN_CHANNEL of the right arm")
    p.add_argument("--compare", type=Path, help="compare with this snapshot instead of saving one")
    p.add_argument("--note", default="", help="free text stored in the snapshot (e.g. 'before handing over')")
    args = p.parse_args()
    arms = [Arm(side, *pair) for side, pair in (("left", args.left), ("right", args.right)) if pair]
    if not arms:
        p.error("give at least one of --left / --right")
    old = json.loads(args.compare.read_text()) if args.compare else None

    try:
        for arm in arms:
            arm.connect()
        snap = take(arms)
    finally:
        for arm in arms:
            arm.disconnect()  # nothing was enabled; this only closes the buses
    snap["note"] = args.note

    if old is not None:
        sys.exit(compare(old, snap))
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / f"{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(snap, indent=2) + "\n")
    missing = [f"{s} {m}" for s, a in snap["arms"].items() for m, v in a["follower"]["motors"].items()
               if v["deg"] is None or v["params"]["SN"] is None]
    print(f"Saved {path.relative_to(ROOT)}" + (f"\nWarning: no answer / no params from {missing}" if missing else ""))


if __name__ == "__main__":
    main()
