"""Analyse des logs de couple : bruit, sensibilité masse -> couple, figures pour les slides.

  # Démo complète sur le mock (génère des pesées 0..200 g puis analyse)
  python analyze_torque.py --demo

  # Pesées réelles : un CSV par masse (log_torque.py --mass-g ...)
  python analyze_torque.py data/weigh_*.csv --joint J2

  # Trace d'un versement (CSV écrit par pour_skill.py)
  python analyze_torque.py --pour data/pour_20261017_153000.csv

Sorties : plots/*.png (fond blanc, 16:9), config/torque_calib.json, résumé console.
Méthode :
  - segment statique = |dq| < 0.01 rad/s sur J1..J7, on coupe 0.3 s aux bords ;
  - bruit = écart-type à l'arrêt ; incertitude de la moyenne par blocs de 0.5 s
    (prend en compte la dérive, pas seulement le bruit blanc) ;
  - régression linéaire pondérée couple moyen = a·masse + b ;
  - résolution en masse = écart-type des résidus / |a|.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from robot_io import JOINT_NAMES, TAU_LSB  # noqa: E402

ARM_JOINTS = JOINT_NAMES[:7]

# Palette de référence (skill dataviz) : texte en encre neutre, séries par rôle.
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SEQ_BLUES = ["#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    "font.size": 13, "axes.titlesize": 16, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 2,
    "legend.frameon": False, "text.color": INK,
})


def static_segment(df: pd.DataFrame, vel_thresh=0.01, trim_s=0.3) -> pd.DataFrame:
    dq = df[[f"dq_{j}" for j in ARM_JOINTS]].abs().max(axis=1)
    st = df[dq < vel_thresh]
    if st.empty:
        return st
    t = st["t_rel"]
    return st[(t > t.min() + trim_s) & (t < t.max() - trim_s)]


def block_sem(x: np.ndarray, t: np.ndarray, block_s=0.5) -> float:
    """Erreur standard de la moyenne estimée par blocs (robuste à la corrélation)."""
    if len(x) < 4:
        return float("nan")
    idx = ((t - t[0]) // block_s).astype(int)
    means = pd.Series(x).groupby(idx).mean().to_numpy()
    if len(means) < 3:
        return float(np.std(x, ddof=1) / np.sqrt(len(x)))
    return float(np.std(means, ddof=1) / np.sqrt(len(means)))


def summarize(files: list[Path]) -> pd.DataFrame:
    rows = []
    for f in files:
        df = pd.read_csv(f)
        st = static_segment(df)
        if st.empty:
            print(f"  ! {f.name} : aucun segment statique, ignoré")
            continue
        mass = pd.to_numeric(df["mass_g"], errors="coerce").dropna()
        row = {"file": f.name, "mass_g": float(mass.iloc[0]) if len(mass) else np.nan,
               "n": len(st), "duration_s": st["t_rel"].iloc[-1] - st["t_rel"].iloc[0]}
        for j in ARM_JOINTS:
            x = st[f"tau_{j}"].to_numpy()
            row[f"mean_{j}"] = x.mean()
            row[f"std_{j}"] = x.std(ddof=1)
            row[f"sem_{j}"] = block_sem(x, st["t_rel"].to_numpy())
        rows.append(row)
    df = pd.DataFrame(rows)
    # Différence par rapport à la bouteille VIDE (masse 0) : c'est ce qu'on calibre.
    ref = df[df["mass_g"] == 0]
    for j in ARM_JOINTS:
        base = ref[f"mean_{j}"].mean() if len(ref) else np.nan
        df[f"delta_{j}"] = df[f"mean_{j}"] - base
    return df


def fit_joint(summary: pd.DataFrame, j: str) -> dict:
    s = summary.dropna(subset=["mass_g"])
    if s["mass_g"].nunique() < 2:
        return {}
    ycol = f"delta_{j}" if s[f"delta_{j}"].notna().all() else f"mean_{j}"
    m, y = s["mass_g"].to_numpy(), s[ycol].to_numpy()
    w = 1 / np.maximum(s[f"sem_{j}"].fillna(s[f"std_{j}"]).to_numpy(), 1e-4)
    a, b = np.polyfit(m, y, 1, w=w)
    resid = y - (a * m + b)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - np.sum(resid ** 2) / ss_tot if ss_tot > 0 else float("nan")
    resid_std = float(np.std(resid, ddof=2)) if len(m) > 2 else float(np.mean(s[f"sem_{j}"]))
    return {"joint": j, "slope_Nm_per_g": float(a), "intercept_Nm": float(b), "r2": float(r2),
            "resid_std_Nm": resid_std,
            "mass_resolution_g": resid_std / abs(a) if a else float("inf"),
            "noise_std_Nm": float(s[f"std_{j}"].mean()), "n_trials": int(len(m))}


# ----------------------------------------------------------------------------- plots

def plot_timeseries(files, summary, joint, out: Path):
    fig, ax = plt.subplots(figsize=(12, 6.75))
    s = summary.sort_values("mass_g")
    colors = dict(zip(s["file"], np.array(SEQ_BLUES)[np.linspace(0, len(SEQ_BLUES) - 1, len(s)).astype(int)]))
    for f in files:
        if f.name not in colors:
            continue
        df = pd.read_csv(f)
        t, tau = df["t_rel"], df[f"tau_{joint}"]
        ax.plot(t, tau, color=colors[f.name], alpha=0.25, lw=1)
        ax.plot(t, tau.rolling(25, center=True, min_periods=1).mean(), color=colors[f.name], lw=2)
        m = s.loc[s["file"] == f.name, "mass_g"].iloc[0]
        ax.annotate(f"{m:.0f} g", (t.iloc[-1], tau.tail(50).mean()), xytext=(6, 0),
                    textcoords="offset points", va="center", color=INK2, fontsize=11)
    ax.set_title(f"Couple {joint} à l'arrêt, par masse dans la bouteille", pad=26)
    ax.set_xlabel("temps (s)")
    ax.set_ylabel("couple (N·m)")
    ax.text(0, 1.01, "trait fin = brut · trait épais = moyenne glissante 0.25 s",
            transform=ax.transAxes, color=MUTED, fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_calibration(summary, fit, out: Path):
    j = fit["joint"]
    s = summary.dropna(subset=["mass_g"])
    fig, ax = plt.subplots(figsize=(12, 6.75))
    ycol = f"delta_{j}" if s[f"delta_{j}"].notna().all() else f"mean_{j}"
    ax.errorbar(s["mass_g"], s[ycol], yerr=2 * s[f"sem_{j}"].fillna(0), fmt="o", ms=9,
                color=BLUE, ecolor=BLUE, elinewidth=2, capsize=0, mec="white", mew=2, zorder=3)
    xs = np.linspace(0, s["mass_g"].max() * 1.05, 50)
    ax.plot(xs, fit["slope_Nm_per_g"] * xs + fit["intercept_Nm"], color=INK2, lw=2, ls="--", zorder=2)
    ax.set_title(f"Peser au couple : {j} voit les M&M's dans la bouteille")
    ax.set_xlabel("masse de M&M's dans la bouteille (g)")
    ax.set_ylabel(f"Δ couple {j} vs bouteille vide (N·m)" if ycol.startswith("delta") else f"couple moyen {j} (N·m)")
    txt = (f"pente {fit['slope_Nm_per_g'] * 1000:.2f} mN·m / g   ·   R² {fit['r2']:.3f}\n"
           f"résolution ≈ {fit['mass_resolution_g']:.1f} g   ·   bruit brut {fit['noise_std_Nm']:.3f} N·m"
           f"   ·   pas de quantif. {TAU_LSB[JOINT_NAMES.index(j)]:.3f} N·m")
    ax.text(0.02, 0.97, txt, transform=ax.transAxes, va="top", color=INK, fontsize=13,
            bbox=dict(facecolor="white", edgecolor=GRID, boxstyle="round,pad=0.5"))
    ax.text(1.0, -0.12, "barres = ±2 erreurs-types de la moyenne", transform=ax.transAxes,
            ha="right", color=MUTED, fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_noise(summary, out: Path, fits: dict):
    fig, ax = plt.subplots(figsize=(12, 6.75))
    x = np.arange(len(ARM_JOINTS))
    noise = [summary[f"std_{j}"].mean() for j in ARM_JOINTS]
    sens = [abs(fits[j]["slope_Nm_per_g"]) * 50 if fits.get(j) else 0 for j in ARM_JOINTS]
    wbar = 0.38
    ax.bar(x - wbar / 2 - 0.01, noise, wbar, color=MUTED, label="bruit à l'arrêt (écart-type)")
    ax.bar(x + wbar / 2 + 0.01, sens, wbar, color=BLUE, label="signal de 50 g de M&M's")
    ax.set_xticks(x, ARM_JOINTS)
    ax.set_ylabel("N·m")
    ax.set_title("Signal 50 g vs bruit, par articulation")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_pour(csv: Path, out: Path):
    df = pd.read_csv(csv)
    t = df["t_rel"]
    panels = [("tilt_deg", "inclinaison (°)", BLUE), ("added_g", "grammes versés", AQUA)]
    tau_col = next((c for c in ("tau_weigh", "tau_J2") if c in df), None)
    if tau_col:
        panels.append((tau_col, "couple pesée (N·m)" if tau_col == "tau_weigh" else "couple J2 (N·m)", ORANGE))
    fig, axes = plt.subplots(len(panels), 1, figsize=(12, 6.75), sharex=True)
    for ax, (col, lab, c) in zip(axes, panels):
        y = df[col]
        ax.plot(t, y, color=c, lw=1 if col.startswith("tau") else 2, alpha=0.5 if col.startswith("tau") else 1)
        if col.startswith("tau"):
            ax.plot(t, y.rolling(25, center=True, min_periods=1).mean(), color=c, lw=2)
        if col == "added_g" and "goal_g" in df and df["goal_g"].notna().any():
            goal = df["goal_g"].dropna().iloc[0]
            ax.axhline(goal, color=INK2, ls="--", lw=1.5)
            ax.text(t.iloc[0], goal, " cible", va="bottom", color=INK2, fontsize=11)
        ax.set_ylabel(lab)
    if "state" in df:  # bandes d'état discrètes en haut
        for st, g in df.groupby((df["state"] != df["state"].shift()).cumsum()):
            axes[0].text(g["t_rel"].iloc[0], 1.02, g["state"].iloc[0], transform=axes[0].get_xaxis_transform(),
                         fontsize=9, color=MUTED, rotation=20)
            for ax in axes:
                ax.axvline(g["t_rel"].iloc[0], color=GRID, lw=1)
    axes[0].set_title(f"Versement en boucle fermée : {csv.stem}", pad=28)
    axes[-1].set_xlabel("temps (s)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


# ----------------------------------------------------------------------------- démo

def make_demo_data(outdir: Path, masses=(0, 30, 60, 90, 120), seconds=3.0, same_side=True) -> list[Path]:
    """Pesées simulées (protocole EXPERIMENT.md). same_side=True : on arrive à la pose
    de mesure toujours par le même côté ; False : côté aléatoire, pour montrer
    l'hystérésis de frottement sur les slides."""
    from robot_io import Robot

    rng = np.random.default_rng(1)
    files = []
    for m in masses:
        robot = Robot("mock", arms=("right_arm",), content_g=m, seed=int(m))
        robot.enable("right_arm")
        q0 = robot.get_targets("right_arm")
        bump = q0.copy()
        side = -np.ones(2) if same_side else rng.choice([-1, 1], size=2)
        bump[[1, 3]] += side * 0.05  # arrivée sur J2 et J4 par le même côté (ou aléatoire)
        robot.move_joints("right_arm", bump, speed=0.2)
        robot.move_joints("right_arm", q0, speed=0.2)
        rows, t0 = [], time.time()
        while time.time() - t0 < seconds:
            s = robot.get_joint_states("right_arm")
            r = s.as_row()
            r.update(t_rel=s.t - t0, label="demo", mass_g=m)
            rows.append(r)
            time.sleep(0.01)
        robot.close()
        f = outdir / f"demo_weigh_{'same' if same_side else 'random'}_{m:03d}g.csv"
        pd.DataFrame(rows).to_csv(f, index=False)
        files.append(f)
        print(f"  demo {m:3d} g -> {f}")
    return files


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="*", type=Path)
    p.add_argument("--joint", default="J2",
                   help="articulation à calibrer (défaut J2 : DM8009 QDD 9:1, peu de frottement ; "
                        "le mock ne sait pas que J3-J4 en 40:1 frottent beaucoup plus). 'auto' = meilleure résolution")
    p.add_argument("--demo", action="store_true", help="génère des pesées mock puis analyse")
    p.add_argument("--demo-random-side", action="store_true", help="démo avec côté d'arrivée aléatoire (hystérésis)")
    p.add_argument("--pour", type=Path, default=None, help="trace CSV d'un versement à tracer")
    p.add_argument("--plots", type=Path, default=Path("plots"))
    p.add_argument("--calib-out", type=Path, default=Path("config/torque_calib.json"))
    a = p.parse_args()
    a.plots.mkdir(exist_ok=True, parents=True)

    if a.pour:
        out = a.plots / f"{a.pour.stem}.png"
        plot_pour(a.pour, out)
        print(f">>> {out}")
        if not a.files and not a.demo:
            return 0

    files = a.files
    if a.demo:
        files = make_demo_data(Path("data"), same_side=not a.demo_random_side)
    if not files:
        p.print_help()
        return 1

    summary = summarize(files)
    if summary.empty:
        print("Aucune donnée exploitable.")
        return 1
    fits = {j: fit_joint(summary, j) for j in ARM_JOINTS}
    usable = {j: f for j, f in fits.items() if f}
    pd.set_option("display.width", 160)
    print("\nBruit à l'arrêt (écart-type, N·m) :")
    print(summary[["file", "mass_g", "n"] + [f"std_{j}" for j in ARM_JOINTS]].round(4).to_string(index=False))

    if not usable:
        print("\nUne seule masse : pas de régression. Bruit seul ci-dessus.")
        return 0

    print("\nSensibilité masse -> couple :")
    print(f"  {'joint':5} {'mN·m/g':>8} {'R²':>6} {'résol. g':>9} {'bruit N·m':>10} {'LSB N·m':>8}")
    for j, f in usable.items():
        print(f"  {j:5} {f['slope_Nm_per_g'] * 1000:8.3f} {f['r2']:6.3f} {f['mass_resolution_g']:9.1f}"
              f" {f['noise_std_Nm']:10.4f} {TAU_LSB[JOINT_NAMES.index(j)]:8.4f}")
    joint = min(usable, key=lambda j: usable[j]["mass_resolution_g"]) if a.joint == "auto" else a.joint
    fit = usable[joint]
    print(f"\n>>> articulation retenue : {joint}  (résolution ≈ {fit['mass_resolution_g']:.1f} g)")

    a.calib_out.parent.mkdir(parents=True, exist_ok=True)
    fit["source_files"] = [f.name for f in files]
    fit["from_mock_demo"] = bool(a.demo)
    a.calib_out.write_text(json.dumps(fit, indent=2))
    summary.to_csv(a.plots / "torque_summary.csv", index=False)
    plot_timeseries(files, summary, joint, a.plots / "torque_timeseries.png")
    plot_calibration(summary, fit, a.plots / "torque_calibration.png")
    plot_noise(summary, a.plots / "torque_signal_vs_noise.png", usable)
    print(f">>> {a.calib_out}, {a.plots}/torque_*.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
