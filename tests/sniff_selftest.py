"""Test du backend "sniff" SANS robot, sur un bus CAN virtuel (vcan), Linux uniquement.

  sudo modprobe vcan
  sudo ip link add dev vcan0 type vcan && sudo ip link set up vcan0     # une fois
  python tests/sniff_selftest.py --iface vcan0

Le script émet de fausses trames d'état Damiao (CAN classique ET CAN-FD) sur vcan0, comme
le feraient les moteurs, et vérifie que CanSnifferBackend les décode. vcan0 est un bus
purement logiciel : rien ne sort vers can0/can1 ni vers le robot. Ne JAMAIS lancer avec
--iface can0 (on émettrait sur le vrai bus) : le script refuse.
"""

import argparse
import socket
import struct
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from robot_io import JOINT_OFFSETS, MOTOR_LIMITS, MOTOR_TYPES, CanSnifferBackend  # noqa: E402
from test_basics import _encode_state  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--iface", default="vcan0")
    a = p.parse_args()
    if not a.iface.startswith("vcan"):
        sys.exit("refusé : ce test émet des trames, uniquement sur une interface vcan*")

    sniff = CanSnifferBackend(arms=("right_arm",), can_interfaces={"right_arm": a.iface})
    tx = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    tx.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FD_FRAMES, 1)
    tx.bind((a.iface,))

    rng = np.random.default_rng(0)
    want_q = rng.uniform(-1, 1, 8)
    want_tau = np.array([rng.uniform(-0.5, 0.5) * MOTOR_LIMITS[t][2] for t in MOTOR_TYPES])
    for idx in range(8):
        data = _encode_state(idx, want_q[idx], 0.1, want_tau[idx])
        can_id = 0x11 + idx
        if idx % 2:   # trame CAN-FD (72 octets : id, len, flags, res0, res1, data[64])
            frame = struct.pack("=IBBBB", can_id, 8, 0, 0, 0) + data + bytes(56)
        else:         # trame classique (16 octets)
            frame = struct.pack("=IBBBB", can_id, 8, 0, 0, 0) + data
        tx.send(frame)
    tx.send(struct.pack("=IBBBB", 0x7FF, 8, 0, 0, 0) + bytes([1, 0, 0xCC, 0, 0, 0, 0, 0]))  # refresh : ignoré
    time.sleep(0.5)

    st = sniff.read("right_arm")
    sniff.close()
    q_raw = st.q + JOINT_OFFSETS["right_arm"]
    lsb = np.array([2 * MOTOR_LIMITS[t][2] / 4095 for t in MOTOR_TYPES])
    ok_q = np.all(np.abs(q_raw - want_q) < 1e-3)
    ok_tau = np.all(np.abs(st.tau - want_tau) <= lsb)
    print(f"trames reçues : {sniff.frames['right_arm']} (attendu 8)")
    print("q   ", np.round(q_raw, 3), "OK" if ok_q else "ÉCHEC")
    print("tau ", np.round(st.tau, 3), "OK" if ok_tau else "ÉCHEC")
    ok = ok_q and ok_tau and sniff.frames["right_arm"] == 8
    print("SNIFF OK" if ok else "SNIFF ÉCHEC")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
