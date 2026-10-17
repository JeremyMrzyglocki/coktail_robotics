"""Tests rapides, sans robot : python -m pytest tests  (ou python tests/test_basics.py)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bar_state import BarState, PourRequestError, load_bar_config  # noqa: E402
from glass_level import GlassModel  # noqa: E402
from robot_io import MOTOR_LIMITS, MOTOR_TYPES, decode_state  # noqa: E402


def _encode_state(idx, q, dq, tau, err=1, tmos=40, trot=35):
    """Encodeur inverse (format des trames d'état Damiao) pour tester le décodeur."""
    pmax, vmax, tmax = MOTOR_LIMITS[MOTOR_TYPES[idx]]

    def f2u(x, lim, bits):
        return int((x + lim) / (2 * lim) * ((1 << bits) - 1))

    qu, dqu, tu = f2u(q, pmax, 16), f2u(dq, vmax, 12), f2u(tau, tmax, 12)
    return bytes([(idx + 1) | (err << 4), qu >> 8, qu & 0xFF, dqu >> 4,
                  ((dqu & 0xF) << 4) | (tu >> 8), tu & 0xFF, tmos, trot])


def test_decode_state_all_motor_types():
    for idx in range(8):
        tmax = MOTOR_LIMITS[MOTOR_TYPES[idx]][2]
        q, dq, tau = decode_state(idx, _encode_state(idx, 0.7, -1.2, 0.3 * tmax))
        lsb = 2 * tmax / 4095
        assert abs(q - 0.7) < 1e-3 and abs(dq + 1.2) < 0.05 and abs(tau - 0.3 * tmax) <= lsb


def test_sniffer_frame_parsing():
    """Chemin de décodage du backend sniff, sans socket (le socket CAN exige Linux)."""
    import struct
    import threading

    from robot_io import JOINT_OFFSETS, CanSnifferBackend

    sn = CanSnifferBackend.__new__(CanSnifferBackend)  # sans ouvrir de socket
    sn.apply_offsets, sn.lock = True, threading.Lock()
    sn.state = {"right_arm": [np.full(8, np.nan) for _ in range(4)] + [0.0]}
    sn.frames = {"right_arm": 0}
    hdr = lambda cid: struct.pack("=IBBBB", cid, 8, 0, 0, 0)  # noqa: E731
    assert sn.handle_frame("right_arm", hdr(0x12) + _encode_state(1, 0.5, 0.0, 10.0))            # classique
    assert sn.handle_frame("right_arm", hdr(0x15) + _encode_state(4, -0.2, 0.0, 1.0) + bytes(56))  # CAN-FD
    assert not sn.handle_frame("right_arm", hdr(0x7FF) + bytes([1, 0, 0xCC, 0, 0, 0, 0, 0]))     # refresh
    assert not sn.handle_frame("right_arm", hdr(0x20000012) + bytes(8))                         # trame d'erreur
    q, tau = sn.state["right_arm"][0], sn.state["right_arm"][2]
    assert abs(q[1] + JOINT_OFFSETS["right_arm"][1] - 0.5) < 1e-3 and abs(tau[1] - 10.0) < 0.03
    assert abs(q[4] - (-0.2)) < 1e-3 and abs(tau[4] - 1.0) < 0.005 and sn.frames["right_arm"] == 2


def _raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except PourRequestError:
        return True
    return False


def test_bar_state_checks():
    st = BarState.fresh(load_bar_config())
    assert st.check_pour("red", 60).grams == 60
    assert st.check_pour("red", "all").grams == 120
    st.record_pour("red", 90, persist=False)
    assert _raises(st.check_pour, "red", 60)                    # 60 > 30 restants
    assert st.check_pour("red", 60, strict=False).grams == 30    # on verse ce qui reste
    st.record_pour("yellow", 120, persist=False)                 # verre : 210 / 300
    assert _raises(st.check_pour, "blue", 120)                   # débordement
    assert st.check_pour("blue", 70).warnings                    # presque plein (280 / 300)
    st.record_pour("red", 30, persist=False)
    assert _raises(st.check_pour, "red", "all")                  # bouteille vide
    assert [layer["color"] for layer in st.glass_layers] == ["red", "yellow", "red"]
    assert _raises(st.check_plan, [("blue", 60), ("yellow", 30)])  # yellow vide


def test_glass_model():
    m = GlassModel([(0.5, 120), (1.0, 300)])                     # verre évasé
    assert abs(m.grams(0.25) - 60) < 1e-6 and abs(m.height(210) - 0.75) < 1e-6
    assert GlassModel(None, 300).grams(0.5) == 150


def test_glass_cumulative_synthetic():
    from glass_level import selftest
    assert selftest() == 0


if __name__ == "__main__":
    test_decode_state_all_motor_types()
    test_sniffer_frame_parsing()
    test_bar_state_checks()
    test_glass_model()
    test_glass_cumulative_synthetic()
    print("OK")
