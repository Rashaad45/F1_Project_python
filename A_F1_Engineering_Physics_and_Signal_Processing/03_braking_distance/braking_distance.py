"""
Project A3 - F1 braking distance: from d = v^2/2a to an aerodynamic model
identified from real telemetry
==========================================================================

Part 1  Calculator (constant deceleration)
        v^2 = v0^2 - 2 a d   ->   d = v0^2 / (2a),   t = v0 / a
        Evaluated from 300 km/h for 1 g ... 6 g.

Part 2  Aerodynamic model (deceleration grows with speed)
        Newton:  m dv/dt = -[ mu (m g + 1/2 rho ClA v^2) + 1/2 rho CdA v^2 ]
                 a(v)   = c0 + c1 v^2,   c0 = mu g,  c1 = rho (mu ClA + CdA)/(2m)
        Using dv/dt = v dv/ds and separating variables:
                 d(v0 -> v1) = 1/(2 c1) * ln[(c0 + c1 v0^2) / (c0 + c1 v1^2)]
                 t(v0 -> 0)  = arctan(v0 sqrt(c1/c0)) / sqrt(c0 c1)

Part 3  System identification from a real qualifying lap (OpenF1)
        - detect braking zones from the brake channel
        - between consecutive braking samples:  a_i = (v_i^2 - v_{i+1}^2) / (2 ds_i)
          evaluated at v_mid^2 = (v_i^2 + v_{i+1}^2)/2
        - linear least squares  a = c0 + c1 v^2   ->  mu, implied ClA
        - compare constant-a and aero models against every braking zone

Run   python braking_distance.py              (300 km/h, NOR Monza 2024 Q)
      python braking_distance.py --speed 330 --driver LEC
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import f1data  # noqa: E402

OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
G = 9.81
CAR = dict(m=800.0, rho=1.20, CdA=1.0)  # kg (car+driver+quali fuel), kg/m^3, m^2


# ------------------------------------------------------------ Part 1
def constant_decel(v0_kmh: float, g_levels=(1, 2, 3, 4, 5, 6)) -> pd.DataFrame:
    v0 = v0_kmh / 3.6
    return pd.DataFrame([{"decel_g": g, "decel_ms2": g * G,
                          "distance_m": v0 ** 2 / (2 * g * G),
                          "time_s": v0 / (g * G)} for g in g_levels])


# ------------------------------------------------------------ Part 2
def aero_distance(v0, v1, c0, c1):
    return np.log((c0 + c1 * v0 ** 2) / (c0 + c1 * v1 ** 2)) / (2 * c1)


def aero_stop_time(v0, c0, c1):
    return np.arctan(v0 * np.sqrt(c1 / c0)) / np.sqrt(c0 * c1)


def simulate_aero(v0, v1, c0, c1):
    """Numerical check of the closed form: integrate state y = [s, v] with
    dy/dt = [v, -(c0 + c1 v^2)] using adaptive Runge-Kutta 4(5)."""
    stop = lambda t, y: y[1] - v1  # noqa: E731  event: speed reached v1
    stop.terminal = True
    sol = solve_ivp(lambda t, y: [y[1], -(c0 + c1 * y[1] ** 2)], (0, 15),
                    [0.0, v0], events=stop, max_step=0.01)
    return sol.y[0], sol.y[1]


# ------------------------------------------------------------ Part 3
def braking_zones(tel: pd.DataFrame, min_drop_kmh=40, heavy_drop_kmh=100):
    """Runs of consecutive samples with brake > 0 that lose >= 40 km/h.

    The brake came on somewhere between sample a (last 'off') and i (first
    'on'); with ~0.27 s between samples we use the midpoint (half-sample
    correction).  The zone ends at the lowest speed while braking.
    'heavy' = loses >= 100 km/h: straight-line, grip-limited stops.  Smaller
    zones are trail-braking into fast corners, where tyre grip is shared
    between braking and cornering (friction circle)."""
    on = tel["brake"].to_numpy() > 0
    zones, i = [], 0
    while i < len(on):
        if not on[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(on) and on[j + 1]:
            j += 1
        a = max(i - 1, 0)
        e = tel.loc[i:j, "speed"].idxmin()
        v0, v1 = tel.loc[a, "speed"], tel.loc[e, "speed"]
        if v0 - v1 >= min_drop_kmh:
            s0 = 0.5 * (tel.loc[a, "distance"] + tel.loc[i, "distance"])
            zones.append({"first_on": i, "end_idx": e, "lap_distance_m": s0,
                          "v0_kmh": v0, "v1_kmh": v1,
                          "measured_d_m": tel.loc[e, "distance"] - s0,
                          "heavy": v0 - v1 >= heavy_drop_kmh})
        i = j + 1
    z = pd.DataFrame(zones)
    v0, v1 = z["v0_kmh"] / 3.6, z["v1_kmh"] / 3.6
    z["mean_decel_g"] = (v0 ** 2 - v1 ** 2) / (2 * z["measured_d_m"]) / G
    return z


def decel_samples(tel, zones):
    """Per-interval deceleration inside heavy zones (brake on at both ends)."""
    v = tel["speed"].to_numpy() / 3.6
    s = tel["distance"].to_numpy()
    rows = []
    for _, zz in zones[zones["heavy"]].iterrows():
        for k in range(int(zz["first_on"]), int(zz["end_idx"])):
            ds = s[k + 1] - s[k]
            if ds > 0 and v[k + 1] < v[k]:
                rows.append({"v2_mid": 0.5 * (v[k] ** 2 + v[k + 1] ** 2),
                             "a": (v[k] ** 2 - v[k + 1] ** 2) / (2 * ds)})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=300.0, help="initial speed km/h")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--circuit", default="Monza")
    ap.add_argument("--driver", default="NOR")
    a = ap.parse_args()

    # ---------------- Part 1
    tab = constant_decel(a.speed)
    print(f"\nPart 1 - constant deceleration from {a.speed:.0f} km/h ({a.speed/3.6:.2f} m/s)")
    print(tab.to_string(index=False, float_format=lambda x: f"{x:8.2f}"))
    tab.to_csv(OUT / "calculator_table.csv", index=False)

    # ---------------- Part 3: identify the model from data
    skey = f1data.session_key(a.year, a.circuit, "Qualifying")
    lap = f1data.fastest_lap(skey, f1data.driver_number(skey, a.driver))
    tel = f1data.lap_telemetry(skey, lap)
    z = braking_zones(tel)
    smp = decel_samples(tel, z)

    # linear least squares:  [1  v^2] [c0 c1]^T = a      (normal equations)
    X = np.column_stack([np.ones(len(smp)), smp["v2_mid"]])
    (c0, c1), *_ = np.linalg.lstsq(X, smp["a"], rcond=None)
    a_const = smp["a"].mean()
    resid = smp["a"] - X @ [c0, c1]
    r2 = 1 - np.sum(resid ** 2) / np.sum((smp["a"] - a_const) ** 2)
    mu = c0 / G
    ClA = (2 * CAR["m"] * c1 / CAR["rho"] - CAR["CdA"]) / mu

    v0s, v1s, dm = z["v0_kmh"] / 3.6, z["v1_kmh"] / 3.6, z["measured_d_m"]
    z["const_model_d_m"] = (v0s ** 2 - v1s ** 2) / (2 * a_const)
    z["aero_model_d_m"] = aero_distance(v0s, v1s, c0, c1)
    h = z["heavy"].to_numpy(bool)
    rmse = lambda col: np.sqrt(np.mean((z.loc[h, col] - dm[h]) ** 2))  # noqa: E731

    print(f"\nPart 3 - {a.driver} {a.circuit} {a.year} Q lap {lap['lap_duration']:.3f}s, "
          f"{len(z)} braking zones ({h.sum()} heavy), {len(smp)} deceleration samples")
    print(z[["lap_distance_m", "v0_kmh", "v1_kmh", "heavy", "measured_d_m", "mean_decel_g",
             "const_model_d_m", "aero_model_d_m"]].round(1).to_string(index=False))
    print(f"\n  Fit a = c0 + c1 v^2 :  c0 = {c0:.2f} m/s^2,  c1 = {c1:.5f} 1/m,  R^2 = {r2:.2f}")
    print(f"  -> mechanical grip mu = {mu:.2f},  implied ClA = {ClA:.2f} m^2 (CdA = {CAR['CdA']})")
    print(f"  Heavy-zone RMSE: constant {a_const/G:.2f} g model = {rmse('const_model_d_m'):.1f} m,"
          f"  aero model = {rmse('aero_model_d_m'):.1f} m")
    print("  (OpenF1 samples at ~3.7 Hz, ~25 m apart at 330 km/h: expect +/-10-15 m noise)")
    z.to_csv(OUT / "braking_zones.csv", index=False)
    smp.to_csv(OUT / "deceleration_samples.csv", index=False)

    # ---------------- Part 2: use the identified model
    v0 = a.speed / 3.6
    s_num, _ = simulate_aero(v0, 0.01, c0, c1)
    print(f"\nPart 2 - identified aero model, {a.speed:.0f} -> 0 km/h:")
    print(f"  closed form d = {aero_distance(v0, 0, c0, c1):6.1f} m | RK45 d = {s_num[-1]:6.1f} m"
          f" | t = {aero_stop_time(v0, c0, c1):.2f} s | decel at {a.speed:.0f} km/h ="
          f" {(c0 + c1 * v0**2)/G:.2f} g")

    # ---------------- plots
    fig, ax = plt.subplots(2, 2, figsize=(13, 9.5))
    v = np.linspace(0.1, 350, 300) / 3.6
    for g in (2, 3, 4, 5, 6):
        ax[0, 0].plot(v * 3.6, v ** 2 / (2 * g * G), lw=1, label=f"{g} g constant")
    ax[0, 0].plot(v * 3.6, aero_distance(v, 0, c0, c1), "k", lw=2.5, label="identified aero model")
    ax[0, 0].axvline(a.speed, color="0.5", ls=":")
    ax[0, 0].set(xlabel="Initial speed [km/h]", ylabel="Distance to stop [m]",
                 title="Braking distance to standstill")
    ax[0, 0].legend(fontsize=8)

    ax[0, 1].scatter(np.sqrt(smp["v2_mid"]) * 3.6, smp["a"] / G, s=18, label="telemetry intervals")
    ax[0, 1].plot(v * 3.6, (c0 + c1 * v ** 2) / G, "k", label=f"fit a = c0 + c1 v^2  (R^2={r2:.2f})")
    ax[0, 1].axhline(a_const / G, color="tab:orange", ls="--", label=f"constant {a_const/G:.2f} g")
    ax[0, 1].set(xlabel="Speed [km/h]", ylabel="Deceleration [g]",
                 title="Deceleration rises with speed (downforce + drag)")
    ax[0, 1].legend(fontsize=8)

    big = z.loc[z["v0_kmh"].idxmax()]
    seg = tel.loc[int(big["first_on"]) - 1:int(big["end_idx"])]
    s_sim, v_sim = simulate_aero(big["v0_kmh"] / 3.6, big["v1_kmh"] / 3.6, c0, c1)
    s_c = np.linspace(0, big["const_model_d_m"], 60)
    v_c = np.sqrt(np.maximum((big["v0_kmh"] / 3.6) ** 2 - 2 * a_const * s_c, 0))
    ax[1, 0].plot(seg["distance"] - big["lap_distance_m"], seg["speed"], "o-", label="telemetry")
    ax[1, 0].plot(s_sim, v_sim * 3.6, "k", label="aero model (RK45)")
    ax[1, 0].plot(s_c, v_c * 3.6, "--", color="tab:orange", label=f"constant {a_const/G:.1f} g")
    ax[1, 0].set(xlabel="Distance from brake point [m]", ylabel="Speed [km/h]",
                 title=f"Heaviest stop: {big['v0_kmh']:.0f} -> {big['v1_kmh']:.0f} km/h")
    ax[1, 0].legend(fontsize=8)

    ax[1, 1].scatter(dm[h], z["const_model_d_m"][h], label=f"constant a (RMSE {rmse('const_model_d_m'):.0f} m)")
    ax[1, 1].scatter(dm[h], z["aero_model_d_m"][h], marker="s",
                     label=f"aero (RMSE {rmse('aero_model_d_m'):.0f} m)")
    ax[1, 1].scatter(dm[~h], z["aero_model_d_m"][~h], marker="x", color="0.4",
                     label="aero, trail-braking corners")
    lim = [0, dm.max() * 1.15]
    ax[1, 1].plot(lim, lim, "k:", lw=1)
    ax[1, 1].set(xlabel="Measured braking distance [m]", ylabel="Model [m]",
                 title="Model vs reality, every braking zone")
    ax[1, 1].legend(fontsize=8)
    for axx in ax.flat:
        axx.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "braking_analysis.png", dpi=150)
    print(f"Saved {OUT/'braking_analysis.png'}")


if __name__ == "__main__":
    main()
