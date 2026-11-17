"""
f1data.py - small, cached client for the free OpenF1 API (https://openf1.org).

Why OpenF1 and not FastF1?
    FastF1 (cloned in ../external_repos/Fast-F1) reads the official F1 live-timing
    feed. Since 2025 that feed requires an F1 account login, so without credentials
    FastF1 returns empty data. OpenF1 (cloned in ../external_repos/openf1) serves the
    same underlying timing/telemetry over a free public REST API, so these projects
    use it as the data source. Every request is cached as a CSV in ./data, so after
    the first run everything works offline and the CSVs form the project dataset.

Endpoints used
    sessions  -> session_key for a (year, circuit, session)
    laps      -> lap & sector durations per driver
    stints    -> tyre compound and tyre age per stint
    car_data  -> ~3.7 Hz telemetry: speed, rpm, throttle, brake, gear, DRS
    location  -> ~3.7 Hz car x/y/z position on track (1/10 m units)
    drivers   -> driver number <-> acronym / team / colour
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE_URL = "https://api.openf1.org/v1"
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _get(endpoint: str, params: dict, cache_name: str) -> pd.DataFrame:
    """GET an OpenF1 endpoint and cache the result as CSV."""
    path = DATA_DIR / f"{cache_name}.csv"
    if path.exists():
        return pd.read_csv(path)

    # OpenF1 uses operators inside the key, e.g. "date>=" -> encode keys manually
    query = "&".join(
        f"{k}={urllib.parse.quote(str(v), safe=':+-.')}" if not k[-1] in "<>="
        else f"{k}{urllib.parse.quote(str(v), safe=':+-.')}"
        for k, v in params.items()
    )
    url = f"{BASE_URL}/{endpoint}?{query}"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                rows = json.loads(r.read().decode())
            break
        except Exception as exc:  # rate limit (429) or network hiccup -> back off
            if attempt == 4:
                raise RuntimeError(f"OpenF1 request failed: {url}") from exc
            time.sleep(2 ** attempt)

    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return df


# ----------------------------------------------------------------- sessions
def session_key(year: int, circuit: str, session_name: str) -> int:
    """e.g. session_key(2024, 'Monza', 'Qualifying') -> 9586"""
    df = _get("sessions", {"year": year, "circuit_short_name": circuit,
                           "session_name": session_name},
              f"sessions_{year}_{circuit}_{session_name}".replace(" ", ""))
    if df.empty:
        raise ValueError(f"No session found for {year} {circuit} {session_name}")
    return int(df["session_key"].iloc[0])


def drivers(skey: int) -> pd.DataFrame:
    return _get("drivers", {"session_key": skey}, f"drivers_{skey}")


def driver_number(skey: int, acronym: str) -> int:
    d = drivers(skey)
    return int(d.loc[d["name_acronym"] == acronym.upper(), "driver_number"].iloc[0])


# --------------------------------------------------------------------- laps
def laps(skey: int) -> pd.DataFrame:
    df = _get("laps", {"session_key": skey}, f"laps_{skey}")
    df["date_start"] = pd.to_datetime(df["date_start"], utc=True, format="ISO8601")
    return df


def stints(skey: int) -> pd.DataFrame:
    return _get("stints", {"session_key": skey}, f"stints_{skey}")


def fastest_lap(skey: int, drv: int) -> pd.Series:
    df = laps(skey)
    df = df[(df["driver_number"] == drv) & df["lap_duration"].notna()]
    return df.loc[df["lap_duration"].idxmin()]


# ---------------------------------------------------------------- telemetry
def _window(lap: pd.Series, pad: float):
    t0 = lap["date_start"] - pd.Timedelta(seconds=pad)
    t1 = lap["date_start"] + pd.Timedelta(seconds=lap["lap_duration"] + pad)
    fmt = "%Y-%m-%dT%H:%M:%S.%f"
    return t0.strftime(fmt), t1.strftime(fmt)


def lap_car_data(skey: int, lap: pd.Series, pad: float = 0.0) -> pd.DataFrame:
    """speed/rpm/throttle/brake/gear samples of one lap.  Adds column t [s]
    = time since lap start."""
    drv, n = int(lap["driver_number"]), int(lap["lap_number"])
    t0, t1 = _window(lap, pad)
    df = _get("car_data", {"session_key": skey, "driver_number": drv,
                           "date>=": t0, "date<=": t1},
              f"car_{skey}_{drv}_lap{n}")
    return _add_time(df, lap)


def lap_location(skey: int, lap: pd.Series, pad: float = 0.0) -> pd.DataFrame:
    drv, n = int(lap["driver_number"]), int(lap["lap_number"])
    t0, t1 = _window(lap, pad)
    df = _get("location", {"session_key": skey, "driver_number": drv,
                           "date>=": t0, "date<=": t1},
              f"loc_{skey}_{drv}_lap{n}")
    return _add_time(df, lap)


def _add_time(df: pd.DataFrame, lap: pd.Series) -> pd.DataFrame:
    df["date"] = pd.to_datetime(df["date"], utc=True, format="ISO8601")
    df = df.sort_values("date").reset_index(drop=True)
    df["t"] = (df["date"] - lap["date_start"]).dt.total_seconds()
    return df


def lap_telemetry(skey: int, lap: pd.Series) -> pd.DataFrame:
    """car_data merged with x/y position (nearest timestamp) and a
    distance column obtained by integrating speed over time."""
    car = lap_car_data(skey, lap)
    loc = lap_location(skey, lap)[["date", "x", "y"]]
    tel = pd.merge_asof(car, loc, on="date", direction="nearest")
    tel = tel[(tel["t"] >= 0) & (tel["t"] <= lap["lap_duration"])].reset_index(drop=True)
    v = tel["speed"].to_numpy() / 3.6                       # km/h -> m/s
    t = tel["t"].to_numpy()
    # trapezoidal rule:  s_i = s_{i-1} + (v_i + v_{i-1})/2 * (t_i - t_{i-1})
    ds = 0.5 * (v[1:] + v[:-1]) * (t[1:] - t[:-1])
    tel["distance"] = pd.Series([0.0, *ds]).cumsum()
    return tel
