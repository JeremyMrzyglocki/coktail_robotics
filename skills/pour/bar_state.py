"""État du bar : bouteilles (grammes restants), verre (remplissage), contrôles de sécurité.

Un seul objet `BarState`, tenu par l'orchestrateur, passé à `pour()` qui le met à jour
après chaque versement. `summary()` est fait pour être injecté tel quel dans le prompt
du LLM ; `check_plan()` valide un cocktail entier AVANT de bouger le robot.

L'état est sauvegardé dans state/bar_state.json (survit à un redémarrage de script).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "containers.yaml"
STATE_PATH = HERE / "state/bar_state.json"
ALL = "all"


@dataclass
class Container:
    name: str
    drink: str = ""
    hsv: list = field(default_factory=list)       # liste de [[h,s,v] lo, [h,s,v] hi]
    capacity_g: float = 120.0
    initial_g: float = 120.0
    empty_mass_g: float = 40.0
    neck_length_m: float = 0.03
    neck_offset_m: list = field(default_factory=lambda: [0.0, 0.0, 0.12])
    tilt_speed_dps: float = 4.0
    max_tilt_deg: float = 120.0
    pre_tilt_deg: float = 35.0
    flow_rate_gps: float = 12.0
    slow_rate_gps: float = 5.0
    approach_pose: list | None = None


@dataclass
class BarConfig:
    containers: dict[str, Container]
    glass_capacity_g: float
    glass_calib: str
    glass_mouth_radius_m: float
    mm_unit_g: float
    cocktails: dict[str, dict[str, float]]


def load_bar_config(path: Path | str = CONFIG_PATH) -> BarConfig:
    raw = yaml.safe_load(Path(path).read_text())
    defaults = raw.get("defaults", {})
    containers = {name: Container(name=name, **{**defaults, **(spec or {})})
                  for name, spec in raw["containers"].items()}
    g = raw["glass"]
    return BarConfig(containers, float(g["capacity_g"]), g.get("calib", ""),
                     float(g.get("mouth_radius_m", 0.04)), float(raw.get("mm_unit_g", 0.9)),
                     raw.get("cocktails", {}))


class PourRequestError(ValueError):
    """Demande refusée avant tout mouvement (bouteille insuffisante, verre plein...)."""


@dataclass
class PourCheck:
    grams: float              # quantité effectivement visée (résout "all")
    warnings: list[str]


@dataclass
class BarState:
    remaining_g: dict[str, float]
    glass_g: float = 0.0
    glass_capacity_g: float = 300.0
    glass_layers: list[dict] = field(default_factory=list)   # [{"color", "grams"}] du fond vers le haut
    onset_deg: dict[str, float] = field(default_factory=dict)  # dernier angle de début d'écoulement par bouteille
    history: list[dict] = field(default_factory=list)
    margin_g: float = 10.0     # tolérance des contrôles (≈ précision visée)

    # ---- création / persistance ----
    @classmethod
    def fresh(cls, cfg: BarConfig) -> "BarState":
        return cls({n: c.initial_g for n, c in cfg.containers.items()}, glass_capacity_g=cfg.glass_capacity_g)

    @classmethod
    def load_or_fresh(cls, cfg: BarConfig, path: Path = STATE_PATH) -> "BarState":
        if path.exists():
            st = cls(**json.loads(path.read_text()))
            for n, c in cfg.containers.items():  # bouteille ajoutée au yaml depuis
                st.remaining_g.setdefault(n, c.initial_g)
            return st
        return cls.fresh(cfg)

    def save(self, path: Path = STATE_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))

    # ---- contrôles ----
    @property
    def glass_free_g(self) -> float:
        return self.glass_capacity_g - self.glass_g

    def check_pour(self, container: str, target: float | str, strict: bool = True) -> PourCheck:
        """Valide une demande. Lève PourRequestError si refusée ; renvoie les avertissements sinon.

        strict=False : si la bouteille n'a pas assez, on verse ce qui reste (avec avertissement).
        """
        if container not in self.remaining_g:
            raise PourRequestError(f"bouteille inconnue : {container}")
        rem = self.remaining_g[container]
        warnings = []
        if target == ALL:
            if rem < 5:
                raise PourRequestError(f"bouteille {container} déjà vide (≈{rem:.0f} g estimés)")
            grams = rem
        else:
            grams = float(target)
            if grams <= 0:
                raise PourRequestError("quantité demandée <= 0")
            if grams > rem + self.margin_g:
                msg = f"{container} : {grams:.0f} g demandés mais ≈{rem:.0f} g restants"
                if strict:
                    raise PourRequestError(msg)
                warnings.append(msg + " : on verse ce qui reste")
                grams = rem
            elif grams > rem:
                warnings.append(f"{container} : on va probablement finir la bouteille (≈{rem:.0f} g restants)")
        if grams > self.glass_free_g + self.margin_g:
            raise PourRequestError(f"le verre déborderait : {grams:.0f} g pour ≈{self.glass_free_g:.0f} g de place")
        if self.glass_g + grams > 0.9 * self.glass_capacity_g:
            warnings.append(f"verre presque plein après versement (≈{self.glass_g + grams:.0f}/{self.glass_capacity_g:.0f} g)")
        return PourCheck(grams, warnings)

    def check_plan(self, steps: list[tuple[str, float | str]]) -> list[str]:
        """Valide une suite de versements sur une copie de l'état. Lève si un pas est refusé."""
        sim = BarState(dict(self.remaining_g), self.glass_g, self.glass_capacity_g)
        warnings = []
        for container, target in steps:
            chk = sim.check_pour(container, target)
            warnings += chk.warnings
            sim.record_pour(container, chk.grams, persist=False)
        return warnings

    # ---- mise à jour ----
    def record_pour(self, container: str, poured_g: float, source: str = "estimate",
                    target: float | str | None = None, persist: bool = True, **extra):
        poured_g = max(0.0, float(poured_g))
        self.remaining_g[container] = max(0.0, self.remaining_g[container] - poured_g)
        self.glass_g += poured_g
        if self.glass_layers and self.glass_layers[-1]["color"] == container:
            self.glass_layers[-1]["grams"] += poured_g
        else:
            self.glass_layers.append({"color": container, "grams": poured_g})
        self.history.append({"t": time.time(), "container": container, "target": target,
                             "poured_g": round(poured_g, 1), "source": source, **extra})
        if persist:
            self.save()

    def new_glass(self):
        self.glass_g, self.glass_layers = 0.0, []
        self.save()

    def refill(self, container: str, grams: float):
        self.remaining_g[container] = float(grams)
        self.onset_deg.pop(container, None)  # le remplissage change l'angle de départ
        self.save()

    # ---- pour le LLM / l'UI ----
    def summary(self, cfg: BarConfig | None = None) -> dict:
        bottles = {}
        for n, g in self.remaining_g.items():
            b = {"remaining_g": round(g), "empty": g < 5}
            if cfg and n in cfg.containers:
                b["drink"] = cfg.containers[n].drink
                b["capacity_g"] = cfg.containers[n].capacity_g
            bottles[n] = b
        return {"bottles": bottles,
                "glass": {"filled_g": round(self.glass_g), "capacity_g": self.glass_capacity_g,
                          "free_g": round(self.glass_free_g), "layers": self.glass_layers},
                "rules": {"pour_amounts_g": [30, 60, 90, "all"], "tolerance_g": self.margin_g}}
