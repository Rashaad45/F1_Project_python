"""
Project A2 - Delta-time indicator (sector timing screen)
=========================================================

Compares every driver's sector times against a REFERENCE lap (default: the
pole lap) and colours each sector like the official F1 timing screen:

    PURPLE  overall fastest sector of the session
    GREEN   driver's personal best sector
    YELLOW  slower than the driver's personal best

Outputs
    - coloured table in the terminal (ANSI escape codes)
    - outputs/timing_screen.png      matplotlib dashboard
    - outputs/timing_screen.xlsx     Excel version with the same colour logic
    - outputs/delta_vs_reference.png cumulative delta at each sector line

Maths
    delta_i = t_i(driver) - t_i(reference)       (negative = faster)
    cumulative delta after sector k:  D_k = sum_{i<=k} delta_i
    theoretical best lap = S1_min + S2_min + S3_min  (best sectors may come
    from different laps)

Run
    python delta_time_indicator.py
    python delta_time_indicator.py --year 2024 --circuit Silverstone --session Qualifying --ref NOR
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import f1data  # noqa: E402

OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
SECT = ["duration_sector_1", "duration_sector_2", "duration_sector_3"]
COLOURS = {"purple": "#9b30ff", "green": "#22c55e", "yellow": "#facc15", "none": "#d1d5db"}
ANSI = {"purple": "\033[95m", "green": "\033[92m", "yellow": "\033[93m", "none": "\033[0m"}
RESET = "\033[0m"


def build_table(skey: int, ref_acr: str | None):
    laps = f1data.laps(skey)
    drv = f1data.drivers(skey)[["driver_number", "name_acronym", "team_colour"]]
    laps = laps.merge(drv.drop_duplicates("driver_number"), on="driver_number")

    # keep only complete, valid laps (all three sectors timed, not out-laps)
    valid = laps.dropna(subset=SECT + ["lap_duration"])
    valid = valid[~valid["is_pit_out_lap"].astype(bool)]
    # remove obvious non-push laps (cool-down laps): >107 % of the fastest lap
    valid = valid[valid["lap_duration"] < 1.07 * valid["lap_duration"].min()]

    overall_best = valid[SECT].min()                         # purple thresholds
    personal_best = valid.groupby("name_acronym")[SECT].min()  # green thresholds

    # each driver's fastest lap is the one shown on the timing screen
    best = valid.loc[valid.groupby("name_acronym")["lap_duration"].idxmin()]
    best = best.sort_values("lap_duration").reset_index(drop=True)

    ref = best.iloc[0] if ref_acr is None else best[best["name_acronym"] == ref_acr].iloc[0]

    rows = []
    for _, r in best.iterrows():
        row = {"Pos": len(rows) + 1, "Driver": r["name_acronym"], "Lap": r["lap_duration"]}
        for i, s in enumerate(SECT, 1):
            t = r[s]
            # --- conditional logic (the heart of the project) ---
            if np.isclose(t, overall_best[s]):
                colour = "purple"
            elif np.isclose(t, personal_best.loc[r["name_acronym"], s]):
                colour = "green"
            else:
                colour = "yellow"
            row[f"S{i}"] = t
            row[f"S{i}_delta"] = t - ref[s]
            row[f"S{i}_colour"] = colour
        row["Gap"] = r["lap_duration"] - ref["lap_duration"]
        row["Ideal"] = personal_best.loc[r["name_acronym"]].sum()
        rows.append(row)
    table = pd.DataFrame(rows)
    return table, ref, overall_best


def print_table(table, ref):
    print(f"\nReference lap: {ref['name_acronym']}  {ref['lap_duration']:.3f}s\n")
    print(f"{'Pos':>3} {'Drv':<4} {'S1':>15} {'S2':>15} {'S3':>15} {'Lap':>9} {'Gap':>8}")
    for _, r in table.iterrows():
        cells = []
        for i in (1, 2, 3):
            c = r[f"S{i}_colour"]
            d = r[f"S{i}_delta"]
            cells.append(f"{ANSI[c]}{r[f'S{i}']:6.3f}({d:+.3f}){RESET}")
        print(f"{r['Pos']:>3} {r['Driver']:<4} {' '.join(cells)} {r['Lap']:9.3f} {r['Gap']:+8.3f}")
    print(f"\n{ANSI['purple']}purple{RESET}=session best  {ANSI['green']}green{RESET}=personal best"
          f"  {ANSI['yellow']}yellow{RESET}=slower than personal best;  (delta vs reference)")


def plot_timing_screen(table, ref, title):
    n = len(table)
    fig, ax = plt.subplots(figsize=(11, 0.42 * n + 1.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(-n, 1.2)
    ax.axis("off")
    headers = ["P", "Driver", "Sector 1", "Sector 2", "Sector 3", "Lap", "Gap", "Ideal"]
    xs = [0.2, 0.8, 2.0, 3.6, 5.2, 6.8, 8.0, 9.1]
    for x, h in zip(xs, headers):
        ax.text(x, 0.5, h, weight="bold", va="center")
    for j, r in table.iterrows():
        y = -j - 0.3
        ax.text(xs[0], y, r["Pos"], va="center")
        ax.text(xs[1], y, r["Driver"], va="center", weight="bold")
        for i in (1, 2, 3):
            ax.add_patch(plt.Rectangle((xs[i + 1] - 0.1, y - 0.38), 1.45, 0.76,
                                       color=COLOURS[r[f"S{i}_colour"]], alpha=0.9))
            ax.text(xs[i + 1], y, f"{r[f'S{i}']:.3f} ({r[f'S{i}_delta']:+.3f})",
                    va="center", fontsize=8.5,
                    color="white" if r[f"S{i}_colour"] == "purple" else "black")
        ax.text(xs[5], y, f"{r['Lap']:.3f}", va="center")
        ax.text(xs[6], y, "REF" if r["Driver"] == ref["name_acronym"] else f"{r['Gap']:+.3f}",
                va="center", color="tab:red" if r["Gap"] > 0 else "tab:green")
        ax.text(xs[7], y, f"{r['Ideal']:.3f}", va="center", color="0.4")
    ax.set_title(title, loc="left", weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "timing_screen.png", dpi=150)


def plot_cumulative_delta(table, ref, top=8):
    fig, ax = plt.subplots(figsize=(9, 5))
    for _, r in table.head(top).iterrows():
        d = np.cumsum([0, r["S1_delta"], r["S2_delta"], r["S3_delta"]])
        ax.plot([0, 1, 2, 3], d, marker="o", label=r["Driver"])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks([0, 1, 2, 3], ["Start", "End S1", "End S2", "Finish"])
    ax.set_ylabel(f"Cumulative delta to {ref['name_acronym']} [s]  (+ = slower)")
    ax.set_title("Where is the time lost? Cumulative delta at each timing line")
    ax.grid(alpha=0.3)
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "delta_vs_reference.png", dpi=150)


def export_excel(table):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Timing"
    head = ["Pos", "Driver", "S1", "dS1", "S2", "dS2", "S3", "dS3", "Lap", "Gap", "Ideal"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    for _, r in table.iterrows():
        ws.append([int(r["Pos"]), r["Driver"], r["S1"], r["S1_delta"], r["S2"], r["S2_delta"],
                   r["S3"], r["S3_delta"], r["Lap"], r["Gap"], r["Ideal"]])
        row = ws.max_row
        for i, col in zip((1, 2, 3), ("C", "E", "G")):
            hexcol = COLOURS[r[f"S{i}_colour"]].lstrip("#").upper()
            ws[f"{col}{row}"].fill = PatternFill("solid", fgColor=hexcol)
    for col in "CDEFGHIJK":
        for cell in ws[col][1:]:
            cell.number_format = "0.000" if col in "CEGIK" else "+0.000;-0.000;0.000"
    wb.save(OUT / "timing_screen.xlsx")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--circuit", default="Monza")
    ap.add_argument("--session", default="Qualifying")
    ap.add_argument("--ref", default=None, help="driver acronym for the reference lap")
    a = ap.parse_args()

    skey = f1data.session_key(a.year, a.circuit, a.session)
    table, ref, best = build_table(skey, a.ref)
    print_table(table, ref)
    print(f"\nTheoretical best lap of session: {best.sum():.3f}s "
          f"(S1 {best.iloc[0]:.3f} + S2 {best.iloc[1]:.3f} + S3 {best.iloc[2]:.3f})")
    title = f"{a.circuit} {a.year} {a.session} - best laps vs {ref['name_acronym']}"
    plot_timing_screen(table, ref, title)
    plot_cumulative_delta(table, ref)
    export_excel(table)
    print(f"Saved timing_screen.png, delta_vs_reference.png, timing_screen.xlsx in {OUT}")


if __name__ == "__main__":
    main()
