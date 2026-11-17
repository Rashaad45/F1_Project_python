"""
Project A1 - Analyse F1 engine sound: spectrogram + RPM estimation
====================================================================

Pipeline
    1. Get a real RPM trace (OpenF1, Leclerc's Monza 2024 qualifying lap).
    2. Build an onboard-style engine sound from that trace (V6 four-stroke
       harmonics + exhaust "rasp" + broadband noise).  Because the true RPM
       is known, the estimator can be scored objectively.
       -> or pass your own recording:  --wav my_onboard.wav
    3. Short-Time Fourier Transform (STFT) -> spectrogram.
    4. Harmonic-sum RPM estimator over a grid of candidate RPMs.
    5. Median smoothing, gear-shift detection, error metrics, plots.

Key physics (4-stroke engine, N cylinders)
    crank rotation frequency   f_rot  = RPM / 60                 [Hz]
    each cylinder fires once every 2 revolutions, so
    firing frequency           f_fire = (RPM / 60) * (N / 2)      [Hz]
    For the F1 1.6 L V6 (N = 6):  f_fire = RPM / 20
        11 000 rpm -> 550 Hz,   12 500 rpm -> 625 Hz

Run
    python engine_sound_analysis.py                    # synthetic from real RPM
    python engine_sound_analysis.py --wav onboard.wav  # your own audio (Audacity export)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile
from scipy.ndimage import median_filter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import f1data  # noqa: E402

OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
FS = 22_050          # audio sample rate [Hz]
N_CYL = 6            # V6


# ---------------------------------------------------------------- 1. data
def load_real_rpm(year=2024, circuit="Monza", session="Qualifying", driver="LEC"):
    skey = f1data.session_key(year, circuit, session)
    lap = f1data.fastest_lap(skey, f1data.driver_number(skey, driver))
    car = f1data.lap_car_data(skey, lap)
    car = car[(car["t"] >= 0) & (car["t"] <= lap["lap_duration"])]
    return car["t"].to_numpy(), car["rpm"].to_numpy(float), car["n_gear"].to_numpy(), \
        f"{driver} {circuit} {year} {session} ({lap['lap_duration']:.3f}s)"


# ------------------------------------------------------- 2. synthesis
def synthesize_engine(t_rpm, rpm, fs=FS, seed=0):
    """Additive synthesis driven by an RPM trace.

    Instantaneous phase is the integral of instantaneous frequency:
        phi(t) = 2*pi * integral_0^t f(tau) dtau   (cumulative sum / fs)
    A sine with that phase glides smoothly as the RPM changes.
    Engine 'orders' are multiples of half the crank frequency; for a V6 the
    3rd order (= firing frequency) dominates.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(0, t_rpm[-1], 1 / fs)
    rpm_a = np.interp(t, t_rpm, rpm)                     # upsample 3.7 Hz -> 22 kHz
    rpm_a = np.convolve(rpm_a, np.ones(400) / 400, mode="same")  # ~18 ms smoothing
    f_rot = rpm_a / 60.0
    phase = 2 * np.pi * np.cumsum(f_rot) / fs

    # (order, amplitude): order k means frequency k * f_rot
    orders = [(1.5, 0.25), (3, 1.0), (4.5, 0.3), (9, 0.3), (12, 0.15)]
    y = sum(a * np.sin(k * phase + rng.uniform(0, 2 * np.pi)) for k, a in orders)
    # exhaust resonance: above ~11 500 rpm the 6th order (2 x firing) becomes
    # LOUDER than the firing frequency -> a loudest-peak picker doubles the RPM
    a6 = 0.5 + 1.0 / (1 + np.exp(-(rpm_a - 11500) / 150))
    y += a6 * np.sin(6 * phase + rng.uniform(0, 2 * np.pi))
    y *= 1 + 0.15 * np.sin(phase * 0.5)                  # cycle-to-cycle modulation
    # gearbox / tyre whine: a tone NOT locked to engine orders (~ road speed)
    whine_f = 300 + 900 * (rpm_a / rpm_a.max())
    y += 0.35 * np.sin(2 * np.pi * np.cumsum(whine_f) / fs)
    # wind noise: brown-ish (low-frequency heavy) + white noise
    brown = np.cumsum(rng.standard_normal(t.size)); brown -= np.convolve(brown, np.ones(2000) / 2000, "same")
    y += 0.8 * rng.standard_normal(t.size) + 0.02 * brown
    y /= np.max(np.abs(y))
    return t, y.astype(np.float32)


# ----------------------------------------------------------- 3. STFT
def spectrogram(y, fs=FS, nperseg=4096, hop=512):
    """|X(m, k)| = | sum_n x[n] w[n - mH] e^{-j 2 pi k n / N} |
    Hann window of N = 4096 samples -> frequency resolution fs/N = 5.4 Hz,
    time step H/fs = 23 ms."""
    f, t, Z = signal.stft(y, fs=fs, window="hann", nperseg=nperseg,
                          noverlap=nperseg - hop)
    return f, t, np.abs(Z)


# ---------------------------------------------------- 4. RPM estimator
def estimate_rpm(f, S, n_cyl=N_CYL, rpm_min=4000, rpm_max=13500, step=10,
                 harmonics=(1, 2, 3, 4)):
    """Harmonic-sum estimator.

    For each candidate RPM r on a grid and each time frame m:
        score(r, m) = sum_h  w_h * log(1 + |X(m, h * f_fire(r))|)
    with f_fire(r) = r/60 * n_cyl/2 and weights w_h = 1/h.
    The RPM with the highest score wins.  Summing harmonics makes the
    estimate robust to one harmonic being masked by noise and suppresses
    octave errors that a single 'loudest peak' picker suffers from.
    """
    cands = np.arange(rpm_min, rpm_max + step, step)
    logS = np.log1p(S / S.max() * 1e3)
    score = np.zeros((cands.size, S.shape[1]))
    for h in harmonics:
        fh = h * cands / 60 * n_cyl / 2
        idx = np.clip(np.round(fh / (f[1] - f[0])).astype(int), 0, f.size - 1)
        score += logS[idx, :] / h
    return cands[np.argmax(score, axis=0)]


