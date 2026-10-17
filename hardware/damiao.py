"""Minimal Damiao motor driver for OpenArm over a PEAK PCAN-USB Pro FD on macOS.

Protocol ported from enactic/openarm_can (src/openarm/damiao_motor/dm_motor_control.cpp).
All positions are in radians, velocities in rad/s, torques in Nm.
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path

DRIVER_DIR = Path(__file__).resolve().parent.parent / "drivers" / "pcbusb"
# python-can looks up libPCBUSB.dylib through ctypes.util.find_library, which honours this.
os.environ["DYLD_LIBRARY_PATH"] = f"{DRIVER_DIR}:{os.environ.get('DYLD_LIBRARY_PATH', '')}"

import can  # noqa: E402

# (pMax rad, vMax rad/s, tMax Nm) used to scale the MIT and feedback fields.
LIMITS = {
    "DM8009": (12.5, 45.0, 54.0),
    "DM4340": (12.5, 10.0, 28.0),
    "DM4310": (12.5, 30.0, 10.0),
}

# OpenArm v10 arm: joints 1-7 then gripper. Send id N, feedback id N + 0x10.
ARM_MOTORS = [
    ("joint_1", 0x01, "DM8009"),
    ("joint_2", 0x02, "DM8009"),
    ("joint_3", 0x03, "DM4340"),
    ("joint_4", 0x04, "DM4340"),
    ("joint_5", 0x05, "DM4310"),
    ("joint_6", 0x06, "DM4310"),
    ("joint_7", 0x07, "DM4310"),
    ("gripper", 0x08, "DM4310"),
]

ERRORS = {
    0x0: "DISABLED", 0x1: "ENABLED", 0x8: "OVERVOLTAGE", 0x9: "UNDERVOLTAGE",
    0xA: "OVERCURRENT", 0xB: "MOS_OVERHEAT", 0xC: "COIL_OVERHEAT",
    0xD: "COMMUNICATION_LOST", 0xE: "OVERLOAD",
}

# 1 Mbps nominal / 5 Mbps data, sample point 0.75, on the PCAN 80 MHz clock.
FD_TIMING = can.BitTimingFd(
    f_clock=80_000_000,
    nom_brp=1, nom_tseg1=59, nom_tseg2=20, nom_sjw=20,
    data_brp=1, data_tseg1=11, data_tseg2=4, data_sjw=4,
)


@dataclass
class MotorState:
    q: float
    dq: float
    tau: float
    t_mos: int
    t_rotor: int
    status: int

    @property
    def status_name(self) -> str:
        return ERRORS.get(self.status, f"UNKNOWN(0x{self.status:X})")


def open_bus(channel: str) -> can.BusABC:
    return can.Bus(interface="pcan", channel=channel, timing=FD_TIMING)


def _to_uint(x: float, lo: float, hi: float, bits: int) -> int:
    x = min(max(x, lo), hi)
    return int((x - lo) / (hi - lo) * ((1 << bits) - 1))


def _to_float(u: int, lo: float, hi: float, bits: int) -> float:
    return u / ((1 << bits) - 1) * (hi - lo) + lo


def _send(bus: can.BusABC, arb_id: int, data: list[int]) -> None:
    bus.send(can.Message(arbitration_id=arb_id, data=bytes(data), is_extended_id=False,
                         is_fd=True, bitrate_switch=True))


def send_enable(bus, send_id):
    _send(bus, send_id, [0xFF] * 7 + [0xFC])


def send_disable(bus, send_id):
    _send(bus, send_id, [0xFF] * 7 + [0xFD])


def send_set_zero(bus, send_id):
    """Store the current shaft position as the motor's zero. Motor must be disabled."""
    _send(bus, send_id, [0xFF] * 7 + [0xFE])


def send_refresh(bus, send_id):
    """Ask for a state frame without changing anything on the motor."""
    _send(bus, 0x7FF, [send_id & 0xFF, (send_id >> 8) & 0xFF, 0xCC, 0, 0, 0, 0, 0])


def send_mit(bus, send_id, motor_type, q, dq=0.0, kp=0.0, kd=0.0, tau=0.0):
    p_max, v_max, t_max = LIMITS[motor_type]
    q_u = _to_uint(q, -p_max, p_max, 16)
    dq_u = _to_uint(dq, -v_max, v_max, 12)
    kp_u = _to_uint(kp, 0, 500, 12)
    kd_u = _to_uint(kd, 0, 5, 12)
    tau_u = _to_uint(tau, -t_max, t_max, 12)
    _send(bus, send_id, [
        q_u >> 8, q_u & 0xFF,
        dq_u >> 4, ((dq_u & 0xF) << 4) | (kp_u >> 8),
        kp_u & 0xFF,
        kd_u >> 4, ((kd_u & 0xF) << 4) | (tau_u >> 8),
        tau_u & 0xFF,
    ])


def parse_state(motor_type: str, data: bytes) -> MotorState:
    p_max, v_max, t_max = LIMITS[motor_type]
    q_u = (data[1] << 8) | data[2]
    dq_u = (data[3] << 4) | (data[4] >> 4)
    tau_u = ((data[4] & 0xF) << 8) | data[5]
    return MotorState(
        q=_to_float(q_u, -p_max, p_max, 16),
        dq=_to_float(dq_u, -v_max, v_max, 12),
        tau=_to_float(tau_u, -t_max, t_max, 12),
        t_mos=data[6],
        t_rotor=data[7],
        status=data[0] >> 4,
    )


def collect_states(bus, motors, timeout=0.05) -> dict[str, MotorState]:
    """Read feedback frames until every motor answered or the timeout expires."""
    by_recv_id = {send_id + 0x10: (name, mtype) for name, send_id, mtype in motors}
    states: dict[str, MotorState] = {}
    deadline = time.monotonic() + timeout
    while len(states) < len(motors) and (remaining := deadline - time.monotonic()) > 0:
        msg = bus.recv(timeout=remaining)
        if msg is None:
            break
        if msg.arbitration_id in by_recv_id and len(msg.data) >= 8:
            name, mtype = by_recv_id[msg.arbitration_id]
            states[name] = parse_state(mtype, msg.data)
    return states


def read_states(bus, motors=ARM_MOTORS, timeout=0.05) -> dict[str, MotorState]:
    for _, send_id, _ in motors:
        send_refresh(bus, send_id)
    return collect_states(bus, motors, timeout)
