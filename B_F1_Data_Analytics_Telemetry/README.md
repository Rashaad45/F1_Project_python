# Folder B: F1 Data Analytics (Telemetry, Beginner to Advanced)

These projects come from the post *"three projects for different skill levels"*, built for an engineering or data-analysis portfolio.

| # | Level | Project | Question answered | Headline result (Monza 2024) |
|---|-------|---------|-------------------|-------------------------------|
| 01 | Beginner | Circuit mapping and speed visualisation | How fast do F1 cars really go around a circuit? | Speed/gear-coloured track map; 259.5 km/h average, 75 % of the lap at full throttle |
| 02 | Intermediate | Tyre degradation analysis | Why did a tyre strategy cost a driver time? | Hard tyre +0.045 s/lap (fuel-corrected); Leclerc's 1-stop beat Piastri's 2-stop by 2.6 s |
| 03 | Advanced | Telemetry comparison | Where does one driver gain time on another? | Distance-aligned delta: NOR +0.134 s over LEC, gained in braking zones and corner minimum speed |

## Run
```bash
pip install -r requirements.txt
cd 01_circuit_mapping      && python circuit_mapping.py       # --circuit Silverstone --driver HAM
cd 02_tyre_degradation     && python tyre_degradation.py      # --pair LEC PIA
cd 03_telemetry_comparison && python telemetry_comparison.py  # --drivers NOR LEC
```

## Data
Same approach as Folder A: `f1data.py` reads the OpenF1 API and caches every request as CSV in `data/`. The posts mention FastF1. Its repository is cloned in `../external_repos/Fast-F1`, and its `examples/` folder is a good next step if you have an F1 account.
