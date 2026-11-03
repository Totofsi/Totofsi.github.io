#!/usr/bin/env python3
"""Marktvermessung für Bucket-/Nachkauf-Systeme – kompletter Lauf (Messungen 1–7).

Beispiele
---------
# Eightcap-Ticks (Export aus scripts/mt5_export.py):
python scripts/run_vermessung.py --config config/EURUSD.toml --kind ticks \
    --input "data/raw/eightcap/EURUSD_ticks_*.parquet" \
    --spec data/raw/eightcap/EURUSD_symbol_spec.json --name eightcap-ticks

# M1-Bars (Proxy):
python scripts/run_vermessung.py --config config/EURUSD.toml --kind bars \
    --input data/raw/proxy_ftmo_server4/EURUSD_m1.csv \
    --spread-input data/raw/proxy_ftmo_server4/EURUSD_m10.csv --name proxy-ftmo

Ausgabe (nie überschreibend, Ordner = Datum + Name):
  results/<datum>_<name>/   CSV-Tabellen + summary.json + quality.json
  charts/<datum>_<name>/    PNG-Charts
  reports/<datum>_<name>.md Bericht (Befunde zuerst, Methodik danach)
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bmlib import charts as C            # noqa: E402
from bmlib import measure as M           # noqa: E402
from bmlib.config import load_config     # noqa: E402
from bmlib.dataio import load_bars, load_dataset  # noqa: E402
from bmlib.report import write_report    # noqa: E402


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def unique_dir(base: Path) -> Path:
    if not base.exists():
        return base
    k = 2
    while Path(f"{base}_v{k}").exists():
        k += 1
    return Path(f"{base}_v{k}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--kind", choices=["ticks", "bars"], required=True)
    ap.add_argument("--input", required=True, help="Datei oder Glob")
    ap.add_argument("--spread-input", help="optionale Bars mit Spread-Spalte (z. B. M10), falls --input keinen Spread hat")
    ap.add_argument("--spec", help="Symbolspezifikation (JSON aus mt5_export.py oder CSV symbol_specs)")
    ap.add_argument("--events", help="optionaler Ereigniskalender CSV (time_utc,event)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--source-label", default="", help="Klartext-Quelle für den Bericht")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--start", help="Zeitraum-Start (UTC, YYYY-MM-DD)")
    ap.add_argument("--end", help="Zeitraum-Ende (UTC, YYYY-MM-DD)")
    ap.add_argument("--n-shuffle", type=int, default=30)
    args = ap.parse_args()

    cfg = load_config(args.config)
    sym = cfg["market"]["symbol"]
    pip = cfg["market"]["pip_size"]
    tag = f"{args.date}_{args.name}"
    out_res = unique_dir(ROOT / "results" / tag)
    tag = out_res.name
    out_ch = ROOT / "charts" / tag
    out_res.mkdir(parents=True)
    out_ch.mkdir(parents=True)
    note = f"{sym} · Quelle: {args.source_label or args.name} · Lauf {tag}"

    # ------------------------------------------------------------ Daten
    paths = [Path(p) for p in sorted(glob.glob(args.input))]
    if not paths:
        sys.exit(f"Keine Eingabedateien für {args.input}")
    log(f"Lade {len(paths)} Datei(en) …")
    ds = load_dataset(cfg, args.kind, paths)
    if args.start or args.end:
        for k in ("base", "m1"):
            ds[k] = ds[k].loc[args.start:args.end]
    m1 = ds["m1"]
    log(f"M1-Bars: {len(m1):,}  Zeitraum UTC {m1.index[0]} – {m1.index[-1]}")
    if args.kind == "ticks":
        spread_bars = ds["m1"][["spread_med_pips"]]
    elif args.spread_input:
        point = 10 ** (-cfg["market"]["digits"])
        spread_bars = load_bars([Path(args.spread_input)], cfg["time"]["data_timezone"], pip, point)[["spread_med_pips"]]
        spread_bars = spread_bars.loc[m1.index[0]:m1.index[-1]]
    elif m1["spread_med_pips"].notna().any():
        spread_bars = m1[["spread_med_pips"]]
    else:
        spread_bars = None

    spec = load_spec(args.spec, sym) if args.spec else {}

    # ------------------------------------------------------------ Qualität
    log("Datenqualität …")
    q = M.data_quality(ds, cfg, spread_bars)
    q["luecken_sonstige_liste"].to_csv(out_res / "quality_gaps.csv", index=False)
    qj = {k: v for k, v in q.items() if k != "luecken_sonstige_liste"}
    (out_res / "quality.json").write_text(json.dumps(qj, indent=2, default=str, ensure_ascii=False))
    charts = {}
    charts["quality"] = C.quality_chart(m1, spread_bars, cfg["time"]["server_timezone"], out_ch / "00_datenqualitaet.png", note)

    # ------------------------------------------------------------ Messung 1
    log("Messung 1: Ausschläge …")
    pb = M.prepare_base(ds, cfg)
    resA = M.run_excursions(pb, cfg, mode_b=False, adverse_first=True)
    resA_fav = M.run_excursions(pb, cfg, mode_b=False, adverse_first=False)
    resB = M.run_excursions(pb, cfg, mode_b=True, adverse_first=True)
    shuf = M.shuffled_bars(m1, cfg, cfg["measurement"]["shuffle_seed"])
    if args.kind == "bars":
        resS = M.run_excursions(pb, cfg, mode_b=False, adverse_first=True,
                                h=shuf["h"].to_numpy() / pip, l=shuf["l"].to_numpy() / pip, c=shuf["c"].to_numpy() / pip)
    else:  # Shuffle auf M1-Ebene, Einstiege je Minute
        pb_s = M.prepare_base({"base": shuf, "base_freq": "1min"}, cfg)
        resS = M.run_excursions(pb_s, cfg, mode_b=False, adverse_first=True)
    sA = M.excursion_summary(resA, cfg)
    sAf = M.excursion_summary(resA_fav, cfg)
    sB = M.excursion_summary(resB, cfg)
    sS = M.excursion_summary(resS, cfg)
    pcts = cfg["measurement"]["percentiles"]
    theo = pd.DataFrame([{"X_pips": x, **{f"p{p}": round(-x * np.log(1 - p / 100), 2) for p in pcts}}
                         for x in cfg["measurement"]["targets_pips"]])
    sA.to_csv(out_res / "m1_defA_adverse_first.csv", index=False)
    sAf.to_csv(out_res / "m1_defA_favorable_first.csv", index=False)
    sB.to_csv(out_res / "m1_defB_gewinn_ab_einstieg.csv", index=False)
    sS.to_csv(out_res / "m1_defA_zufallspfad_shuffle.csv", index=False)
    theo.to_csv(out_res / "m1_defA_theorie_random_walk.csv", index=False)
    main_x = 10 if 10 in cfg["measurement"]["targets_pips"] else cfg["measurement"]["targets_pips"][0]
    for x in cfg["measurement"]["targets_pips"]:
        charts[f"ccdf_{x}"] = C.mae_ccdf(resA, resS, x, out_ch / f"01_mae_ccdf_X{x:02d}.png", note)
    charts["norm"] = C.mae_normalized(sA, sS, pcts, out_ch / "01_mae_normiert.png", note)
    charts["defb"] = C.defb_bars(sB, out_ch / "01b_defB_gewinn_ab_einstieg.png", note)

    # ------------------------------------------------------------ Messung 2
    log("Messung 2: Stunde/Session/Wochentag …")
    g_hs = M.excursion_grouped(resA, pb, cfg, "hour_server")
    g_hm = M.excursion_grouped(resA, pb, cfg, "hour_mez")
    g_se = M.excursion_grouped(resA, pb, cfg, "session")
    g_wd = M.excursion_grouped(resA, pb, cfg, "weekday")
    g_se_shuf = M.excursion_grouped(resS, pb if args.kind == "bars" else pb_s, cfg, "session")
    stab = pd.concat([M.split_half_stability(resA, pb, by, main_x, pc)
                      for by in ("hour_server", "session", "weekday") for pc in (90, 99)])
    stab.to_csv(out_res / "m2_stabilitaet_halbjahre.csv", index=False)
    for n, g in [("hour_server", g_hs), ("hour_mez", g_hm), ("session", g_se), ("weekday", g_wd),
                 ("session_zufallspfad", g_se_shuf)]:
        g.to_csv(out_res / f"m2_{n}.csv", index=False)
    for x in cfg["measurement"]["targets_pips"]:
        charts[f"hs_{x}"] = C.by_hour(g_hs, x, "hour_server", out_ch / f"02_stunde_server_X{x:02d}.png",
                                      f"Messung 2 – MAE je Einstiegsstunde (Serverzeit), X={x}", note)
    charts["hm"] = C.by_hour(g_hm, main_x, "hour_mez", out_ch / f"02_stunde_mez_X{main_x:02d}.png",
                             f"Messung 2 – MAE je Einstiegsstunde (MEZ/MESZ), X={main_x}", note)
    charts["se"] = C.by_category(g_se, main_x, "session", out_ch / f"02_session_X{main_x:02d}.png",
                                 f"Messung 2 – MAE je Session, X={main_x}", note)
    charts["wd"] = C.by_category(g_wd, main_x, "weekday", out_ch / f"02_wochentag_X{main_x:02d}.png",
                                 f"Messung 2 – MAE je Wochentag (Server), X={main_x}", note)

    # ------------------------------------------------------------ Messung 3
    log("Messung 3: Regime …")
    daily = M.classify_days(M.add_regimes(M.daily_table(m1, cfg)))
    daily.to_csv(out_res / "m3_m4_tage.csv")
    ent_day = pb["feats"]["server_day"].to_numpy()
    reg_rows = []
    for kind, col in [("ex ante (ATR14 Vortage)", "regime_exante"), ("ex post (Tagesrange)", "regime_expost")]:
        lab = daily[col].reindex(pd.DatetimeIndex(ent_day)).astype(object).to_numpy()
        atr = daily["atr14_exante"].reindex(pd.DatetimeIndex(ent_day)).to_numpy()
        for (x, side), (mae, dur, cen) in resA.items():
            for r in [c for c in daily[col].cat.categories]:
                m = lab == r
                if m.sum() == 0:
                    continue
                row = {"Regimeart": kind, "Regime": r, "X_pips": x, "Seite": side,
                       "ATR14_median": round(float(np.nanmedian(atr[m])), 1)}
                row.update(M.pct_table(mae[m], cen[m], pcts))
                row["p99_in_ATR"] = round(row["p99"] / row["ATR14_median"], 3) if row["ATR14_median"] else np.nan
                reg_rows.append(row)
    reg = pd.DataFrame(reg_rows)
    reg.to_csv(out_res / "m3_regime.csv", index=False)
    charts["reg"] = C.regime_chart(reg, main_x, out_ch / f"03_regime_X{main_x:02d}.png", note)

    # ------------------------------------------------------------ Messung 4
    log("Messung 4: Trend-/Rangetage …")
    rules, auc = M.early_detection(m1, daily, cfg)
    rules.to_csv(out_res / "m4_frueherkennung_regeln.csv", index=False)
    auc.to_csv(out_res / "m4_frueherkennung_auc.csv", index=False)
    dt_counts = daily["daytype"].value_counts()
    # MAE von Gegentrend-Einstiegen an Trendtagen vs. sonst
    dtype = daily["daytype"].reindex(pd.DatetimeIndex(ent_day)).to_numpy()
    tdir = daily["trend_dir"].reindex(pd.DatetimeIndex(ent_day)).to_numpy()
    td_rows = []
    for (x, side), (mae, dur, cen) in resA.items():
        for t in ["Trendtag", "Mischtag", "Rangetag"]:
            m = dtype == t
            if t == "Trendtag":
                against = (tdir == "ab") if side == "Long" else (tdir == "auf")
                for lab_, mm in [("Trendtag gegen Trend", m & against), ("Trendtag mit Trend", m & ~against)]:
                    row = {"Tagtyp": lab_, "X_pips": x, "Seite": side}
                    row.update(M.pct_table(mae[mm], cen[mm], pcts)); td_rows.append(row)
            else:
                row = {"Tagtyp": t, "X_pips": x, "Seite": side}
                row.update(M.pct_table(mae[m], cen[m], pcts)); td_rows.append(row)
    td = pd.DataFrame(td_rows)
    td.to_csv(out_res / "m4_mae_nach_tagtyp.csv", index=False)
    charts["days"] = C.daytype_chart(daily.dropna(subset=["body_range"]), auc, out_ch / "04_trend_range_tage.png", note)

    # ------------------------------------------------------------ Messung 5
    log("Messung 5: Rückkehrneigung …")
    vr, hl = M.mean_reversion(m1, cfg, n_shuffle=args.n_shuffle)
    vr.to_csv(out_res / "m5_varianz_ratio_autokorrelation.csv", index=False)
    hl.to_csv(out_res / "m5_halbwertszeit.csv", index=False)
    charts["vr"] = C.vr_chart(vr, out_ch / "05_varianz_ratio.png", note)
    charts["hl"] = C.halflife_chart(hl, out_ch / "05_halbwertszeit.png", note)

    # ------------------------------------------------------------ Messung 6
    log("Messung 6: Extremphasen …")
    events = M.scheduled_slots(m1.index[0], m1.index[-1])
    if args.events:
        ev = pd.read_csv(args.events)
        ev["time_utc"] = pd.to_datetime(ev["time_utc"], utc=True)
        events = pd.concat([ev[["time_utc", "event"]], events]).sort_values("time_utc")
    ext_tables = {}
    for x in cfg["measurement"]["zigzag_pips"]:
        e = M.extremes(m1, cfg, x, cfg["measurement"]["top_n_extremes"], events)
        e.index = np.arange(len(e))
        e.to_csv(out_res / f"m6_extreme_X{x:02d}.csv", index=False)
        ext_tables[x] = e
        lr = M.leg_distribution(m1, cfg, x)
        ls = M.leg_distribution(shuf, cfg, x)
        pd.DataFrame({"stat": ["n", "p50", "p90", "p99", "max"],
                      "real": [len(lr), *np.percentile(lr, [50, 90, 99]).round(1), round(lr.max(), 1)],
                      "zufallspfad": [len(ls), *np.percentile(ls, [50, 90, 99]).round(1), round(ls.max(), 1)]}
                     ).to_csv(out_res / f"m6_beinverteilung_X{x:02d}.csv", index=False)
        charts[f"ext_{x}"] = C.extremes_chart(m1, e, lr, ls, x, out_ch / f"06_extreme_X{x:02d}.png", note,
                                              cfg["time"]["server_timezone"])

    # ------------------------------------------------------------ Messung 7
    log("Messung 7: Kosten …")
    cost = {}
    if spread_bars is not None:
        sp_h = M.spread_by_hour(spread_bars.dropna(), cfg)
        sp_h.to_csv(out_res / "m7_spread_je_serverstunde.csv")
        comm = cfg["costs"]["commission_per_lot_per_side"]
        pip_value = cfg["costs"]["contract_size"] * pip  # USD je Pip und Lot (Quote-Währung USD)
        scen = {}
        if not np.isnan(comm):
            scen[f"Kommission belegt {2*comm:.2f} USD RT"] = 2 * comm / pip_value
        for s in cfg["costs"]["commission_scenarios_rt_usd"]:
            scen[f"Szenario {s:.0f} USD RT/Lot"] = s / pip_value
        for label, cp in scen.items():
            t = M.cost_thresholds(sp_h, cfg, cp)
            t.to_csv(out_res / f"m7_kosten_schwellen_{label.split()[0].lower()}_{cp:.2f}pips.csv", index=False)
            cost[label] = t
        charts["spread"] = C.spread_chart(sp_h, out_ch / "07_spread_je_stunde.png", note)
        charts["costshare"] = C.cost_share_chart(sp_h, scen, out_ch / "07_kostenanteil.png", note)
    else:
        sp_h = None

    # ------------------------------------------------------------ Bericht
    log("Bericht …")
    ctx = dict(args=vars(args), cfg=cfg, tag=tag, quality=qj, gaps=q["luecken_sonstige_liste"], sA=sA, sAf=sAf,
               sB=sB, sS=sS, theo=theo, g_hs=g_hs, g_hm=g_hm, g_se=g_se, g_wd=g_wd, g_se_shuf=g_se_shuf, stab=stab,
               reg=reg, daily=daily, rules=rules, auc=auc, td=td, vr=vr, hl=hl, ext=ext_tables,
               sp_h=sp_h, cost=cost, spec=spec, charts=charts, main_x=main_x, kind=args.kind,
               n_entries=len(pb["entries"]), out_res=out_res, out_ch=out_ch)
    rep = write_report(ctx, ROOT / "reports" / f"{tag}.md")
    summ = {"tag": tag, "report": str(rep.relative_to(ROOT)), "results": str(out_res.relative_to(ROOT)),
            "charts": str(out_ch.relative_to(ROOT)), "m1_bars": len(m1), "entries": len(pb["entries"])}
    (out_res / "summary.json").write_text(json.dumps(summ, indent=2, ensure_ascii=False))
    log(f"Fertig: {rep}")


def load_spec(path: str, sym: str) -> dict:
    p = Path(path)
    if p.suffix == ".json":
        return json.loads(p.read_text())
    df = pd.read_csv(p)
    row = df[df["name"] == sym]
    return row.iloc[0].to_dict() if len(row) else {}


if __name__ == "__main__":
    main()
