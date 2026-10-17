"""Niveau de remplissage du verre par vision (OpenCV), zone d'intérêt fixe.

Deux méthodes :
  - "hsv"  : le contenu a une couleur reconnaissable (bonbons, riz coloré).
             Seuillage HSV dans la zone.
  - "diff" : riz blanc / contenu peu coloré. On capture une image du verre VIDE,
             puis tout pixel qui en diffère assez est du contenu. Exige une
             caméra et un éclairage fixes.
Le niveau = hauteur remplie depuis le bas de la zone, de 0 (vide) à 1 (haut de
la zone). Placer le haut de la zone au bord du verre, le bas au fond.

  python glass_level.py --calibrate          # webcam du Mac, réglage interactif
  python glass_level.py                      # affichage live du niveau
  python glass_level.py --image photo.jpg    # test sur une image
  python glass_level.py --selftest           # test synthétique sans caméra

macOS : autoriser l'accès caméra pour le Terminal (Réglages > Confidentialité).

Calibration (fenêtre "calib") :
  r  sélectionner la zone (glisser puis Entrée)
  clic gauche  échantillonner la couleur du contenu (plusieurs clics)
  b  capturer la référence "verre vide" (méthode diff)
  m  basculer hsv / diff        s  sauvegarder        q  quitter
  Curseurs : bornes HSV, seuil diff, fraction de ligne remplie.
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

DEFAULT_CALIB = Path("config/glass_calib.json")


@dataclass
class GlassCalib:
    roi: list[int] = field(default_factory=lambda: [0, 0, 0, 0])  # x, y, w, h
    mode: str = "hsv"
    hsv_lo: list[int] = field(default_factory=lambda: [0, 80, 60])
    hsv_hi: list[int] = field(default_factory=lambda: [179, 255, 255])
    diff_thresh: int = 35
    row_frac: float = 0.35      # une ligne est "remplie" si >= 35 % de ses pixels sont du contenu
    ref_path: str = "config/glass_empty.png"

    @classmethod
    def load(cls, path=DEFAULT_CALIB) -> "GlassCalib":
        return cls(**json.loads(Path(path).read_text()))

    def save(self, path=DEFAULT_CALIB):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(asdict(self), indent=2))


def content_mask(frame: np.ndarray, calib: GlassCalib, ref: np.ndarray | None = None) -> np.ndarray:
    x, y, w, h = calib.roi
    crop = frame[y:y + h, x:x + w]
    if calib.mode == "diff":
        if ref is None:
            raise ValueError("méthode diff : référence 'verre vide' manquante (touche b)")
        d = cv2.absdiff(cv2.GaussianBlur(crop, (5, 5), 0), cv2.GaussianBlur(ref[y:y + h, x:x + w], (5, 5), 0))
        mask = (d.max(axis=2) > calib.diff_thresh).astype(np.uint8) * 255
    else:
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        lo, hi = np.array(calib.hsv_lo), np.array(calib.hsv_hi)
        if lo[0] <= hi[0]:
            mask = cv2.inRange(hsv, lo, hi)
        else:  # teinte qui "boucle" (rouges) : H dans [lo, 179] U [0, hi]
            mask = cv2.inRange(hsv, lo, np.array([179, *hi[1:]])) | cv2.inRange(hsv, np.array([0, *lo[1:]]), hi)
    k = np.ones((3, 3), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)


def level_from_mask(mask: np.ndarray, row_frac: float) -> float:
    """Hauteur remplie depuis le bas, tolérante aux trous (grains épars, reflets)."""
    if mask.size == 0:
        return 0.0
    rows = (mask > 0).mean(axis=1)                       # fraction remplie par ligne (haut -> bas)
    filled = np.convolve(rows >= row_frac, np.ones(5) / 5, mode="same")[::-1]  # bas -> haut
    # niveau = plus haute ligne k elle-même remplie, avec >= 80 % de lignes remplies sous elle
    cum = np.cumsum(filled) / np.arange(1, len(filled) + 1)
    ok = np.nonzero((cum >= 0.8) & (filled >= 0.5))[0]
    return float((ok[-1] + 1) / len(filled)) if len(ok) else 0.0


class GlassLevelSensor:
    """Capteur de niveau. `read()` renvoie un niveau lissé dans [0, 1] ou None.

    Le riz ne quitte pas le verre : par défaut le niveau publié est monotone
    (max glissant d'une médiane), ce qui filtre le filet de riz qui traverse la
    zone et la main/bouteille qui masque le verre un instant.
    """

    def __init__(self, calib: GlassCalib | None = None, camera: int | str = 0,
                 median_n=5, monotonic=True):
        self.calib = calib or GlassCalib.load()
        self.cap = None
        if camera is not None:
            api = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" and isinstance(camera, int) else cv2.CAP_ANY
            self.cap = cv2.VideoCapture(camera, api)
            if not self.cap.isOpened():
                raise RuntimeError(f"caméra {camera} indisponible (permission caméra ?)")
        self.ref = cv2.imread(self.calib.ref_path) if self.calib.mode == "diff" else None
        self.hist: deque[float] = deque(maxlen=median_n)
        self.monotonic = monotonic
        self.best = 0.0
        self.last_frame = None
        self.last_mask = None

    def reset(self):
        self.hist.clear()
        self.best = 0.0

    def measure(self, frame) -> float:
        self.last_mask = content_mask(frame, self.calib, self.ref)
        return level_from_mask(self.last_mask, self.calib.row_frac)

    def read(self) -> float | None:
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok:
            return None
        self.last_frame = frame
        self.hist.append(self.measure(frame))
        med = float(np.median(self.hist))
        if self.monotonic:
            self.best = max(self.best, med)
            return self.best
        return med

    def close(self):
        if self.cap is not None:
            self.cap.release()


class MockGlassSensor:
    """Capteur simulé pour le backend mock : niveau réel + bruit + trous de mesure."""

    def __init__(self, robot, noise=0.01, dropout=0.03, seed=0):
        self.robot, self.noise, self.dropout = robot, noise, dropout
        self.rng = np.random.default_rng(seed)

    def reset(self):
        pass

    def read(self) -> float | None:
        if self.rng.random() < self.dropout:
            return None
        return float(np.clip(self.robot.backend.glass_fill() + self.rng.normal(0, self.noise), 0, 1.2))

    def close(self):
        pass


# --------------------------------------------------------------------------- UI

def draw_overlay(frame, calib: GlassCalib, level: float | None, mask=None):
    x, y, w, h = calib.roi
    out = frame.copy()
    if w and h:
        if mask is not None:
            tint = np.zeros_like(out[y:y + h, x:x + w])
            tint[mask > 0] = (0, 200, 255)
            out[y:y + h, x:x + w] = cv2.addWeighted(out[y:y + h, x:x + w], 1.0, tint, 0.5, 0)
        cv2.rectangle(out, (x, y), (x + w, y + h), (255, 255, 255), 2)
        if level is not None:
            ly = int(y + h * (1 - min(level, 1.0)))
            cv2.line(out, (x - 10, ly), (x + w + 10, ly), (0, 255, 0), 2)
    txt = "niveau: ---" if level is None else f"niveau: {level * 100:5.1f} %"
    cv2.putText(out, f"{txt}  [{calib.mode}]", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
    cv2.putText(out, f"{txt}  [{calib.mode}]", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return out


def calibrate(camera, path: Path):
    calib = GlassCalib.load(path) if path.exists() else GlassCalib()
    cap = cv2.VideoCapture(camera, cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_ANY)
    if not cap.isOpened():
        print("Caméra indisponible. Sur macOS : autoriser le Terminal dans Confidentialité > Caméra.")
        return 1
    ok, frame = cap.read()
    if not ok:
        return 1
    if not calib.roi[2]:
        hh, ww = frame.shape[:2]
        calib.roi = [ww // 3, hh // 4, ww // 3, hh // 2]
    ref = cv2.imread(calib.ref_path) if Path(calib.ref_path).exists() else None
    samples: list[np.ndarray] = []
    win = "calib"
    cv2.namedWindow(win)

    def tb(name, val, mx):
        cv2.createTrackbar(name, win, int(val), mx, lambda _: None)

    for i, c in enumerate("HSV"):
        tb(f"{c} min", calib.hsv_lo[i], 179 if c == "H" else 255)
        tb(f"{c} max", calib.hsv_hi[i], 179 if c == "H" else 255)
    tb("diff", calib.diff_thresh, 255)
    tb("ligne %", int(calib.row_frac * 100), 100)

    def on_click(event, px, py, *_):
        if event == cv2.EVENT_LBUTTONDOWN and frame is not None:
            hsv = cv2.cvtColor(frame[max(py - 3, 0):py + 4, max(px - 3, 0):px + 4], cv2.COLOR_BGR2HSV)
            samples.append(hsv.reshape(-1, 3))
            allpx = np.concatenate(samples)
            lo = np.percentile(allpx, 3, axis=0) - [8, 40, 40]
            hi = np.percentile(allpx, 97, axis=0) + [8, 40, 40]
            lo, hi = np.clip(lo, 0, [179, 255, 255]).astype(int), np.clip(hi, 0, [179, 255, 255]).astype(int)
            for i, ch in enumerate("HSV"):
                cv2.setTrackbarPos(f"{ch} min", win, int(lo[i]))
                cv2.setTrackbarPos(f"{ch} max", win, int(hi[i]))
            print(f"échantillon {len(samples)} : HSV lo={lo.tolist()} hi={hi.tolist()}")

    cv2.setMouseCallback(win, on_click)
    print(__doc__.split("Calibration")[1])
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        calib.hsv_lo = [cv2.getTrackbarPos(f"{c} min", win) for c in "HSV"]
        calib.hsv_hi = [cv2.getTrackbarPos(f"{c} max", win) for c in "HSV"]
        calib.diff_thresh = cv2.getTrackbarPos("diff", win)
        calib.row_frac = max(cv2.getTrackbarPos("ligne %", win), 1) / 100
        try:
            mask = content_mask(frame, calib, ref)
            level = level_from_mask(mask, calib.row_frac)
        except ValueError:
            mask, level = None, None
        cv2.imshow(win, draw_overlay(frame, calib, level, mask))
        k = cv2.waitKey(1) & 0xFF
        if k == ord("r"):
            r = cv2.selectROI("zone", frame, showCrosshair=False)
            cv2.destroyWindow("zone")
            if r[2] and r[3]:
                calib.roi = [int(v) for v in r]
        elif k == ord("b"):
            Path(calib.ref_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(calib.ref_path, frame)
            ref = frame.copy()
            print(f"référence verre vide -> {calib.ref_path}")
        elif k == ord("m"):
            calib.mode = "diff" if calib.mode == "hsv" else "hsv"
            print("méthode :", calib.mode)
        elif k == ord("s"):
            calib.save(path)
            print(f"calibration -> {path}")
        elif k in (ord("q"), 27):
            break
    cap.release()
    cv2.destroyAllWindows()
    return 0


def live(camera, path: Path):
    sensor = GlassLevelSensor(GlassCalib.load(path), camera=camera, monotonic=False)
    t0, n = time.time(), 0
    while True:
        level = sensor.read()
        if sensor.last_frame is None:
            break
        n += 1
        img = draw_overlay(sensor.last_frame, sensor.calib, level, sensor.last_mask)
        cv2.putText(img, f"{n / (time.time() - t0):.0f} fps", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.imshow("niveau", img)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break
    sensor.close()
    cv2.destroyAllWindows()
    return 0


def synthetic_glass(level: float, w=640, h=480, color=(40, 160, 230), seed=0) -> np.ndarray:
    """Image de test : fond gris, verre, contenu coloré granuleux jusqu'à `level`."""
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 90, np.uint8)
    x0, y0, gw, gh = 260, 120, 120, 260
    cv2.rectangle(img, (x0, y0), (x0 + gw, y0 + gh), (200, 200, 200), 2)
    top = int(y0 + gh * (1 - level))
    fill = np.array(color, np.int16) + rng.integers(-25, 25, (y0 + gh - top, gw, 3))
    img[top:y0 + gh, x0:x0 + gw] = np.clip(fill, 0, 255).astype(np.uint8)
    holes = rng.random((y0 + gh - top, gw)) < 0.08  # grains manquants
    img[top:y0 + gh, x0:x0 + gw][holes] = 90
    return img


