"""Grammes versés dans le grand verre, mesurés par vision (OpenCV), zone d'intérêt fixe.

Méthode par défaut : DIFF CUMULATIF.
  1. Juste avant chaque versement : photo de référence du verre DANS SON ÉTAT ACTUEL
     (`begin_pour`). Les couches déjà présentes font partie de la référence.
  2. Pendant le versement : tout ce qui diffère de la référence AU-DESSUS de la surface
     précédente (h0) est la nouvelle couche. Le sommet de cette couche donne h1.
  3. Grammes ajoutés = G(h1) - G(h0), avec G la calibration hauteur -> grammes du verre.
  Bonus : chaque bouteille a une couleur unique, donc on vérifie que la nouvelle couche
  a bien la couleur attendue (mauvaise bouteille => avertissement).

Hauteurs en fraction de la zone (0 = fond, 1 = haut de la zone). Placer le bas de la zone
au fond du verre et le haut au niveau "plein" (≈300 g).

  python glass_level.py --calibrate         # zone, seuils ; touche b = référence verre VIDE
  python glass_level.py --set-empty         # référence verre vide, sans fenêtre
  python glass_level.py --add-point 60      # calibration : verre contenant 60 g (pesés à la balance)
  python glass_level.py --live              # grammes ajoutés en direct (r = nouvelle référence)
  python glass_level.py --selftest          # test synthétique sans caméra

macOS : autoriser l'accès caméra pour le Terminal (Réglages > Confidentialité).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

DEFAULT_CALIB = Path("config/glass_calib.json")         # zone + seuils
DEFAULT_GRAMS = Path("config/glass_grams_calib.json")   # hauteur -> grammes


@dataclass
class GlassCalib:
    roi: list[int] = field(default_factory=lambda: [0, 0, 0, 0])  # x, y, w, h
    diff_thresh: int = 35
    row_frac: float = 0.35      # une ligne est "remplie" si >= 35 % de ses pixels ont changé
    empty_ref_path: str = "config/glass_empty.png"

    @classmethod
    def load(cls, path=DEFAULT_CALIB) -> "GlassCalib":
        d = json.loads(Path(path).read_text())
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def save(self, path=DEFAULT_CALIB):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(asdict(self), indent=2))


class GlassModel:
    """Calibration hauteur -> grammes (interpolation linéaire par morceaux, monotone).

    Sans points mesurés : verre cylindrique, h=1 <=> capacity_g (approximation, à remplacer).
    """

    def __init__(self, points: list[tuple[float, float]] | None = None, capacity_g: float = 300.0):
        pts = sorted({(0.0, 0.0), *[(float(h), float(g)) for h, g in (points or [])]})
        if len(pts) < 2:
            pts = [(0.0, 0.0), (1.0, capacity_g)]
        self.h = np.maximum.accumulate(np.array([p[0] for p in pts]))
        self.g = np.maximum.accumulate(np.array([p[1] for p in pts]))
        self.calibrated = bool(points)

    @classmethod
    def load(cls, path=DEFAULT_GRAMS, capacity_g=300.0) -> "GlassModel":
        p = Path(path)
        if p.exists():
            return cls(json.loads(p.read_text())["points"], capacity_g)
        return cls(None, capacity_g)

    def _extrap(self, x, xs, ys):
        if x <= xs[-1]:
            return float(np.interp(x, xs, ys))
        slope = (ys[-1] - ys[-2]) / max(xs[-1] - xs[-2], 1e-9)
        return float(ys[-1] + slope * (x - xs[-1]))

    def grams(self, h: float) -> float:
        return self._extrap(h, self.h, self.g)

    def height(self, g: float) -> float:
        return self._extrap(g, self.g, self.h)


def diff_mask(frame: np.ndarray, ref: np.ndarray, calib: GlassCalib) -> np.ndarray:
    x, y, w, h = calib.roi
    a = cv2.GaussianBlur(frame[y:y + h, x:x + w], (5, 5), 0)
    b = cv2.GaussianBlur(ref[y:y + h, x:x + w], (5, 5), 0)
    mask = (cv2.absdiff(a, b).max(axis=2) > calib.diff_thresh).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def _filled_rows(mask: np.ndarray, row_frac: float) -> np.ndarray:
    """Indicateur lissé "ligne remplie", indexé du BAS vers le HAUT."""
    rows = (mask > 0).mean(axis=1)
    return np.convolve(rows >= row_frac, np.ones(5) / 5, mode="same")[::-1]


def level_from_mask(mask: np.ndarray, row_frac: float) -> float:
    """Hauteur remplie depuis le fond (pour une différence avec le verre VIDE)."""
    return added_top(mask, 0.0, row_frac)


def added_top(mask: np.ndarray, h0: float, row_frac: float, settle_margin: float = 0.03) -> float:
    """Sommet de la nouvelle couche (fraction), au-dessus de la surface précédente h0.

    On exige la continuité depuis h0 : le filet de M&M's en chute ou le goulot qui entre
    par le haut de la zone ne forment pas une couche continue et sont ignorés.
    """
    if mask.size == 0:
        return h0
    filled = _filled_rows(mask, row_frac)
    n = len(filled)
    i0 = max(0, int((h0 - settle_margin) * n))   # les grains du dessus peuvent bouger un peu
    seg = filled[i0:]
    if not len(seg):
        return h0
    cum = np.cumsum(seg) / np.arange(1, len(seg) + 1)
    ok = np.nonzero((cum >= 0.6) & (seg >= 0.5))[0]
    return max(h0, float((i0 + ok[-1] + 1) / n)) if len(ok) else h0


def hsv_match(bgr: np.ndarray, ranges: list) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in ranges:
        m |= cv2.inRange(hsv, np.array(lo), np.array(hi))
    return m


class GlassScale:
    """Capteur "balance optique" du verre. API utilisée par pour() :

      begin_pour(h0=None, expected=None, palette=None)   référence + surface de départ
      read_added_g() -> float | None                      grammes ajoutés (lissé, monotone)
      end_pour() -> dict                                  bilan + contrôle de couleur
    """

    def __init__(self, calib: GlassCalib | None = None, model: GlassModel | None = None,
                 camera: int | str | None = 0, median_n: int = 5):
        self.calib = calib or GlassCalib.load()
        self.model = model or GlassModel.load()
        self.cap = None
        if camera is not None:
            api = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" and isinstance(camera, int) else cv2.CAP_ANY
            self.cap = cv2.VideoCapture(camera, api)
            if not self.cap.isOpened():
                raise RuntimeError(f"caméra {camera} indisponible (permission caméra ?)")
        p = Path(self.calib.empty_ref_path)
        self.empty_ref = cv2.imread(str(p)) if p.exists() else None
        self.ref = None
        self.h0 = self.h1 = 0.0
        self.hist: deque[float] = deque(maxlen=median_n)
        self.expected, self.palette = None, {}
        self.last_frame = self.last_mask = None

    # -- images --
    def grab(self) -> np.ndarray | None:
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if ok:
            self.last_frame = frame
        return frame if ok else None

    def grab_median(self, n=5) -> np.ndarray:
        frames = [f for f in (self.grab() for _ in range(n)) if f is not None]
        if not frames:
            raise RuntimeError("aucune image de la caméra")
        return np.median(np.stack(frames), axis=0).astype(np.uint8)

    def absolute_level(self, frame=None) -> float | None:
        """Hauteur totale vs la référence VERRE VIDE (calibration, contrôle)."""
        if self.empty_ref is None:
            return None
        frame = self.grab_median() if frame is None else frame
        return level_from_mask(diff_mask(frame, self.empty_ref, self.calib), self.calib.row_frac)

    # -- API versement --
    def begin_pour(self, h0: float | None = None, expected: str | None = None, palette: dict | None = None):
        """h0 : surface actuelle (fraction). None => mesurée vs verre vide, sinon dernière connue."""
        self.ref = self.grab_median()
        if h0 is None:
            h0 = self.absolute_level(self.ref)
            h0 = self.h1 if h0 is None else h0
        self.h0 = self.h1 = float(h0)
        self.hist.clear()
        self.expected, self.palette = expected, palette or {}

    def measure(self, frame) -> float:
        self.last_mask = diff_mask(frame, self.ref, self.calib)
        return added_top(self.last_mask, self.h0, self.calib.row_frac)

    def read_added_g(self) -> float | None:
        frame = self.grab()
        if frame is None or self.ref is None:
            return None
        self.hist.append(self.measure(frame))
        self.h1 = max(self.h1, float(np.median(self.hist)))  # les M&M's ne repartent pas
        return self.model.grams(self.h1) - self.model.grams(self.h0)

    def color_check(self, frame=None) -> dict:
        """Couleur de la nouvelle couche (bande h0..h1) comparée à la palette des bouteilles."""
        frame = self.last_frame if frame is None else frame
        if frame is None or not self.palette or self.h1 - self.h0 < 0.01:
            return {}
        x, y, w, h = self.calib.roi
        top, bot = int(h * (1 - self.h1)), int(h * (1 - self.h0))
        band = frame[y + top:y + bot, x:x + w]
        changed = diff_mask(frame, self.ref, self.calib)[top:bot] > 0
        if band.size == 0 or changed.sum() < 20:
            return {}
        scores = {c: float((hsv_match(band, r) > 0)[changed].mean()) for c, r in self.palette.items()}
        best = max(scores, key=scores.get)
        return {"scores": scores, "best": best,
                "ok": None if self.expected is None else best == self.expected and scores[best] > 0.3}

    def end_pour(self) -> dict:
        frame = self.grab_median()
        self.hist.clear()
        self.hist.append(self.measure(frame))
        self.h1 = max(self.h1, self.hist[0])
        return {"added_g": self.model.grams(self.h1) - self.model.grams(self.h0),
                "h0": self.h0, "h1": self.h1, "color": self.color_check(frame),
                "calibrated": self.model.calibrated}

    def close(self):
        if self.cap is not None:
            self.cap.release()


class MockGlassSensor:
    """Même API que GlassScale, branchée sur le backend mock (bruit + trous de mesure)."""

    def __init__(self, robot, noise_g=1.5, dropout=0.03, seed=0):
        self.robot, self.noise_g, self.dropout = robot, noise_g, dropout
        self.rng = np.random.default_rng(seed)
        self.g0, self.best, self.expected = 0.0, 0.0, None
        self.hist: deque[float] = deque(maxlen=5)

    def begin_pour(self, h0=None, expected=None, palette=None):
        self.g0, self.best, self.expected = self.robot.backend.glass_grams(), 0.0, expected
        self.hist = deque(maxlen=5)

    def read_added_g(self):
        if self.rng.random() < self.dropout:
            return None
        self.hist.append(self.robot.backend.glass_grams() - self.g0 + self.rng.normal(0, self.noise_g))
        self.best = max(self.best, float(np.median(self.hist)))  # même filtrage que GlassScale
        return self.best

    def end_pour(self):
        layers = self.robot.backend.glass_layers_g()
        top = layers[-1][0] if layers else None
        added = self.robot.backend.glass_grams() - self.g0 + self.rng.normal(0, self.noise_g)
        return {"added_g": added, "color": {"best": top, "ok": None if self.expected is None else top == self.expected},
                "calibrated": True}

    def close(self):
        pass


# --------------------------------------------------------------------------- UI / CLI

def draw_overlay(frame, calib: GlassCalib, h0=None, h1=None, mask=None, text=""):
    x, y, w, h = calib.roi
    out = frame.copy()
    if w and h:
        if mask is not None:
            tint = np.zeros_like(out[y:y + h, x:x + w])
            tint[mask > 0] = (0, 200, 255)
            out[y:y + h, x:x + w] = cv2.addWeighted(out[y:y + h, x:x + w], 1.0, tint, 0.5, 0)
        cv2.rectangle(out, (x, y), (x + w, y + h), (255, 255, 255), 2)
        for lv, col in ((h0, (255, 160, 0)), (h1, (0, 255, 0))):
            if lv is not None:
                ly = int(y + h * (1 - min(lv, 1.0)))
                cv2.line(out, (x - 10, ly), (x + w + 10, ly), col, 2)
    for c, th in (((0, 0, 0), 4), ((255, 255, 255), 2)):
        cv2.putText(out, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, c, th)
    return out


def open_camera(camera):
    cap = cv2.VideoCapture(camera, cv2.CAP_AVFOUNDATION if sys.platform == "darwin" and isinstance(camera, int)
                           else cv2.CAP_ANY)
    if not cap.isOpened():
        sys.exit("Caméra indisponible. macOS : autoriser le Terminal (Confidentialité > Caméra). "
                 "VM : ls /dev/video* ; caméra redirigée/partagée ?")
    return cap


def calibrate(camera, path: Path):
    calib = GlassCalib.load(path) if path.exists() else GlassCalib()
    cap = open_camera(camera)
    ok, frame = cap.read()
    if not calib.roi[2]:
        hh, ww = frame.shape[:2]
        calib.roi = [ww // 3, hh // 4, ww // 3, hh // 2]
    empty = cv2.imread(calib.empty_ref_path) if Path(calib.empty_ref_path).exists() else None
    win = "calib"
    cv2.namedWindow(win)
    cv2.createTrackbar("diff", win, calib.diff_thresh, 255, lambda _: None)
    cv2.createTrackbar("ligne %", win, int(calib.row_frac * 100), 100, lambda _: None)
    print("r = zone (glisser + Entrée) | b = référence verre VIDE | s = sauver | q = quitter")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        calib.diff_thresh = cv2.getTrackbarPos("diff", win)
        calib.row_frac = max(cv2.getTrackbarPos("ligne %", win), 1) / 100
        mask = lv = None
        if empty is not None and empty.shape == frame.shape:
            mask = diff_mask(frame, empty, calib)
            lv = level_from_mask(mask, calib.row_frac)
        txt = "niveau vs vide: " + ("--- (touche b)" if lv is None else f"{lv * 100:.1f} %")
        cv2.imshow(win, draw_overlay(frame, calib, None, lv, mask, txt))
        k = cv2.waitKey(1) & 0xFF
        if k == ord("r"):
            r = cv2.selectROI("zone", frame, showCrosshair=False)
            cv2.destroyWindow("zone")
            if r[2] and r[3]:
                calib.roi = [int(v) for v in r]
        elif k == ord("b"):
            Path(calib.empty_ref_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(calib.empty_ref_path, frame)
            empty = frame.copy()
            print(f"référence verre vide -> {calib.empty_ref_path}")
        elif k == ord("s"):
            calib.save(path)
            print(f"calibration -> {path}")
        elif k in (ord("q"), 27):
            break
    cap.release()
    cv2.destroyAllWindows()
    return 0


def set_empty(camera, path: Path):
    calib = GlassCalib.load(path)
    s = GlassScale(calib, camera=camera)
    ref = s.grab_median(10)
    Path(calib.empty_ref_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(calib.empty_ref_path, ref)
    print(f"référence verre vide -> {calib.empty_ref_path}")
    return 0


def add_point(camera, path: Path, grams: float, grams_path: Path):
    s = GlassScale(GlassCalib.load(path), camera=camera)
    lv = s.absolute_level(s.grab_median(10))
    if lv is None:
        sys.exit("Pas de référence verre vide : python glass_level.py --set-empty (verre vide !)")
    data = json.loads(grams_path.read_text()) if grams_path.exists() else {"points": []}
    data["points"].append([round(lv, 4), grams])
    grams_path.parent.mkdir(parents=True, exist_ok=True)
    grams_path.write_text(json.dumps(data, indent=2))
    print(f"point ajouté : h={lv:.3f} <-> {grams:.0f} g")
    for h, g in sorted(data["points"]):
        print(f"   h={h:.3f}  {g:6.1f} g")
    return 0


def live(camera, path: Path):
    s = GlassScale(GlassCalib.load(path), camera=camera)
    s.begin_pour()
    print("r = nouvelle référence (avant un versement) | q = quitter")
    while True:
        g = s.read_added_g()
        if s.last_frame is None:
            break
        txt = f"+{g:5.1f} g  (h0={s.h0:.2f} h1={s.h1:.2f})" + ("" if s.model.calibrated else " [non calibré]")
        cv2.imshow("verre", draw_overlay(s.last_frame, s.calib, s.h0, s.h1, s.last_mask, txt))
        k = cv2.waitKey(1) & 0xFF
        if k == ord("r"):
            s.begin_pour(h0=s.h1)
        elif k in (ord("q"), 27):
            break
    s.close()
    cv2.destroyAllWindows()
    return 0


BGR = {"red": (40, 30, 200), "yellow": (40, 210, 235), "blue": (200, 90, 20)}


def synthetic_glass(layers: list[tuple[float, str]], w=640, h=480, seed=0) -> np.ndarray:
    """Image de test : verre avec couches [(hauteur du sommet, couleur), ...] du fond vers le haut."""
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 90, np.uint8)
    x0, y0, gw, gh = 260, 120, 120, 260
    cv2.rectangle(img, (x0, y0), (x0 + gw, y0 + gh), (200, 200, 200), 2)
    prev = 0.0
    for top_h, color in layers:
        top, bot = int(y0 + gh * (1 - top_h)), int(y0 + gh * (1 - prev))
        fill = np.array(BGR[color], np.int16) + rng.integers(-20, 20, (bot - top, gw, 3))
        img[top:bot, x0:x0 + gw] = np.clip(fill, 0, 255).astype(np.uint8)
        holes = rng.random((bot - top, gw)) < 0.06   # interstices entre billes
        img[top:bot, x0:x0 + gw][holes] = 60
        prev = top_h
    return img


def selftest() -> int:
    from bar_state import load_bar_config

    palette = {n: c.hsv for n, c in load_bar_config().containers.items()}
    calib = GlassCalib(roi=[260, 120, 120, 260])
    model = GlassModel(None, 300.0)
    worst = 0.0
    cases = [([], [(0.2, "red")]),                                   # 1er versement, verre vide
             ([(0.2, "red")], [(0.2, "red"), (0.5, "yellow")]),       # 2e couleur par-dessus
             ([(0.2, "red"), (0.5, "yellow")], [(0.2, "red"), (0.5, "yellow"), (0.6, "blue")])]
    for before, after in cases:
        s = GlassScale(calib, model, camera=None)
        ref = synthetic_glass(before, seed=1)
        s.ref = ref
        s.h0 = s.h1 = before[-1][0] if before else 0.0
        s.palette, s.expected = palette, after[-1][1]
        frame = synthetic_glass(after, seed=2)          # grains différents = image réelle suivante
        frame[130:175, 300:340] = (230, 230, 230)       # goulot qui entre en haut de la zone
        s.h1 = max(s.h1, s.measure(frame))
        got = model.grams(s.h1) - model.grams(s.h0)
        want = model.grams(after[-1][0]) - model.grams(s.h0)
        col = s.color_check(frame)
        worst = max(worst, abs(got - want))
        print(f"  attendu +{want:5.1f} g  mesuré +{got:5.1f} g  couleur {col.get('best')} (ok={col.get('ok')})")
        if not col.get("ok"):
            worst = max(worst, 99)
    print("OK" if worst < 9 else "ÉCHEC", f"(erreur max {worst:.1f} g sur 300 g pleine échelle)")
    return 0 if worst < 9 else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--camera", default="0", help="index ou chemin de la caméra (défaut 0)")
    p.add_argument("--calib", type=Path, default=DEFAULT_CALIB)
    p.add_argument("--grams-calib", type=Path, default=DEFAULT_GRAMS)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--calibrate", action="store_true")
    g.add_argument("--set-empty", action="store_true")
    g.add_argument("--add-point", type=float, metavar="GRAMMES")
    g.add_argument("--live", action="store_true")
    g.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    cam = int(a.camera) if a.camera.isdigit() else a.camera
    if a.selftest:
        return selftest()
    if a.calibrate:
        return calibrate(cam, a.calib)
    if a.set_empty:
        return set_empty(cam, a.calib)
    if a.add_point is not None:
        return add_point(cam, a.calib, a.add_point, a.grams_calib)
    if a.live:
        return live(cam, a.calib)
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
