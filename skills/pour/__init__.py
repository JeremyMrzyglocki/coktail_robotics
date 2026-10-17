"""Skill « pour » importable depuis la racine du repo : `from skills.pour import pour, Robot, BarState`.

Les modules de la skill s'importent entre eux par leur nom (`from robot_io import ...`) pour
rester lançables comme scripts depuis ce dossier ; on ajoute donc ce dossier au sys.path.
"""

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from bar_state import ALL, BarState, PourRequestError, load_bar_config  # noqa: E402
from pour_skill import PourConfig, PourResult, pour  # noqa: E402
from robot_io import Robot  # noqa: E402

__all__ = ["ALL", "BarState", "PourConfig", "PourRequestError", "PourResult", "Robot", "load_bar_config", "pour"]
