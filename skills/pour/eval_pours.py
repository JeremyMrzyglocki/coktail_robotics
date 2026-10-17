"""Évaluation finale (slides) : précision des versements, protocole EXPERIMENT.md.

  # 10 versements par cible, bouteille rouge
  python eval_pours.py run --container red --targets 30 60 90 all --n 10
  # 3 cocktails complets
  python eval_pours.py cocktails --names mojito lagon_bleu sunset
  # tableau + figure à partir des CSV
  python eval_pours.py report data/eval_*.csv

Vérité terrain :
  - mock : la simulation (exacte) ;
  - vrai robot : la BALANCE de cuisine. Après chaque versement le script demande le poids
    ajouté (tare le verre avant chaque versement). Entrée vide = pas de pesée (l'essai
    n'entre pas dans le taux de succès).
Succès : |vrai - cible| <= 10 g. Pour "all" : la bouteille est vide à 10 g près.
Le script met la bouteille en pause quand il faut la remplir ou vider le verre (mock : auto).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from bar_state import ALL, HERE, BarState, PourRequestError, load_bar_config
from pour_skill import PourConfig, pour
from robot_io import Robot

TOL_G = 10.0


def ask_float(msg: str) -> float | None:
    while True:
        s = input(msg).strip().replace(",", ".")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            print("  nombre attendu (ou Entrée pour passer)")


class Bench:
    def __init__(self, backend: str, camera: str):
        from glass_level import GlassScale, MockGlassSensor

        self.bar = load_bar_config()
        self.state = BarState.fresh(self.bar)
        self.mock = backend == "mock"
        kw = dict(bottles=dict(self.state.remaining_g), glass_capacity_g=self.bar.glass_capacity_g) if self.mock else {}
        self.cfg = PourConfig()
        self.robot = Robot(backend, arms=(self.cfg.arm,), **kw)
        self.robot.enable(self.cfg.arm)
        self.sensor = MockGlassSensor(self.robot) if self.mock else \
            GlassScale(camera=int(camera) if camera.isdigit() else camera)

    def hold_bottle(self, color):
        if self.mock:
            self.robot.backend.attach_bottle(color)
        else:
            input(f"  >>> Bouteille {color} en main, verticale au-dessus du verre ? Entrée pour continuer ")

    def ensure(self, color, grams):
        """Assez dans la bouteille et de la place dans le verre, sinon on remet à zéro."""
        need = self.bar.containers[color].capacity_g if grams == ALL else grams
        if grams == ALL or self.state.remaining_g[color] < need + 5:
            if self.mock:
                self.robot.backend.set_bottle(color, self.bar.containers[color].capacity_g)
            else:
                input(f"  >>> Remplir la bouteille {color} à {self.bar.containers[color].capacity_g:.0f} g (balance), Entrée ")
            self.state.refill(color, self.bar.containers[color].capacity_g)
        if self.state.glass_free_g < need + TOL_G:
            if self.mock:
                self.robot.backend.empty_glass()
            else:
                input("  >>> Vider le verre (et le remettre en place), Entrée ")
            self.state.new_glass()

    def truth(self, glass_before, color, target):
        if self.mock:
            return self.robot.backend.glass_grams() - glass_before, self.robot.backend.bottle_g(color)
        added = ask_float("  >>> Poids AJOUTÉ dans le verre, lu sur la balance (g) : ")
        left = ask_float("  >>> M&M's restant dans la bouteille (g) : ") if target == ALL else None
        return added, left

    def one(self, color, target, trial, kind, cocktail=None) -> dict:
        if kind == "single":
            self.ensure(color, target)
        self.hold_bottle(color)
        g0 = self.robot.backend.glass_grams() if self.mock else None
        rem_before = self.state.remaining_g[color]
        try:
            r = pour(self.robot, target, color, sensor=self.sensor, state=self.state, config=self.cfg, bar=self.bar)
        except PourRequestError as e:
            return {"kind": kind, "cocktail": cocktail, "trial": trial, "container": color,
                    "target": str(target), "refused": str(e)}
        truth, left = self.truth(g0, color, target)
        goal = rem_before if target == ALL else float(target)
        row = {"backend": "mock" if self.mock else "openarm", "kind": kind, "cocktail": cocktail, "trial": trial, "container": color, "target": str(target),
               "goal_g": goal, "poured_est_g": r.poured_g, "source": r.source, "truth_g": truth,
               "bottle_left_g": left, "onset_deg": r.flow_onset_deg, "onset_by": r.onset_by,
               "duration_s": r.duration_s, "skill_success": r.success, "reason": r.reason, "trace": r.trace_path}
        if truth is not None:
            row["error_g"] = truth - goal
            row["est_error_g"] = (r.poured_g - truth) if r.poured_g is not None else np.nan
            row["success"] = (left is not None and left <= TOL_G) if target == ALL and left is not None \
                else abs(truth - goal) <= TOL_G
        print(f"  essai {trial:2d} {color:6s} cible {str(target):>4s} -> vrai "
              f"{'—' if truth is None else f'{truth:5.1f}'} g, estimé "
              f"{'—' if r.poured_g is None else f'{r.poured_g:5.1f}'} g ({r.source}) {r.reason}")
        return row

    def close(self):
        self.robot.close(disable=False)


def save(rows, prefix) -> Path:
    out = HERE / "data" / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    out.parent.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f">>> {out}")
    return out


def cmd_run(a):
    b = Bench(a.backend, a.camera)
    rows = []
    try:
        for t in a.targets:
            target = ALL if t == ALL else float(t)
            print(f"== cible {t} ({a.n} essais)")
            for i in range(1, a.n + 1):
                rows.append(b.one(a.container, target, i, "single"))
    except KeyboardInterrupt:
        print("\ninterrompu : on garde les essais faits")
    finally:
        b.close()
    report([save(rows, "eval")], a.plots)


def cmd_cocktails(a):
    b = Bench(a.backend, a.camera)
    rows = []
    try:
        for name in a.names:
            recipe = b.bar.cocktails[name]
            if b.mock:
                b.robot.backend.empty_glass()
            else:
                input(f"== {name} : verre vide en place, Entrée ")
            b.state.new_glass()
            for color, g in recipe.items():  # bouteilles pleines au début de chaque cocktail
                if b.state.remaining_g[color] < g + 5:
                    b.ensure(color, ALL)
            print(f"== {name} {recipe}")
            for color, g in recipe.items():
                rows.append(b.one(color, g, 1, "cocktail", cocktail=name))
    finally:
        b.close()
    out = save(rows, "cocktails")
    report([out], a.plots)


def report(files, plots_dir: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from analyze_torque import BLUE, GRID, INK, INK2, MUTED  # styles des slides

    df = pd.concat([pd.read_csv(f) for f in files if f], ignore_index=True)
    df = df[df["truth_g"].notna()] if "truth_g" in df else df.iloc[0:0]
    if df.empty:
        print("Aucun essai avec vérité terrain.")
        return
    order = [t for t in ("30.0", "60.0", "90.0", "all") if t in set(df["target"].astype(str))]
    df["target"] = df["target"].astype(str)
    rows = []
    for t in order:
        d = df[(df["target"] == t) & (df["kind"] == "single")]
        if d.empty:
            continue
        rows.append({"cible": t.replace(".0", " g") if t != "all" else "vider", "n": len(d),
                     "erreur moy (g)": d["error_g"].mean(), "|erreur| moy (g)": d["error_g"].abs().mean(),
                     "écart-type (g)": d["error_g"].std(), "succès ±10 g": f"{d['success'].mean() * 100:.0f} %",
                     "erreur capteur (g)": d["est_error_g"].abs().mean(), "durée (s)": d["duration_s"].mean()})
    if rows:
        print(pd.DataFrame(rows).round(1).to_string(index=False))
        bias = df[(df["kind"] == "single") & (df["target"] != "all")]["error_g"].mean()
        print(f"\nBiais moyen {bias:+.1f} g. Biais < 0 : on s'arrête trop tôt -> baisser PourConfig.latency_s ;"
              f" > 0 : l'augmenter.")
    c = df[df["kind"] == "cocktail"]
    if not c.empty:
        print("\nCocktails :")
        for name, d in c.groupby("cocktail"):
            parts = ", ".join(f"{r.container} {r.truth_g:.0f}/{r.goal_g:.0f} g" for r in d.itertuples())
            print(f"  {name:12s} {parts}   {'OK' if d['success'].all() else 'raté'}")

    singles = df[df["kind"] == "single"]
    if singles.empty:
        return
    fig, ax = plt.subplots(figsize=(12, 6.75))
    ax.axhspan(-TOL_G, TOL_G, color=GRID, alpha=0.6, lw=0)
    ax.axhline(0, color=MUTED, lw=1)
    rng = np.random.default_rng(0)
    labels = []
    for i, t in enumerate(order):
        d = singles[singles["target"] == t]
        if d.empty:
            continue
        x = i + rng.uniform(-0.12, 0.12, len(d))
        ax.scatter(x, d["error_g"], s=70, color=BLUE, edgecolor="white", linewidth=2, zorder=3)
        ax.plot([i - 0.25, i + 0.25], [d["error_g"].mean()] * 2, color=INK, lw=2.5, zorder=4)
        ax.text(i, TOL_G + 1.5, f"{d['success'].mean() * 100:.0f} % ✓", ha="center", color=INK, fontsize=14,
                fontweight="bold")
        labels.append("vider" if t == "all" else f"{float(t):.0f} g")
    ax.set_xticks(range(len(labels)), labels)
    ax.set_xlim(-0.6, len(labels) - 0.4)
    lim = max(TOL_G + 6, float(singles["error_g"].abs().max()) + 3)
    ax.set_ylim(-lim, lim)
    ax.set_ylabel("erreur (g) = versé réel − cible")
    sim = "backend" in singles and (singles["backend"] == "mock").all()
    ax.set_title("Précision du versement — SIMULATION (mock)" if sim else
                 "Précision du versement, mesurée à la balance", pad=26)
    ax.text(0, 1.01, f"bande grise = succès (±{TOL_G:.0f} g) · trait = moyenne · {len(singles)} versements",
            transform=ax.transAxes, color=MUTED, fontsize=11)
    ax.tick_params(axis="x", labelsize=14, labelcolor=INK2)
    fig.tight_layout()
    plots_dir.mkdir(exist_ok=True, parents=True)
    out = plots_dir / "eval_errors.png"
    fig.savefig(out, dpi=150)
    print(f">>> {out}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "cocktails"):
        s = sub.add_parser(name)
        s.add_argument("--backend", choices=["mock", "openarm"], default="mock")
        s.add_argument("--camera", default="0")
        s.add_argument("--plots", type=Path, default=HERE / "plots")
        s.add_argument("--i-understand-motors-will-be-armed", dest="confirm", action="store_true")
    sub.choices["run"].add_argument("--container", default="red")
    sub.choices["run"].add_argument("--targets", nargs="+", default=["30", "60", "90", "all"])
    sub.choices["run"].add_argument("--n", type=int, default=10)
    sub.choices["cocktails"].add_argument("--names", nargs="+", default=["mojito", "lagon_bleu", "sunset"])
    r = sub.add_parser("report")
    r.add_argument("files", nargs="+", type=Path)
    r.add_argument("--plots", type=Path, default=HERE / "plots")
    a = p.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")
    if a.cmd == "report":
        report(a.files, a.plots)
        return 0
    if a.backend == "openarm" and not a.confirm:
        print("Le vrai robot va être armé et va bouger. Ajoute --i-understand-motors-will-be-armed.")
        return 2
    {"run": cmd_run, "cocktails": cmd_cocktails}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
