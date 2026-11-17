"""
Project B1 - How fast do F1 cars really go around a circuit?
Circuit mapping and speed visualisation (Beginner)
==============================================================

Builds a track map of a qualifying lap from the recorded x/y car position,
colours it by speed and marks high-speed sections and braking zones.

Steps
    1. Fastest qualifying lap of a driver -> position (x, y) + car data
       (speed, throttle, brake, gear), merged on nearest timestamp.
    2. Rotate the coordinates so the map is drawn the 'usual' way up:
           [x']   [cos t  -sin t] [x]
           [y'] = [sin t   cos t] [y]
    3. Turn the polyline into segments  (p_i, p_{i+1})  and colour every
       segment by its speed with matplotlib's LineCollection.
    4. Markers: top-speed point, brake-on points (brake 0 -> 100) and
       'full-throttle' share of the lap.
    5. A second figure coloured by gear.

Run
    python circuit_mapping.py
    python circuit_mapping.py --year 2024 --circuit Silverstone --driver HAM
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import f1data  # noqa: E402

OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)


def rotate(xy: np.ndarray, angle_deg: float) -> np.ndarray:
    t = np.deg2rad(angle_deg)
    R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    return xy @ R.T


def best_rotation(xy: np.ndarray) -> float:
    """Principal-axis alignment: rotate so the longest extent of the track
    is horizontal.  The covariance matrix's main eigenvector gives the
    direction of largest spread (this is PCA in 2-D)."""
    c = np.cov((xy - xy.mean(0)).T)
    w, V = np.linalg.eigh(c)
    major = V[:, np.argmax(w)]
    return -np.degrees(np.arctan2(major[1], major[0]))


def segments(xy: np.ndarray) -> np.ndarray:
    pts = xy.reshape(-1, 1, 2)
    return np.concatenate([pts[:-1], pts[1:]], axis=1)   # shape (N-1, 2, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--circuit", default="Monza")
    ap.add_argument("--session", default="Qualifying")
    ap.add_argument("--driver", default="NOR")
    a = ap.parse_args()

    skey = f1data.session_key(a.year, a.circuit, a.session)
    lap = f1data.fastest_lap(skey, f1data.driver_number(skey, a.driver))
    tel = f1data.lap_telemetry(skey, lap).dropna(subset=["x", "y"])
    tel.to_csv(OUT / "lap_telemetry.csv", index=False)

    xy = tel[["x", "y"]].to_numpy(float) / 10.0          # OpenF1 units: 1/10 m
    xy = rotate(xy, best_rotation(xy))
    speed = tel["speed"].to_numpy(float)
    seg = segments(xy)
    seg_speed = 0.5 * (speed[:-1] + speed[1:])

    # ---------------- statistics
    i_max = int(np.argmax(speed))
    brake = tel["brake"].to_numpy() > 0
    brake_on = np.where(~brake[:-1] & brake[1:])[0] + 1
    full_thr = tel["throttle"].to_numpy() >= 98
    dt = np.diff(tel["t"].to_numpy(), append=tel["t"].iloc[-1])
    lap_len = tel["distance"].iloc[-1]
    print(f"{a.driver} {a.circuit} {a.year} {a.session} - lap {lap['lap_duration']:.3f}s")
    print(f"  lap length (integrated)  : {lap_len:7.0f} m")
    print(f"  average speed            : {lap_len/lap['lap_duration']*3.6:7.1f} km/h")
    print(f"  top speed                : {speed.max():7.0f} km/h at {tel['distance'].iloc[i_max]:.0f} m")
    print(f"  minimum speed            : {speed.min():7.0f} km/h")
    print(f"  full throttle            : {100*dt[full_thr].sum()/dt.sum():7.1f} % of lap time")
    print(f"  braking zones            : {len(brake_on)}")

    # ---------------- figure 1: speed map
    fig, ax = plt.subplots(figsize=(12, 7.5))
    ax.plot(xy[:, 0], xy[:, 1], color="black", lw=14, zorder=0)   # track 'tarmac'
    norm = plt.Normalize(speed.min(), speed.max())
    lc = LineCollection(seg, cmap="plasma", norm=norm, lw=6, zorder=1)
    lc.set_array(seg_speed)
    ax.add_collection(lc)
    cb = fig.colorbar(lc, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("Speed [km/h]")

    ax.scatter(*xy[i_max], s=260, marker="*", color="cyan", edgecolor="k", zorder=3,
               label=f"top speed {speed[i_max]:.0f} km/h")
    ax.scatter(xy[brake_on, 0], xy[brake_on, 1], s=110, marker="v", color="red",
               edgecolor="white", zorder=3, label="brake applied (entry km/h)")
    for k, i in enumerate(brake_on, 1):
        ax.annotate(f"B{k}\n{speed[i - 1]:.0f}", xy[i], xytext=(12, 12),
                    textcoords="offset points", fontsize=8, color="darkred")
    ax.scatter(*xy[0], s=120, marker="s", color="white", edgecolor="k", zorder=3,
               label="start / finish")
    ax.set_aspect("equal")
    ax.axis("off")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title(f"{a.circuit} {a.year} {a.session} - {a.driver} {lap['lap_duration']:.3f}s\n"
                 f"track coloured by speed", weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "circuit_speed_map.png", dpi=150)

    # ---------------- figure 2: gear map
    fig2, ax2 = plt.subplots(figsize=(12, 7.5))
    gear = tel["n_gear"].to_numpy()
    cmap = plt.get_cmap("Paired", 8)
    lc2 = LineCollection(seg, cmap=cmap, norm=plt.Normalize(0.5, 8.5), lw=6)
    lc2.set_array(gear[:-1].astype(float))
    ax2.add_collection(lc2)
    cb2 = fig2.colorbar(lc2, ax=ax2, ticks=range(1, 9), shrink=0.8)
    cb2.set_label("Gear")
    ax2.autoscale()
    ax2.set_aspect("equal")
    ax2.axis("off")
    ax2.set_title(f"Gear used around {a.circuit} - {a.driver}", weight="bold")
    fig2.tight_layout()
    fig2.savefig(OUT / "circuit_gear_map.png", dpi=150)

    # ---------------- figure 3: speed trace vs distance
    fig3, ax3 = plt.subplots(figsize=(12, 4))
    ax3.plot(tel["distance"], speed, color="tab:purple")
    ax3.fill_between(tel["distance"], 0, 360, where=brake, color="red", alpha=0.15,
                     step="mid", label="braking")
    ax3.set(xlabel="Distance [m]", ylabel="Speed [km/h]", ylim=(0, 360),
            title="Speed trace with braking zones")
    ax3.grid(alpha=0.3)
    ax3.legend()
    fig3.tight_layout()
    fig3.savefig(OUT / "speed_trace.png", dpi=150)
    print(f"Saved maps to {OUT}")


if __name__ == "__main__":
    main()
