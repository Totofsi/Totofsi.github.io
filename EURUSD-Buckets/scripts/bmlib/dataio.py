"""Daten laden und auf ein einheitliches Basisformat bringen.

Unterstützte Eingaben
---------------------
1. Ticks (bevorzugt, Eightcap-MT5-Export via scripts/mt5_export.py):
   CSV oder Parquet mit Spalten  time_msc (ms seit Epoche, Serverzeit!) | time,
   bid, ask  [, flags]. Zeitstempel = MT5-Serverzeit.
2. MT5-Terminal-Tickexport (Strg+U -> Ticks -> Export):
   <DATE> <TIME> <BID> <ASK> <LAST> <VOLUME> <FLAGS>  (tab-getrennt)
3. M1-Bars (Ersatz, wenn keine Ticks verfügbar):
   CSV mit datetime|time|<DATE>+<TIME>, open, high, low, close [, spread, tick_volume].

Basisformat
-----------
DataFrame, Index = UTC-Zeit (tz-aware), Spalten:
  o, h, l, c        Preis (Ticks: Mid; Bars: Bid wie geliefert)
  spread_med_pips   Median-Spread im Intervall (Ticks) bzw. Bar-Spread (MT5: Spalte spread in Points)
  spread_max_pips   Max-Spread im Intervall (nur Ticks)
  n_ticks           Ticks im Intervall
Auflösung: 1 Sekunde (aus Ticks, für exakte Ausschläge) und 1 Minute.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .timeutil import to_utc


# ---------------------------------------------------------------- Ticks
def _read_any(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        head = f.readline()
    sep = "\t" if "\t" in head else ("," if "," in head else ";")
    return pd.read_csv(path, sep=sep)


def load_ticks(paths: list[Path], data_tz: str) -> pd.DataFrame:
    """Liest Tickdateien -> DataFrame(index=UTC, bid, ask)."""
    frames = []
    for p in sorted(paths):
        df = _read_any(Path(p))
        df.columns = [c.strip("<>").lower() for c in df.columns]
        if "time_msc" in df.columns:
            t = pd.to_datetime(df["time_msc"].astype("int64"), unit="ms")
        elif "date" in df.columns and "time" in df.columns:
            t = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), format="mixed")
        else:
            t = pd.to_datetime(df["time"], format="mixed")
        out = pd.DataFrame({"bid": pd.to_numeric(df["bid"], errors="coerce"),
                            "ask": pd.to_numeric(df["ask"], errors="coerce")})
        out.index = to_utc(t, data_tz)
        frames.append(out)
    ticks = pd.concat(frames).sort_index()
    # MT5-Exporte enthalten Ticks, bei denen nur bid ODER ask wechselt (anderes = 0/NaN)
    ticks = ticks.replace(0.0, np.nan).ffill().dropna()
    ticks = ticks[~ticks.index.isna()]
    return ticks


def ticks_to_bars(ticks: pd.DataFrame, freq: str, pip: float) -> pd.DataFrame:
    mid = (ticks["bid"] + ticks["ask"]) / 2.0
    spr = (ticks["ask"] - ticks["bid"]) / pip
    g = mid.resample(freq)
    bars = pd.DataFrame({"o": g.first(), "h": g.max(), "l": g.min(), "c": g.last(),
                         "spread_med_pips": spr.resample(freq).median(),
                         "spread_max_pips": spr.resample(freq).max(),
                         "n_ticks": g.count()})
    return bars[bars["n_ticks"] > 0]


# ---------------------------------------------------------------- Bars
def load_bars(paths: list[Path], data_tz: str, pip: float, point: float) -> pd.DataFrame:
    frames = []
    for p in sorted(paths):
        df = _read_any(Path(p))
        df.columns = [c.strip("<>").lower() for c in df.columns]
        if "datetime" in df.columns:
            t = pd.to_datetime(df["datetime"], format="mixed")
        elif "date" in df.columns and "time" in df.columns:
            t = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), format="mixed")
        elif "time" in df.columns:
            t = pd.to_datetime(df["time"], format="mixed")
        else:
            raise ValueError(f"Keine Zeitspalte in {p}: {list(df.columns)}")
        out = pd.DataFrame({"o": df["open"].astype(float).values, "h": df["high"].astype(float).values,
                            "l": df["low"].astype(float).values, "c": df["close"].astype(float).values})
        if "spread" in df.columns:  # MT5: Spread in Points
            out["spread_med_pips"] = df["spread"].astype(float).values * point / pip
        else:
            out["spread_med_pips"] = np.nan
        out["spread_max_pips"] = np.nan
        vol = next((c for c in ["tick_volume", "tickvol", "volume", "vol"] if c in df.columns), None)
        out["n_ticks"] = df[vol].values if vol else np.nan
        out.index = to_utc(t, data_tz)
        frames.append(out)
    bars = pd.concat(frames).sort_index()
    bars = bars[~bars.index.isna()]
    bars = bars[~bars.index.duplicated(keep="last")]
    return bars


def load_dataset(cfg: dict, input_kind: str, paths: list[Path]) -> dict:
    """Gibt {'kind', 'base' (S1 oder M1), 'm1', 'ticks'?} zurück."""
    pip = cfg["market"]["pip_size"]
    point = 10 ** (-cfg["market"]["digits"])
    tz = cfg["time"]["data_timezone"]
    if input_kind == "ticks":
        ticks = load_ticks(paths, tz)
        s1 = ticks_to_bars(ticks, "1s", pip)
        m1 = ticks_to_bars(ticks, "1min", pip)
        return {"kind": "ticks", "ticks": ticks, "base": s1, "base_freq": "1s", "m1": m1}
    bars = load_bars(paths, tz, pip, point)
    return {"kind": "bars", "ticks": None, "base": bars, "base_freq": "1min", "m1": bars}
