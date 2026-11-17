"""Run all six projects in order (first run downloads data from OpenF1 and caches it in */data)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = [
    "A_F1_Engineering_Physics_and_Signal_Processing/01_engine_sound_analysis/engine_sound_analysis.py",
    "A_F1_Engineering_Physics_and_Signal_Processing/02_delta_time_indicator/delta_time_indicator.py",
    "A_F1_Engineering_Physics_and_Signal_Processing/03_braking_distance/braking_distance.py",
    "B_F1_Data_Analytics_Telemetry/01_circuit_mapping/circuit_mapping.py",
    "B_F1_Data_Analytics_Telemetry/02_tyre_degradation/tyre_degradation.py",
    "B_F1_Data_Analytics_Telemetry/03_telemetry_comparison/telemetry_comparison.py",
]
for s in SCRIPTS:
    p = ROOT / s
    print("\n" + "=" * 80 + f"\n{p.parent.name}\n" + "=" * 80, flush=True)
    r = subprocess.run([sys.executable, p.name], cwd=p.parent)
    if r.returncode:
        sys.exit(f"{s} failed")
print("\nAll projects finished - see each project's outputs/ folder.")
