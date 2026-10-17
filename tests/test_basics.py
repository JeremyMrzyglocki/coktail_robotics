"""Tests rapides, sans robot : python -m pytest tests  (ou python tests/test_basics.py)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glass_level import GlassCalib, content_mask, level_from_mask, synthetic_glass  # noqa: E402
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


def test_glass_level_synthetic():
    calib = GlassCalib(roi=[260, 120, 120, 260], hsv_lo=[5, 120, 120], hsv_hi=[30, 255, 255])
    for lv in (0.0, 0.3, 0.8):
        est = level_from_mask(content_mask(synthetic_glass(lv), calib), calib.row_frac)
        assert abs(est - lv) < 0.03, (lv, est)


if __name__ == "__main__":
    test_decode_state_all_motor_types()
    test_glass_level_synthetic()
    print("OK")
