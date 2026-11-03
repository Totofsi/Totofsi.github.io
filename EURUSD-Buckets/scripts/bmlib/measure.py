"""Messungen 1–7 + Datenqualität. Jede Funktion liefert DataFrames (keine Plots)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .kernels import excursion, zigzag
from .timeutil import time_features, from_utc


# ============================================================ Hilfen
def pct_table(values: np.ndarray, censored: np.ndarray, pcts) -> dict:
    """Perzentile + Max. Zensierte Werte gehen als Untergrenze ein."""
    out = {"n": int(len(values))}
    if len(values) == 0:
        for p in pcts:
            out[f"p{p}"] = np.nan
        out["max"] = np.nan
        out["zensiert_%"] = np.nan
        return out
    q = np.percentile(values, pcts)
    for p, v in zip(pcts, q):
        out[f"p{p}"] = round(float(v), 2)
    out["max"] = round(float(values.max()), 2)
    out["zensiert_%"] = round(100.0 * censored.mean(), 3)
    return out


def prepare_base(ds: dict, cfg: dict) -> dict:
    """Preisreihen in Pips, Sekundenachse, Einstiegsindizes je Minute."""
    pip = cfg["market"]["pip_size"]
    base = ds["base"]
    tsec = base.index.as_unit("s").asi8.astype(np.float64)
    h = base["h"].to_numpy(np.float64) / pip
    l = base["l"].to_numpy(np.float64) / pip
    c = base["c"].to_numpy(np.float64) / pip
    # Einstieg: letzter Basis-Bar jeder Minute (bei M1-Basis = jeder Bar)
    step = int(cfg["measurement"]["entry_every_min"])
    minute = base.index.floor(f"{step}min")
    last_in_min = np.r_[minute[1:] != minute[:-1], True]
    entries = np.flatnonzero(last_in_min).astype(np.int64)
    entry_time = base.index[entries]
    if ds["base_freq"] == "1min":
        entry_time = entry_time + pd.Timedelta(minutes=1)  # Einstieg zum Close = Bar-Ende
    feats = time_features(entry_time, cfg)
    return {"h": h, "l": l, "c": c, "tsec": tsec, "entries": entries,
            "entry_time": entry_time, "feats": feats}


def run_excursions(pb: dict, cfg: dict, mode_b: bool, adverse_first: bool,
                   h=None, l=None, c=None) -> dict:
    """Alle X × Richtung. Rückgabe {(X, 'Long'|'Short'): (mae, dur, cen)}."""
    h = pb["h"] if h is None else h
    l = pb["l"] if l is None else l
    c = pb["c"] if c is None else c
    max_secs = float(cfg["measurement"]["max_horizon_days"]) * 86400.0
    res = {}
    for x in cfg["measurement"]["targets_pips"]:
        for d, name in [(1, "Long"), (-1, "Short")]:
            res[(x, name)] = excursion(h, l, c, pb["entries"], float(x), d, mode_b,
                                       adverse_first, max_secs, pb["tsec"])
    return res


def excursion_summary(res: dict, cfg: dict, mask=None) -> pd.DataFrame:
    pcts = cfg["measurement"]["percentiles"]
    rows = []
    for (x, side), (mae, dur, cen) in res.items():
        m = slice(None) if mask is None else mask
        r = {"X_pips": x, "Seite": side}
        r.update(pct_table(mae[m], cen[m], pcts))
        r["Dauer_med_min"] = round(float(np.median(dur[m])) / 60.0, 1)
        r["Dauer_p99_min"] = round(float(np.percentile(dur[m], 99)) / 60.0, 1)
        r["MAE=0_%"] = round(100.0 * float((mae[m] <= 1e-9).mean()), 1)
        rows.append(r)
    return pd.DataFrame(rows)


def excursion_grouped(res: dict, pb: dict, cfg: dict, by: str) -> pd.DataFrame:
    pcts = cfg["measurement"]["percentiles"]
    g = pb["feats"][by].to_numpy()
    keys = pb["feats"][by].cat.categories if hasattr(pb["feats"][by], "cat") else np.unique(g)
    rows = []
    for (x, side), (mae, dur, cen) in res.items():
        for k in keys:
            m = g == k
            if m.sum() == 0:
                continue
            r = {"X_pips": x, "Seite": side, by: k}
            r.update(pct_table(mae[m], cen[m], pcts))
            rows.append(r)
    return pd.DataFrame(rows)


# ============================================================ Shuffle-Benchmark
def shuffled_bars(m1: pd.DataFrame, cfg: dict, seed: int) -> pd.DataFrame:
    """Zufallspfad mit gleicher Tagesvolatilität: Bar-Formen (relativ zum
    Vor-Close) werden innerhalb jedes Servertages zufällig permutiert.
    Zerstört Autokorrelation/Trends innerhalb des Tages, erhält Tagesvola,
    Bar-Ranges und Overnight-Lücken zwischen Tagen."""
    rng = np.random.default_rng(seed)
    pip = cfg["market"]["pip_size"]
    c = m1["c"].to_numpy() / pip
    prev = np.r_[c[0], c[:-1]]
    dh = m1["h"].to_numpy() / pip - prev
    dl = m1["l"].to_numpy() / pip - prev
    dc = c - prev
    day = from_utc(m1.index, cfg["time"]["server_timezone"]).normalize().asi8
    starts = np.flatnonzero(np.r_[True, day[1:] != day[:-1]])
    ends = np.r_[starts[1:], len(c)]
    perm = np.arange(len(c))
    for s, e in zip(starts, ends):
        if e - s > 2:
            perm[s + 1:e] = s + 1 + rng.permutation(e - s - 1)  # erster Bar (Gap) bleibt
    dh, dl, dc = dh[perm], dl[perm], dc[perm]
    cc = c[0] + np.cumsum(np.r_[0.0, dc[1:]])
    pc = np.r_[cc[0], cc[:-1]]
    return pd.DataFrame({"h": (pc + dh) * pip, "l": (pc + dl) * pip, "c": cc * pip,
                         "o": pc * pip}, index=m1.index)


# ============================================================ Messung 3: Regime
def daily_table(m1: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    pip = cfg["market"]["pip_size"]
    srv = from_utc(m1.index, cfg["time"]["server_timezone"])
    df = m1[["o", "h", "l", "c"]].copy()
    df["day"] = srv.normalize()
    df["absd"] = df["c"].diff().abs()
    g = df.groupby("day")
    d = pd.DataFrame({"open": g["o"].first(), "high": g["h"].max(), "low": g["l"].min(),
                      "close": g["c"].last(), "path": g["absd"].sum(), "bars": g["c"].count()})
    d = d[d["bars"] >= 600]  # Rumpftage (z. B. Feiertage) nicht klassifizieren
    d["range_pips"] = (d["high"] - d["low"]) / pip
    d["net_pips"] = (d["close"] - d["open"]) / pip
    d["body_range"] = d["net_pips"].abs() / d["range_pips"].replace(0, np.nan)
    d["close_pos"] = (d["close"] - d["low"]) / (d["high"] - d["low"]).replace(0, np.nan)
    d["eff_ratio"] = (d["close"] - d["open"]).abs() / d["path"].replace(0, np.nan)
    d["atr14_exante"] = d["range_pips"].shift(1).rolling(14, min_periods=10).mean()
    d["weekday"] = d.index.dayofweek
    return d


def add_regimes(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    lab = ["Q1 ruhig", "Q2", "Q3", "Q4", "Q5 wild"]
    d["regime_exante"] = pd.qcut(d["atr14_exante"], 5, labels=lab)
    d["regime_expost"] = pd.qcut(d["range_pips"], 5, labels=lab)
    return d


def classify_days(daily: pd.DataFrame) -> pd.DataFrame:
    """Trend/Range-Klassifikation (Messdefinition, im Bericht dokumentiert)."""
    d = daily.copy()
    up = (d["net_pips"] > 0) & (d["close_pos"] >= 0.85)
    dn = (d["net_pips"] < 0) & (d["close_pos"] <= 0.15)
    trend = (d["body_range"] >= 0.70) & (up | dn)
    rng = d["body_range"] <= 0.30
    d["daytype"] = np.where(trend, "Trendtag", np.where(rng, "Rangetag", "Mischtag"))
    d["trend_dir"] = np.where(trend & up, "auf", np.where(trend & dn, "ab", ""))
    return d


def early_detection(m1: pd.DataFrame, daily: pd.DataFrame, cfg: dict,
                    checkpoints=(4, 8, 10, 12, 14, 16)) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Teiltagesmerkmale bis Serverstunde h -> Vorhersagekraft für Trendtag."""
    pip = cfg["market"]["pip_size"]
    srv = from_utc(m1.index, cfg["time"]["server_timezone"])
    df = m1[["o", "h", "l", "c"]].copy()
    df["day"] = srv.normalize()
    df["hr"] = srv.hour
    rows, auc_rows = [], []
    for hcut in checkpoints:
        part = df[df["hr"] < hcut]
        g = part.groupby("day")
        f = pd.DataFrame({"o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(), "c": g["c"].last()})
        f = f.join(daily[["daytype", "atr14_exante", "net_pips"]], how="inner").dropna()
        rng = (f["h"] - f["l"]) / pip
        f["p_body"] = ((f["c"] - f["o"]).abs() / pip) / rng.replace(0, np.nan)
        f["p_range_atr"] = rng / f["atr14_exante"]
        f["p_net_atr"] = ((f["c"] - f["o"]).abs() / pip) / f["atr14_exante"]
        f["same_dir"] = np.sign(f["c"] - f["o"]) == np.sign(f["net_pips"])
        y = (f["daytype"] == "Trendtag").to_numpy()
        base = y.mean()
        for feat in ["p_body", "p_net_atr", "p_range_atr"]:
            auc_rows.append({"bis_Serverstunde": hcut, "Merkmal": feat,
                             "AUC": round(_auc(f[feat].to_numpy(), y), 3), "Basisrate_Trendtag": round(base, 3)})
        # Regel: Netto-Bewegung bis h >= k * ATR
        for k in (0.3, 0.5, 0.7):
            sig = (f["p_net_atr"] >= k).to_numpy()
            tp = (sig & y).sum()
            rows.append({"bis_Serverstunde": hcut, "Regel": f"|Netto| ≥ {k}·ATR",
                         "Signal_Tage": int(sig.sum()), "Trefferquote_%": round(100 * tp / max(sig.sum(), 1), 1),
                         "erfasste_Trendtage_%": round(100 * tp / max(y.sum(), 1), 1),
                         "Richtung_richtig_%": round(100 * float(f.loc[sig & y, "same_dir"].mean()) if (sig & y).any() else np.nan, 1),
                         "Basisrate_%": round(100 * base, 1)})
    return pd.DataFrame(rows), pd.DataFrame(auc_rows)


def _auc(score, y):
    ok = ~np.isnan(score)
    s, y = score[ok], y[ok]
    npos, nneg = y.sum(), (~y).sum()
    if npos == 0 or nneg == 0:
        return np.nan
    ranks = pd.Series(s).rank().to_numpy()
    return (ranks[y].sum() - npos * (npos + 1) / 2) / (npos * nneg)


# ============================================================ Messung 5: Rückkehrneigung
def _minute_grid(m1: pd.DataFrame, cfg: dict):
    """Log-Preis auf vollständigem 1-Minuten-Raster je Servertag (ffill)."""
    srv = from_utc(m1.index, cfg["time"]["server_timezone"])
    s = pd.Series(np.log(m1["c"].to_numpy()), index=m1.index)
    full = s.resample("1min").last()
    filled = full.ffill(limit=30)
    day = from_utc(filled.index, cfg["time"]["server_timezone"]).normalize()
    return filled, day


def _vr_ac(r1: np.ndarray, day: np.ndarray, sess: np.ndarray, q: int, key):
    """VR(q) aus überlappenden q-Renditen; Lag-1-Autokorrelation aufeinander-
    folgender, nicht-überlappender q-Renditen. Nur innerhalb Servertag und
    (falls key) innerhalb derselben Session."""
    n = len(r1)
    valid = ~np.isnan(r1)
    cs = np.r_[0.0, np.cumsum(np.where(valid, r1, 0.0))]
    cv = np.r_[0, np.cumsum(valid)]
    idx = np.arange(n - q + 1)
    rq = cs[idx + q] - cs[idx]
    ok = ((cv[idx + q] - cv[idx]) == q) & (day[idx] == day[idx + q - 1])
    sel1 = valid
    if key is not None:
        ok &= (sess[idx] == key) & (sess[idx + q - 1] == key)
        sel1 = valid & (sess == key)
    var1 = np.var(r1[sel1])
    vr = np.var(rq[ok]) / (q * var1) if ok.sum() > 10 else np.nan
    a = np.arange(0, n - 2 * q + 1, q)
    b = a + q
    m = ok[a] & ok[b] & (day[a] == day[b])
    x, y = rq[a][m], rq[b][m]
    ac = np.corrcoef(x, y)[0, 1] if len(x) > 30 else np.nan
    return vr, ac, int(ok.sum()), int(len(x))


def _shuffle_within_day(r1, starts, ends, rng):
    rs = r1.copy()
    for s, e in zip(starts, ends):
        if e - s > 2:
            rs[s + 1:e] = rs[s + 1:e][rng.permutation(e - s - 1)]
    return rs


def mean_reversion(m1: pd.DataFrame, cfg: dict, n_shuffle: int = 30) -> tuple[pd.DataFrame, pd.DataFrame]:
    filled, day = _minute_grid(m1, cfg)
    from .timeutil import session_labels
    sess = session_labels(filled.index, cfg)
    lp = filled.to_numpy()
    r1 = np.r_[np.nan, np.diff(lp)]
    dayv = day.asi8
    r1[np.r_[True, dayv[1:] != dayv[:-1]]] = np.nan  # keine Overnight-/Wochenend-Renditen
    hs = cfg["measurement"]["vr_horizons_min"]
    keys = [None, "Asien", "London", "Überlappung LDN/NY", "New York", "Spät/Rollover"]
    rng = np.random.default_rng(cfg["measurement"]["shuffle_seed"])
    # Nullverteilung: Renditen innerhalb Tag permutieren
    starts = np.flatnonzero(np.r_[True, dayv[1:] != dayv[:-1]])
    ends = np.r_[starts[1:], len(r1)]
    shuffles = [_shuffle_within_day(r1, starts, ends, rng) for _ in range(n_shuffle)]
    midpt = len(r1) // 2
    r1_h1 = r1.copy(); r1_h1[midpt:] = np.nan
    r1_h2 = r1.copy(); r1_h2[:midpt] = np.nan
    rows = []
    for key in keys:
        for q in hs:
            vr, ac, nvr, nac = _vr_ac(r1, dayv, sess, q, key)
            nulls = [_vr_ac(rs, dayv, sess, q, key)[:2] for rs in shuffles]
            vr_h1 = _vr_ac(r1_h1, dayv, sess, q, key)[0]
            vr_h2 = _vr_ac(r1_h2, dayv, sess, q, key)[0]
            null_vr = [v for v, _ in nulls]
            null_ac = [a for _, a in nulls]
            rows.append({"Session": key or "Alle", "Horizont_min": q,
                         "VR": round(vr, 3), "VR_Null_2.5%": round(np.nanpercentile(null_vr, 2.5), 3),
                         "VR_Null_97.5%": round(np.nanpercentile(null_vr, 97.5), 3),
                         "VR_1.Hälfte": round(vr_h1, 3), "VR_2.Hälfte": round(vr_h2, 3),
                         "AC1": round(ac, 4), "AC1_Null_2.5%": round(np.nanpercentile(null_ac, 2.5), 4),
                         "AC1_Null_97.5%": round(np.nanpercentile(null_ac, 97.5), 4),
                         "n_AC": nac})
    vr_df = pd.DataFrame(rows)
    # Halbwertszeit der Abweichung vom gleitenden Mittel, real vs. permutiert
    hl_rows = []
    rs = shuffles[0]
    lp_shuf = np.nancumsum(np.nan_to_num(rs))
    lp_real = np.nancumsum(np.nan_to_num(r1))
    for W in cfg["measurement"]["mr_windows_min"]:
        for label, series in [("real", lp_real), ("Zufallspfad", lp_shuf)]:
            ps = pd.Series(series)
            dev = (ps - ps.rolling(W, min_periods=W).mean()).to_numpy()
            d0 = dev[:-1]; d1 = dev[1:]
            same = dayv[:-1] == dayv[1:]
            for key in keys:
                m = same & ~np.isnan(d0) & ~np.isnan(d1)
                if key is not None:
                    m &= sess[:-1] == key
                if m.sum() < 100:
                    continue
                beta = np.dot(d0[m], d1[m]) / np.dot(d0[m], d0[m])
                hl = -np.log(2) / np.log(beta) if 0 < beta < 1 else np.inf
                hl_rows.append({"Fenster_min": W, "Reihe": label, "Session": key or "Alle",
                                "beta": round(beta, 5), "Halbwertszeit_min": round(hl, 1)})
    return vr_df, pd.DataFrame(hl_rows)


# ============================================================ Messung 6: Extremphasen
def extremes(m1: pd.DataFrame, cfg: dict, x: float, top: int, events: pd.DataFrame | None) -> pd.DataFrame:
    pip = cfg["market"]["pip_size"]
    h = m1["h"].to_numpy() / pip
    l = m1["l"].to_numpy() / pip
    s, e, d, ln = zigzag(h, l, float(x))
    legs = pd.DataFrame({"s": s, "e": e, "dir": d, "len": ln}).sort_values("len", ascending=False).head(top)
    t_end = m1.index + pd.Timedelta(minutes=1)
    rows = []
    for _, r in legs.iterrows():
        ts, te = m1.index[int(r.s)], t_end[int(r.e)]
        srv_s = from_utc(pd.DatetimeIndex([ts]), cfg["time"]["server_timezone"])[0]
        mez_s = from_utc(pd.DatetimeIndex([ts]), cfg["time"]["local_timezone"])[0]
        dur_min = (te - ts).total_seconds() / 60
        trig = _match_events(ts, te, events) if events is not None else ""
        rows.append({"Start_Server": srv_s.strftime("%Y-%m-%d %H:%M"), "Start_MEZ": mez_s.strftime("%a %d.%m.%Y %H:%M"),
                     "Richtung": "auf" if r.dir == 1 else "ab", "Länge_Pips": round(r.len, 1),
                     "Dauer_h": round(dur_min / 60, 1), "Pips/h": round(r.len / max(dur_min / 60, 1 / 60), 1),
                     "Ereignis_im_Fenster": trig})
    return pd.DataFrame(rows)


def leg_distribution(m1: pd.DataFrame, cfg: dict, x: float) -> np.ndarray:
    pip = cfg["market"]["pip_size"]
    _, _, _, ln = zigzag(m1["h"].to_numpy() / pip, m1["l"].to_numpy() / pip, float(x))
    return ln


def _match_events(ts, te, ev: pd.DataFrame) -> str:
    m = (ev["time_utc"] >= ts - pd.Timedelta(minutes=30)) & (ev["time_utc"] <= te)
    names = ev.loc[m, "event"].tolist()
    return "; ".join(dict.fromkeys(names))[:120]


def scheduled_slots(start, end) -> pd.DataFrame:
    """Regelmäßige Veröffentlichungs-Slots (aus Regeln abgeleitet, keine Inhalte):
    US-Daten 08:30 ET (werktags), NFP = 1. Freitag 08:30 ET, US 10:00 ET."""
    s0 = pd.Timestamp(start).tz_convert("America/New_York").tz_localize(None).normalize()
    e0 = pd.Timestamp(end).tz_convert("America/New_York").tz_localize(None).normalize()
    days = pd.date_range(s0, e0, freq="B")
    rows = []
    for d in days:
        nfp = d.dayofweek == 4 and d.day <= 7
        t830 = pd.Timestamp(d.year, d.month, d.day, 8, 30).tz_localize("America/New_York").tz_convert("UTC")
        rows.append({"time_utc": t830, "event": "NFP (1. Fr 08:30 ET)" if nfp else "US-Daten-Slot 08:30 ET"})
    return pd.DataFrame(rows)


# ============================================================ Messung 7: Kosten
def spread_by_hour(spread_bars: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    f = time_features(spread_bars.index, cfg)
    df = pd.DataFrame({"spread": spread_bars["spread_med_pips"].to_numpy(),
                       "hour_server": f["hour_server"].to_numpy(), "hour_mez": f["hour_mez"].to_numpy()})
    g = df.groupby("hour_server")["spread"]
    out = pd.DataFrame({"Spread_Median": g.median(), "Spread_Mittel": g.mean(),
                        "Spread_p90": g.quantile(0.9), "Spread_p99": g.quantile(0.99), "Spread_max": g.max(),
                        "n_Bars": g.count()}).round(3)
    mez = df.groupby("hour_server")["hour_mez"].agg(lambda s: "/".join(str(v) for v in sorted(s.unique())))
    out.insert(0, "MEZ_Stunde(n)", mez)
    return out


def cost_thresholds(spread_hour: pd.DataFrame, cfg: dict, commission_rt_pips: float, stat="Spread_Median") -> pd.DataFrame:
    rows = []
    for hr, r in spread_hour.iterrows():
        cost = r[stat] + commission_rt_pips
        row = {"Serverstunde": hr, "MEZ": r["MEZ_Stunde(n)"], "Kosten_Pips": round(cost, 3)}
        for s in cfg["costs"]["cost_share_thresholds"]:
            row[f"Ziel_<_{int(s*100)}%"] = round(cost / s, 2)
        rows.append(row)
    return pd.DataFrame(rows)


# ============================================================ Datenqualität
def data_quality(ds: dict, cfg: dict, spread_bars: pd.DataFrame | None) -> dict:
    pip = cfg["market"]["pip_size"]
    m1 = ds["m1"]
    srv = from_utc(m1.index, cfg["time"]["server_timezone"])
    q = {}
    q["zeitraum_utc"] = f"{m1.index[0]} – {m1.index[-1]}"
    q["m1_bars"] = len(m1)
    q["duplikate"] = int(m1.index.duplicated().sum())
    days = pd.Series(1, index=srv.normalize()).groupby(level=0).count()
    q["handelstage"] = int(len(days))
    q["tage_unter_1000_bars"] = days[days < 1000].index.strftime("%Y-%m-%d").tolist()
    q["bars_an_wochenenden_server"] = int((srv.dayofweek >= 5).sum())
    # Lücken
    dt = np.diff(m1.index.as_unit("s").asi8) / 60.0
    gap = dt > cfg["measurement"]["gap_minutes"]
    gstart = m1.index[:-1][gap]
    gsrv = from_utc(gstart, cfg["time"]["server_timezone"])
    gl = pd.DataFrame({"start_server": gsrv, "laenge_min": dt[gap]})
    gl["wochenende"] = gl["laenge_min"] > 24 * 60
    gl["rollover"] = (gsrv.hour >= 23) | (gsrv.hour == 0)
    q["luecken_gesamt"] = int(gap.sum())
    q["luecken_wochenende"] = int(gl["wochenende"].sum())
    q["luecken_rollover_23_01"] = int((gl["rollover"] & ~gl["wochenende"]).sum())
    other = gl[~gl["wochenende"] & ~gl["rollover"]]
    q["luecken_sonstige"] = int(len(other))
    q["luecken_sonstige_liste"] = other.sort_values("laenge_min", ascending=False).head(15)
    # Sprünge und Extrembars
    c = m1["c"].to_numpy()
    jump = np.abs(m1["o"].to_numpy()[1:] - c[:-1]) / pip
    q["sprung_gt_10pips_ausser_wochenende"] = int(((jump > 10) & (dt < 24 * 60)).sum())
    rngb = (m1["h"] - m1["l"]).to_numpy() / pip
    q["m1_range_p50_p99_max"] = [round(float(np.percentile(rngb, 50)), 2), round(float(np.percentile(rngb, 99)), 2),
                                 round(float(rngb.max()), 2)]
    q["m1_range_gt_20pips"] = int((rngb > 20).sum())
    q["anteil_bars_range_ge_X"] = {x: round(100 * float((rngb >= x).mean()), 2) for x in cfg["measurement"]["targets_pips"]}
    q["null_range_bars_%"] = round(100 * float((rngb == 0).mean()), 2)
    q["ohlc_inkonsistent"] = int(((m1["h"] < m1[["o", "c"]].max(axis=1)) | (m1["l"] > m1[["o", "c"]].min(axis=1))).sum())
    if spread_bars is not None and spread_bars["spread_med_pips"].notna().any():
        sp = spread_bars["spread_med_pips"]
        ssrv = from_utc(sp.index, cfg["time"]["server_timezone"])
        spike = sp > cfg["measurement"]["spread_spike_pips"]
        q["spread_spitzen_n"] = int(spike.sum())
        q["spread_spitzen_nach_serverstunde"] = pd.Series(ssrv.hour[spike.to_numpy()]).value_counts().sort_index().to_dict()
        q["spread_median_gesamt"] = round(float(sp.median()), 3)
    return q


# ============================================================ Stabilität
def split_half_stability(res: dict, pb: dict, by: str, x: int, pct: float = 99) -> pd.DataFrame:
    """Rangkorrelation (Spearman) der Gruppen-Perzentile zwischen erster und
    zweiter Hälfte des Zeitraums. Hoch = Muster wiederholt sich."""
    t = pb["entry_time"]
    mid = t[0] + (t[-1] - t[0]) / 2
    half = (t >= mid)
    g = pb["feats"][by].astype(str).to_numpy()
    keys = [k for k in pd.unique(g)]
    rows = []
    for side in ("Long", "Short"):
        mae = res[(x, side)][0]
        a = [np.percentile(mae[(g == k) & ~half], pct) for k in keys]
        b = [np.percentile(mae[(g == k) & half], pct) for k in keys]
        rho = pd.Series(a).corr(pd.Series(b), method="spearman")
        rows.append({"Gruppierung": by, "X_pips": x, "Seite": side, "Perzentil": pct,
                     "Spearman_H1_H2": round(float(rho), 2), "Teilung_bei": str(mid)[:10]})
    return pd.DataFrame(rows)
