"""
Project B2 - Why did a tyre strategy cost a driver time?
Tyre degradation analysis (Intermediate)
=========================================================

Data: every lap + every tyre stint of a race (default Monza 2024, which
Leclerc won on a ONE-stop against the TWO-stopping McLarens).

Pipeline
    1. Join laps with stints -> compound and tyre age for each lap
           tyre_age = tyre_age_at_start + (lap_number - lap_start)
    2. Cleaning (only representative 'green-flag' laps are kept)
           - drop lap 1, pit-out laps and in-laps
           - drop neutralised laps: field median of that lap > 105 % of race median
           - drop per-driver outliers: > 3 MAD above the stint median
    3. Fuel correction.  The car burns ~FUEL_KG kg over the race and each kg
       costs ~0.03 s per lap, so heavier early laps look slower even with new
       tyres.  corrected_t = t - 0.03 * fuel_remaining(lap)
    4. Ordinary least squares per stint:  t_corr = b0 + b1 * tyre_age
           b1 = degradation [s/lap];  95 % CI = b1 +/- t_{0.975, n-2} * SE(b1)
    5. Strategy story: gap chart between two drivers built from lap start
       timestamps; pit stops marked.

Run
    python tyre_degradation.py
    python tyre_degradation.py --year 2024 --circuit Silverstone --pair HAM VER
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import f1data  # noqa: E402

OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
COMPOUND_COLOURS = {"SOFT": "#e10600", "MEDIUM": "#f5c400", "HARD": "#9a9a9a",
                    "INTERMEDIATE": "#43b02a", "WET": "#0067ad"}
FUEL_KG = 105.0          # fuel burnt over a race distance (approx.)
SEC_PER_KG = 0.03        # lap-time sensitivity to mass (rule of thumb)


def build_dataset(skey: int) -> pd.DataFrame:
    laps = f1data.laps(skey)
    st = f1data.stints(skey)
    drv = f1data.drivers(skey)[["driver_number", "name_acronym"]].drop_duplicates()

    # attach stint info to every lap (a lap belongs to the stint whose
    # [lap_start, lap_end] interval contains it)
    m = laps.merge(st, on="driver_number")
    m = m[(m["lap_number"] >= m["lap_start"]) & (m["lap_number"] <= m["lap_end"])]
    m = m.merge(drv, on="driver_number")
    m["tyre_age"] = m["tyre_age_at_start"] + (m["lap_number"] - m["lap_start"])
    last_stint = m.groupby("driver_number")["stint_number"].transform("max")
    m["is_in_lap"] = (m["lap_number"] == m["lap_end"]) & (m["stint_number"] < last_stint)
    total_laps = int(m["lap_number"].max())
    m["fuel_remaining_kg"] = FUEL_KG * (1 - (m["lap_number"] - 1) / total_laps)
    m["lap_time_corr"] = m["lap_duration"] - SEC_PER_KG * m["fuel_remaining_kg"]
    return m.sort_values(["name_acronym", "lap_number"]).reset_index(drop=True)


def clean(m: pd.DataFrame) -> pd.DataFrame:
    c = m.dropna(subset=["lap_duration"])
    c = c[(c["lap_number"] > 1) & ~c["is_pit_out_lap"].astype(bool) & ~c["is_in_lap"]]
    lap_med = c.groupby("lap_number")["lap_duration"].median()
    green = lap_med[lap_med < 1.05 * lap_med.median()].index
    c = c[c["lap_number"].isin(green)]
    # robust outlier filter: median absolute deviation (MAD) per stint
    g = c.groupby(["name_acronym", "stint_number"])["lap_duration"]
    med = g.transform("median")
    mad = g.transform(lambda s: np.median(np.abs(s - s.median())) + 1e-3)
    return c[c["lap_duration"] < med + 3 * 1.4826 * mad]


def stint_regressions(c: pd.DataFrame, min_laps=8) -> pd.DataFrame:
    rows = []
    for (d, s), g in c.groupby(["name_acronym", "stint_number"]):
        if len(g) < min_laps:
            continue
        r = stats.linregress(g["tyre_age"], g["lap_time_corr"])
        tcrit = stats.t.ppf(0.975, len(g) - 2)
        rows.append({"driver": d, "stint": s, "compound": g["compound"].iloc[0],
                     "laps": len(g), "age_from": g["tyre_age"].min(),
                     "age_to": g["tyre_age"].max(),
                     "deg_s_per_lap": r.slope, "ci95": tcrit * r.stderr,
                     "intercept": r.intercept, "r2": r.rvalue ** 2,
                     "median_corr_time": g["lap_time_corr"].median()})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--circuit", default="Monza")
    ap.add_argument("--pair", nargs=2, default=["LEC", "PIA"],
                    help="two drivers for the strategy gap chart")
    a = ap.parse_args()

    skey = f1data.session_key(a.year, a.circuit, "Race")
    m = build_dataset(skey)
    c = clean(m)
    m.to_csv(OUT / "race_laps_with_tyres.csv", index=False)
    print(f"{a.circuit} {a.year} race: {len(m)} laps total, {len(c)} representative laps kept")

    reg = stint_regressions(c)
    reg.to_csv(OUT / "stint_degradation.csv", index=False)
    print("\nDegradation per stint (fuel-corrected, s/lap, 95 % CI):")
    print(reg.sort_values(["compound", "deg_s_per_lap"])[
        ["driver", "stint", "compound", "laps", "deg_s_per_lap", "ci95", "r2"]
    ].round(3).to_string(index=False))

    # pooled per-compound model with a separate intercept per driver-stint
    # (removes car pace differences, leaves the shared tyre-age slope)
    print("\nPooled degradation by compound (driver-stint fixed effects):")
    pooled = {}
    for comp, g in c.groupby("compound"):
        if len(g) < 20:                       # too few laps for a reliable slope
            continue
        g = g.copy()
        key = g["name_acronym"] + "_" + g["stint_number"].astype(str)
        g["t_dm"] = g["lap_time_corr"] - g.groupby(key)["lap_time_corr"].transform("mean")
        g["a_dm"] = g["tyre_age"] - g.groupby(key)["tyre_age"].transform("mean")
        slope = np.sum(g["a_dm"] * g["t_dm"]) / np.sum(g["a_dm"] ** 2)
        resid = g["t_dm"] - slope * g["a_dm"]
        se = np.sqrt(np.sum(resid ** 2) / (len(g) - key.nunique() - 1) / np.sum(g["a_dm"] ** 2))
        pooled[comp] = slope
        print(f"  {comp:7s}: {slope:+.3f} +/- {1.96*se:.3f} s/lap   ({len(g)} laps)")

    # ------------------------------------------------ figure 1: scatter + fits
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5))
    for comp, g in c.groupby("compound"):
        if comp not in pooled:
            continue
        col = COMPOUND_COLOURS.get(comp, "k")
        ax[0].scatter(g["tyre_age"], g["lap_time_corr"], s=10, alpha=0.45, color=col,
                      edgecolor="k", linewidth=0.2, label=f"{comp}  ({pooled[comp]:+.3f} s/lap)")
    for _, r in reg.iterrows():
        x = np.array([r["age_from"], r["age_to"]])
        ax[0].plot(x, r["intercept"] + r["deg_s_per_lap"] * x,
                   color=COMPOUND_COLOURS.get(r["compound"], "k"), lw=0.8, alpha=0.7)
    ax[0].set(xlabel="Tyre age [laps]", ylabel="Fuel-corrected lap time [s]",
              title="Lap time vs tyre age (lines = per-stint OLS fits)")
    lo, hi = np.percentile(c["lap_time_corr"], [1, 99.5])
    ax[0].set_ylim(lo - 0.3, hi + 0.3)
    ax[0].legend(fontsize=8)

    reg = reg[reg["compound"].isin(pooled)]
    order = reg.groupby("compound")["deg_s_per_lap"].median().sort_values().index
    data = [reg.loc[reg["compound"] == k, "deg_s_per_lap"] for k in order]
    bp = ax[1].boxplot(data, patch_artist=True)
    ax[1].set_xticks(range(1, len(order) + 1), list(order))
    for patch, k in zip(bp["boxes"], order):
        patch.set_facecolor(COMPOUND_COLOURS.get(k, "w"))
    ax[1].axhline(0, color="k", lw=0.7)
    ax[1].set(ylabel="Degradation [s/lap]", title="Distribution of stint degradation rates")
    for axx in ax:
        axx.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "degradation_scatter.png", dpi=150)

    # ------------------------------------------------ figure 2: strategy chart
    st = f1data.stints(skey).merge(
        f1data.drivers(skey)[["driver_number", "name_acronym"]].drop_duplicates(), on="driver_number")
    finish = m.groupby("name_acronym")["lap_number"].max().sort_values(ascending=True)
    fig2, ax2 = plt.subplots(figsize=(12, 7))
    for y, d in enumerate(finish.index):
        for _, s in st[st["name_acronym"] == d].iterrows():
            ax2.barh(y, s["lap_end"] - s["lap_start"] + 1, left=s["lap_start"] - 1,
                     color=COMPOUND_COLOURS.get(s["compound"], "w"), edgecolor="k")
    ax2.set_yticks(range(len(finish)), finish.index)
    ax2.set(xlabel="Lap", title=f"Tyre strategies - {a.circuit} {a.year}")
    handles = [plt.Rectangle((0, 0), 1, 1, color=v) for k, v in COMPOUND_COLOURS.items()
               if k in set(st["compound"])]
    ax2.legend(handles, [k for k in COMPOUND_COLOURS if k in set(st["compound"])], loc="lower right")
    fig2.tight_layout()
    fig2.savefig(OUT / "strategy_chart.png", dpi=150)

    # ------------------------------------------------ figure 3: gap chart
    d1, d2 = a.pair
    t1 = m[m["name_acronym"] == d1].set_index("lap_number")["date_start"]
    t2 = m[m["name_acronym"] == d2].set_index("lap_number")["date_start"]
    gap = (t2 - t1).dt.total_seconds().dropna()        # + = d1 ahead
    # add the chequered flag: finish time = start of last lap + its duration
    def finish(d):
        last = m[m["name_acronym"] == d].sort_values("lap_number").iloc[-1]
        return last["date_start"] + pd.Timedelta(seconds=last["lap_duration"]), last["lap_number"]
    (f1, n1), (f2, _) = finish(d1), finish(d2)
    gap.loc[n1 + 1] = (f2 - f1).total_seconds()
    fig3, ax3 = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax3[0].plot(gap.index, gap.values, color="k")
    ax3[0].axhline(0, color="0.5", lw=0.8)
    for d, col in ((d1, "tab:red"), (d2, "tab:orange")):
        pits = st[(st["name_acronym"] == d) & (st["stint_number"] > 1)]["lap_start"]
        for p in pits:
            ax3[0].axvline(p, color=col, ls="--", lw=1)
        ax3[0].plot([], [], color=col, ls="--", label=f"{d} pit stop")
    ax3[0].set(ylabel=f"Gap [s]  (+ = {d1} ahead)",
               title=f"Strategy battle: {d1} vs {d2} - gap at the start of each lap")
    ax3[0].legend()
    for d, col in ((d1, "tab:red"), (d2, "tab:orange")):
        g = c[c["name_acronym"] == d]
        ax3[1].plot(g["lap_number"], g["lap_time_corr"], "o-", ms=3, color=col, label=d)
    ax3[1].set(xlabel="Lap", ylabel="Fuel-corrected lap time [s]",
               title="Race pace (representative laps only)")
    ax3[1].legend()
    for axx in ax3:
        axx.grid(alpha=0.3)
    fig3.tight_layout()
    fig3.savefig(OUT / "strategy_gap.png", dpi=150)

    # strategy summary + how much faster the 2-stopper's fresher tyres were
    stops = {d: int(st[st["name_acronym"] == d]["stint_number"].max() - 1) for d in (d1, d2)}
    pace = {d: c[c["name_acronym"] == d]["lap_time_corr"].median() for d in (d1, d2)}
    print(f"\n{d1}: {stops[d1]} stop(s), median corrected pace {pace[d1]:.3f} s")
    print(f"{d2}: {stops[d2]} stop(s), median corrected pace {pace[d2]:.3f} s")
    print(f"At the flag {d1} is ahead of {d2} by {gap.iloc[-1]:+.2f} s "
          f"(largest {d1} lead {gap.max():.2f} s, largest {d2} lead {-gap.min():.2f} s)")
    print(f"Saved figures to {OUT}")


if __name__ == "__main__":
    main()
