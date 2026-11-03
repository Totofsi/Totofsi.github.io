"""Zeitzonen, Serverzeit, Sessions.

Konvention: intern ist alles UTC (tz-aware). Serverzeit wird als naive Zeit
abgeleitet. "SERVER_NY_PLUS_7" = New-York-Ortszeit + 7 h (GMT+2 Winter / GMT+3
Sommer, Wechsel an den US-DST-Terminen) – das ist die übliche MT5-Serverzeit
von Eightcap und vielen anderen Brokern (Tageswechsel = NY 17:00).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NY_PLUS_7 = "SERVER_NY_PLUS_7"


def to_utc(naive: pd.Series | pd.DatetimeIndex, tz: str) -> pd.DatetimeIndex:
    """Naive Zeitstempel in Zone `tz` -> UTC (tz-aware)."""
    idx = pd.DatetimeIndex(naive)
    if idx.tz is not None:
        return idx.tz_convert("UTC")
    if tz == NY_PLUS_7:
        ny = (idx - pd.Timedelta(hours=7)).tz_localize(
            "America/New_York", ambiguous="NaT", nonexistent="shift_forward")
        return ny.tz_convert("UTC")
    return idx.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def from_utc(idx_utc: pd.DatetimeIndex, tz: str) -> pd.DatetimeIndex:
    """UTC -> naive Ortszeit in `tz`."""
    if tz == NY_PLUS_7:
        return idx_utc.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
    return idx_utc.tz_convert(tz).tz_localize(None)


SESSION_ORDER = ["Asien", "London", "Überlappung LDN/NY", "New York", "Spät/Rollover"]


def _in_window(idx_utc, tz, win):
    loc = idx_utc.tz_convert(tz)
    h = loc.hour + loc.minute / 60.0
    return (h >= win[0]) & (h < win[1])


def session_labels(idx_utc: pd.DatetimeIndex, cfg: dict) -> np.ndarray:
    """Session je Zeitstempel. Fenster in Ortszeit -> DST korrekt."""
    s = cfg["sessions"]
    tok = _in_window(idx_utc, s["tokyo_tz"], s["tokyo"])
    ldn = _in_window(idx_utc, s["london_tz"], s["london"])
    ny = _in_window(idx_utc, s["newyork_tz"], s["newyork"])
    out = np.full(len(idx_utc), "Spät/Rollover", dtype=object)
    out[tok & ~ldn & ~ny] = "Asien"
    out[ldn & ~ny] = "London"
    out[ldn & ny] = "Überlappung LDN/NY"
    out[ny & ~ldn] = "New York"
    return out


def time_features(idx_utc: pd.DatetimeIndex, cfg: dict) -> pd.DataFrame:
    srv = from_utc(idx_utc, cfg["time"]["server_timezone"])
    loc = from_utc(idx_utc, cfg["time"]["local_timezone"])
    wd_names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    return pd.DataFrame({
        "hour_server": srv.hour.astype(np.int16),
        "hour_mez": loc.hour.astype(np.int16),
        "weekday": pd.Categorical([wd_names[d] for d in srv.dayofweek], categories=wd_names, ordered=True),
        "server_day": srv.normalize(),
        "session": pd.Categorical(session_labels(idx_utc, cfg), categories=SESSION_ORDER, ordered=True),
    }, index=idx_utc)
