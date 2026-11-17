"""
Project B3 - Where does one driver gain time on another?
F1 telemetry comparison (Advanced)
=========================================================

Compares two drivers' fastest qualifying laps on the same circuit.

Pipeline
    1. Telemetry for both laps (speed, throttle, brake, gear, x, y).
    2. Distance  s(t) = v0*t0 + integral v dt  (trapezoidal rule; v0*t0 covers
       the gap between the timing line and the first telemetry sample).  Integration drift
       makes the two laps a few metres different in length, so each lap is
       rescaled to the same reference length:  s' = s * L_ref / L_i
    3. Resample both laps onto one common distance grid (every 5 m) with
       linear interpolation  ->  t_A(s), t_B(s), v_A(s), v_B(s) ...
    4. Delta time:  dt(s) = t_B(s) - t_A(s)     (+ = driver B is behind)
       Its slope tells where time is lost:  d(dt)/ds = 1/v_B - 1/v_A
    5. Mini-sectors: split the lap into 25 equal pieces; the driver with the
       smaller time in each piece "owns" it -> coloured track map.
    6. Corner table: minimum speed through each braking zone for both drivers.

Run
    python telemetry_comparison.py
    python telemetry_comparison.py --year 2024 --circuit Silverstone --drivers RUS HAM
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import f1data  # noqa: E402

OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
COLS = ["t", "speed", "throttle", "brake", "n_gear", "x", "y"]


def get_lap(skey, acr):
    lap = f1data.fastest_lap(skey, f1data.driver_number(skey, acr))
    tel = f1data.lap_telemetry(skey, lap).dropna(subset=["x", "y"])
    return lap, tel


def lap_distance(tel: pd.DataFrame, lap_time: float) -> np.ndarray:
    """Distance from the timing line for every sample.  The first sample
    arrives t0 > 0 s after the line, so the car has already covered
    v0 * t0 metres; likewise after the last sample until the lap ends."""
    v0 = tel["speed"].iloc[0] / 3.6
    return tel["distance"].to_numpy() + v0 * tel["t"].iloc[0]


def lap_length(tel: pd.DataFrame, lap_time: float) -> float:
    s = lap_distance(tel, lap_time)
    return s[-1] + tel["speed"].iloc[-1] / 3.6 * (lap_time - tel["t"].iloc[-1])


def resample(tel: pd.DataFrame, L_ref: float, grid: np.ndarray, lap_time: float) -> pd.DataFrame:
    s = lap_distance(tel, lap_time) * L_ref / lap_length(tel, lap_time)
    out = {"distance": grid}
    for c in COLS:
        out[c] = np.interp(grid, s, tel[c].to_numpy(float))
    # pin both ends: t = 0 at the line, t = lap time at s = L_ref
    out["t"] = np.interp(grid, np.r_[0, s, L_ref], np.r_[0, tel["t"].to_numpy(), lap_time])
    out["n_gear"] = np.round(out["n_gear"])
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--circuit", default="Monza")
    ap.add_argument("--session", default="Qualifying")
    ap.add_argument("--drivers", nargs=2, default=["NOR", "LEC"])
    ap.add_argument("--minisectors", type=int, default=25)
    a = ap.parse_args()
    dA, dB = a.drivers

    skey = f1data.session_key(a.year, a.circuit, a.session)
    lapA, telA = get_lap(skey, dA)
    lapB, telB = get_lap(skey, dB)
    L_ref = 0.5 * (lap_length(telA, lapA["lap_duration"]) + lap_length(telB, lapB["lap_duration"]))
    grid = np.arange(0, L_ref, 5.0)
    A = resample(telA, L_ref, grid, lapA["lap_duration"])
    B = resample(telB, L_ref, grid, lapB["lap_duration"])
    delta = B["t"] - A["t"]
    pd.DataFrame({"distance": grid, f"t_{dA}": A["t"], f"t_{dB}": B["t"], "delta": delta,
                  f"v_{dA}": A["speed"], f"v_{dB}": B["speed"]}).to_csv(OUT / "aligned_laps.csv", index=False)

    print(f"{a.circuit} {a.year} {a.session}:  {dA} {lapA['lap_duration']:.3f}s  vs  "
          f"{dB} {lapB['lap_duration']:.3f}s   (gap {lapB['lap_duration']-lapA['lap_duration']:+.3f}s)")
    print(f"  top speed  {dA} {telA['speed'].max():.0f} km/h | {dB} {telB['speed'].max():.0f} km/h")
    for d, T in ((dA, A), (dB, B)):
        thr = 100 * np.mean(T["throttle"] >= 98)
        brk = 100 * np.mean(T["brake"] > 0)
        print(f"  {d}: full throttle {thr:.1f} % of distance, braking {brk:.1f} % of distance")

    # ---------------- mini-sectors
    edges = np.linspace(0, L_ref, a.minisectors + 1)
    ms = np.digitize(grid, edges[1:-1])
    rows = []
    for k in range(a.minisectors):
        idx = np.where(ms == k)[0]
        i0, i1 = idx[0], min(idx[-1] + 1, len(grid) - 1)
        tA = A["t"][i1] - A["t"][i0]
        tB = B["t"][i1] - B["t"][i0]
        rows.append({"minisector": k + 1, "start_m": edges[k], f"time_{dA}": tA,
                     f"time_{dB}": tB, "gain_for_A": tB - tA,
                     "faster": dA if tA < tB else dB})
    msdf = pd.DataFrame(rows)
    msdf.to_csv(OUT / "minisectors.csv", index=False)
    print(f"\n  mini-sectors won: {dA} {sum(msdf.faster == dA)} | {dB} {sum(msdf.faster == dB)}")
    top = msdf.reindex(msdf["gain_for_A"].abs().sort_values(ascending=False).index).head(5)
    print("  biggest swings:")
    for _, r in top.iterrows():
        print(f"    MS{r['minisector']:>2} @ {r['start_m']:5.0f} m: {r['faster']} faster by "
              f"{abs(r['gain_for_A']):.3f}s")

    # ---------------- corner table (min speed in each braking zone of A)
    on = A["brake"].to_numpy() > 50
    starts = np.where(~on[:-1] & on[1:])[0] + 1
    corners = []
    for n, s0 in enumerate(starts, 1):
        w = slice(s0, min(s0 + 60, len(grid)))          # next 300 m
        corners.append({"corner": f"B{n}", "brake_at_m": grid[s0],
                        f"vmin_{dA}": A["speed"][w].min(), f"vmin_{dB}": B["speed"][w].min()})
    cdf = pd.DataFrame(corners)
    if not cdf.empty:
        cdf["diff_kmh"] = cdf[f"vmin_{dA}"] - cdf[f"vmin_{dB}"]
        print("\n  minimum corner speeds [km/h]:")
        print(cdf.round(0).to_string(index=False))
        cdf.to_csv(OUT / "corner_speeds.csv", index=False)

    # ---------------- figure 1: stacked traces
    cA, cB = "tab:orange", "tab:red"
    fig, ax = plt.subplots(5, 1, figsize=(13, 12), sharex=True,
                           gridspec_kw={"height_ratios": [3, 1.6, 1.2, 0.8, 1]})
    ax[0].plot(grid, A["speed"], color=cA, label=dA)
    ax[0].plot(grid, B["speed"], color=cB, label=dB)
    ax[0].set_ylabel("Speed [km/h]")
    ax[0].legend(loc="lower right")
    ax[0].set_title(f"{a.circuit} {a.year} {a.session}: {dA} vs {dB}", weight="bold")
    ax[1].plot(grid, delta, color="k")
    ax[1].fill_between(grid, 0, delta, where=delta > 0, color=cA, alpha=0.3, label=f"{dA} ahead")
    ax[1].fill_between(grid, 0, delta, where=delta < 0, color=cB, alpha=0.3, label=f"{dB} ahead")
    ax[1].axhline(0, color="0.4", lw=0.8)
    ax[1].set_ylabel(f"Delta [s]\n{dB} - {dA}")
    ax[1].legend(loc="upper left", fontsize=8)
    ax[2].plot(grid, A["throttle"], color=cA)
    ax[2].plot(grid, B["throttle"], color=cB)
    ax[2].set_ylabel("Throttle [%]")
    ax[3].plot(grid, A["brake"] > 0, color=cA)
    ax[3].plot(grid, B["brake"] > 0, color=cB, ls="--")
    ax[3].set_ylabel("Brake")
    ax[3].set_yticks([0, 1], ["off", "on"])
    ax[4].step(grid, A["n_gear"], color=cA, where="mid")
    ax[4].step(grid, B["n_gear"], color=cB, where="mid", ls="--")
    ax[4].set_ylabel("Gear")
    ax[4].set_xlabel("Distance [m]")
    for e in edges[1:-1]:
        ax[1].axvline(e, color="0.85", lw=0.5, zorder=0)
    for axx in ax:
        axx.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "telemetry_comparison.png", dpi=150)

    # ---------------- figure 2: mini-sector dominance map
    xy = A[["x", "y"]].to_numpy() / 10
    pts = xy.reshape(-1, 1, 2)
    seg = np.concatenate([pts[:-1], pts[1:]], axis=1)
    owner = np.array([0 if msdf.loc[k, "faster"] == dA else 1 for k in ms[:-1]])
    fig2, ax2 = plt.subplots(figsize=(11, 7))
    ax2.plot(xy[:, 0], xy[:, 1], color="k", lw=12)
    lc = LineCollection(seg, colors=np.where(owner[:, None] == 0, [[1, .55, 0]], [[.85, .1, .1]]), lw=6)
    ax2.add_collection(lc)
    for k in range(a.minisectors):
        i = np.where(ms == k)[0][len(np.where(ms == k)[0]) // 2]
        ax2.annotate(str(k + 1), xy[i], fontsize=7, ha="center", va="center", color="white",
                     bbox=dict(boxstyle="circle,pad=0.15", fc="0.2", lw=0))
    ax2.plot([], [], color=cA, lw=6, label=f"{dA} faster ({sum(msdf.faster == dA)})")
    ax2.plot([], [], color=cB, lw=6, label=f"{dB} faster ({sum(msdf.faster == dB)})")
    ax2.legend(loc="upper left")
    ax2.set_aspect("equal")
    ax2.axis("off")
    ax2.set_title(f"Mini-sector dominance - {dA} vs {dB}", weight="bold")
    fig2.tight_layout()
    fig2.savefig(OUT / "minisector_map.png", dpi=150)
    print(f"\nSaved figures to {OUT}")


if __name__ == "__main__":
    main()