def naive_peak_rpm(f, S, n_cyl=N_CYL, fmin=150, fmax=1400):
    """Baseline: take the loudest bin and assume it is the firing frequency."""
    band = (f >= fmin) & (f <= fmax)
    fpk = f[band][np.argmax(S[band, :], axis=0)]
    return fpk * 60 * 2 / n_cyl


def detect_upshifts(t, rpm, drop=450, window=0.25, rise=0.6):
    """Upshift signature: RPM was CLIMBING (driver on throttle) and then
    falls by more than `drop` rpm within `window` seconds.
    Requiring the prior climb rejects braking zones, where RPM also falls
    but was not rising beforehand."""
    dt = t[1] - t[0]
    k, kr = max(1, int(window / dt)), max(1, int(rise / dt))
    shifts, last = [], -1e9
    for i in range(kr, len(rpm) - k):
        falling = rpm[i + k] - rpm[i] < -drop
        climbing = rpm[i] - rpm[i - kr] > 150
        if falling and climbing and t[i] - last > 0.8:      # debounce
            shifts.append(t[i])
            last = t[i]
    return np.array(shifts)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", help="analyse your own engine recording instead")
    ap.add_argument("--cylinders", type=int, default=N_CYL)
    ap.add_argument("--driver", default="LEC")
    args = ap.parse_args()

    truth = None
    if args.wav:
        fs, y = wavfile.read(args.wav)
        y = y.astype(np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)            # stereo -> mono
        y /= np.max(np.abs(y))
        title = Path(args.wav).name
    else:
        t_rpm, rpm_true, gear, title = load_real_rpm(driver=args.driver)
        _, y = synthesize_engine(t_rpm, rpm_true)
        fs = FS
        wavfile.write(OUT / "synthetic_onboard.wav", fs, y)
        truth = (t_rpm, rpm_true, gear)
        print(f"Wrote {OUT/'synthetic_onboard.wav'}  (open it in Audacity!)")

    f, ts, S = spectrogram(y, fs)
    rpm_hs = median_filter(estimate_rpm(f, S, args.cylinders), size=9)
    rpm_naive = naive_peak_rpm(f, S, args.cylinders)
    shifts = detect_upshifts(ts, rpm_hs)

    # ------------------------------------------------------------ metrics
    if truth is not None:
        t_rpm, rpm_true, gear = truth
        ref = np.interp(ts, t_rpm, rpm_true)
        mask = ref > 4000
        for name, est in [("harmonic-sum", rpm_hs), ("naive peak", rpm_naive)]:
            err = est[mask] - ref[mask]
            print(f"{name:13s}  MAE = {np.mean(np.abs(err)):7.1f} rpm   "
                  f"MAPE = {100*np.mean(np.abs(err)/ref[mask]):5.2f} %   "
                  f"within 3 % = {100*np.mean(np.abs(err)/ref[mask] < 0.03):5.1f} %")
        true_shifts = t_rpm[1:][np.diff(gear) > 0]
        hits = sum(np.any(np.abs(true_shifts - s) < 0.7) for s in shifts)
        print(f"Upshifts in telemetry: {len(true_shifts)} | detected from audio: "
              f"{len(shifts)} | correct (within 0.7 s): {hits}")

    # -------------------------------------------------------------- plots
    fig, ax = plt.subplots(3, 1, figsize=(13, 11), sharex=True,
                           gridspec_kw={"height_ratios": [2.2, 1.4, 1]})
    SdB = 20 * np.log10(S + 1e-9)
    fmax = 2000
    sel = f <= fmax
    ax[0].pcolormesh(ts, f[sel], SdB[sel], shading="auto", cmap="magma",
                     vmin=SdB.max() - 70, vmax=SdB.max())
    ax[0].plot(ts, rpm_hs / 60 * args.cylinders / 2, "c", lw=1, label="estimated firing freq.")
    ax[0].set_ylabel("Frequency [Hz]")
    ax[0].set_title(f"Spectrogram - {title}")
    ax[0].legend(loc="upper right")

    ax[1].plot(ts, rpm_naive, ".", ms=2, color="0.6", label="naive loudest-peak")
    ax[1].plot(ts, rpm_hs, color="tab:red", lw=1.4, label="harmonic-sum estimate")
    if truth is not None:
        ax[1].plot(t_rpm, rpm_true, "k--", lw=1, label="telemetry RPM (truth)")
    for s in shifts:
        ax[1].axvline(s, color="tab:green", alpha=0.35, lw=0.8)
    ax[1].plot([], [], color="tab:green", label="upshift detected from audio")
    ax[1].set_ylim(3000, 14000)
    ax[1].set_ylabel("RPM")
    ax[1].legend(loc="lower right", fontsize=8)

    if truth is not None:
        ax[2].step(t_rpm, gear, where="post", color="tab:blue")
        for s in shifts:
            ax[2].axvline(s, color="tab:green", alpha=0.35, lw=0.8)
        ax[2].set_ylabel("Gear")
    else:
        ax[2].plot(ts, np.gradient(rpm_hs, ts), color="tab:purple")
        ax[2].set_ylabel("dRPM/dt")
    ax[2].set_xlabel("Time [s]")
    for a in ax:
        a.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "engine_spectrogram_rpm.png", dpi=150)
    print(f"Saved {OUT/'engine_spectrogram_rpm.png'}")


if __name__ == "__main__":
    main()
