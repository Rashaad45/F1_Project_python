# Folder A: F1 Engineering (Physics and Signal Processing)

These projects come from the post *"Formula 1 engineering is more accessible than you might think"*. Each one turns an engineering idea into a measurable result on real F1 data.

| # | Project | Core skill | Headline result (Monza 2024) |
|---|---------|-----------|-------------------------------|
| 01 | Engine-sound spectrogram and RPM estimation | DSP: STFT, harmonic-sum pitch tracking | RPM recovered from audio with 0.12 % error (naive peak picking: 35 %) |
| 02 | Delta-time indicator / timing screen | Data analysis, conditional logic, Excel automation | Purple/green/yellow sector screen + theoretical best lap 79.055 s |
| 03 | Braking distance: d = v^2/2a to aero model | Physics modelling, least squares, ODE solving | Aero model fitted on telemetry predicts braking distance to 3 m RMSE (constant-g: 29 m) |

## Run
```bash
pip install -r requirements.txt
cd 01_engine_sound_analysis && python engine_sound_analysis.py      # or --wav your_onboard.wav
cd 02_delta_time_indicator  && python delta_time_indicator.py       # --circuit Silverstone --ref NOR
cd 03_braking_distance      && python braking_distance.py           # --speed 330 --driver LEC
```
Figures, CSVs, the WAV and the Excel file are written to each project's `outputs/` folder.

## Data
`f1data.py` downloads from the free OpenF1 API (https://openf1.org) and caches every request as CSV in `data/`. That CSV cache is the project dataset, and it lets the scripts run offline. FastF1 now needs an F1 account to read the live-timing feed, which is why OpenF1 is used here. Both repos are cloned in `../external_repos/` for reference.