def selftest() -> int:
    calib = GlassCalib(roi=[260, 120, 120, 260], mode="hsv", hsv_lo=[5, 120, 120], hsv_hi=[30, 255, 255])
    worst = 0.0
    for lv in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9):
        est = level_from_mask(content_mask(synthetic_glass(lv), calib), calib.row_frac)
        worst = max(worst, abs(est - lv))
        print(f"  vrai {lv:4.2f}  estimé {est:4.2f}")
    ref = synthetic_glass(0.0)
    calib_d = GlassCalib(roi=calib.roi, mode="diff")
    est = level_from_mask(content_mask(synthetic_glass(0.4), calib_d, ref), calib_d.row_frac)
    print(f"  diff : vrai 0.40  estimé {est:4.2f}")
    worst = max(worst, abs(est - 0.4))
    print("OK" if worst < 0.03 else "ÉCHEC", f"(erreur max {worst:.3f})")
    return 0 if worst < 0.03 else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--camera", default="0", help="index ou chemin de la caméra (défaut 0)")
    p.add_argument("--calib", type=Path, default=DEFAULT_CALIB)
    p.add_argument("--calibrate", action="store_true")
    p.add_argument("--image", type=Path)
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    cam = int(a.camera) if a.camera.isdigit() else a.camera
    if a.selftest:
        return selftest()
    if a.calibrate:
        return calibrate(cam, a.calib)
    if a.image:
        calib = GlassCalib.load(a.calib)
        s = GlassLevelSensor(calib, camera=None)
        frame = cv2.imread(str(a.image))
        level = s.measure(frame)
        out = a.image.with_name(a.image.stem + "_level.png")
        cv2.imwrite(str(out), draw_overlay(frame, calib, level, s.last_mask))
        print(f"niveau {level * 100:.1f} %  -> {out}")
        return 0
    return live(cam, a.calib)


if __name__ == "__main__":
    raise SystemExit(main())
