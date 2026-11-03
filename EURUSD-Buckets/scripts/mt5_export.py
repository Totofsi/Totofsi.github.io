#!/usr/bin/env python3
"""Eightcap-MT5-Export: Real-Ticks + Symbolspezifikation (Swap) + Kommission aus Deal-Historie.

Läuft NUR unter Windows mit installiertem, eingeloggtem MetaTrader-5-Terminal
(Eightcap). Liest ausschließlich – sendet keine Orders, ändert nichts am Konto.

    pip install MetaTrader5 pandas pyarrow
    python scripts/mt5_export.py --symbol EURUSD --years 3 --out data/raw/eightcap

Ergebnis in --out:
    <SYMBOL>_ticks_YYYY-MM.parquet   Spalten time_msc (Serverzeit, ms), bid, ask, flags
    <SYMBOL>_symbol_spec.json        komplette symbol_info + account_info (ohne Login/Name)
                                     + gemessene Kommission je Lot und Seite (falls Deals vorhanden)
    export_log.json                  Monatszähler, Erst-/Letzttick, Laufzeit

Hinweise
- MT5 liefert Tick-Zeitstempel in Serverzeit (als "UTC" etikettiert). Die
  Konfiguration setzt deshalb data_timezone = "SERVER_NY_PLUS_7".
- Für lange Zeiträume vorher im Terminal: Extras > Optionen > Charts >
  "Max. Balken im Chart" = Unbegrenzt; ggf. Symbol > Ticks einmal laden.
- Kommission ist nicht Teil von symbol_info. Sie wird aus echten Deals des
  Kontos gelesen (history_deals_get). Ohne EURUSD-Deals bleibt sie leer ->
  dann bitte Wert aus der Eightcap-Kontospezifikation (Raw-Konto) belegen und in
  config/EURUSD.toml eintragen, mit Quelle in STATUS.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import pandas as pd


def month_starts(start: dt.datetime, end: dt.datetime):
    cur = dt.datetime(start.year, start.month, 1)
    while cur < end:
        nxt = dt.datetime(cur.year + (cur.month // 12), cur.month % 12 + 1, 1)
        yield cur, min(nxt, end)
        cur = nxt


def main():
    import MetaTrader5 as mt5

    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--years", type=float, default=3)
    ap.add_argument("--out", default="data/raw/eightcap")
    ap.add_argument("--terminal", help="Pfad zu terminal64.exe (optional)")
    ap.add_argument("--deal-days", type=int, default=365, help="Deal-Historie für Kommissionsmessung")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ok = mt5.initialize(args.terminal) if args.terminal else mt5.initialize()
    if not ok:
        raise SystemExit(f"MT5 initialize fehlgeschlagen: {mt5.last_error()}")
    if not mt5.symbol_select(args.symbol, True):
        raise SystemExit(f"Symbol {args.symbol} nicht verfügbar")

    acc = mt5.account_info()._asdict()
    for k in ("login", "name"):
        acc.pop(k, None)
    si = mt5.symbol_info(args.symbol)._asdict()
    spec = {"exported_at_local": dt.datetime.now().isoformat(), "account": acc, "symbol": si}

    # --- Kommission aus echten Deals
    now = dt.datetime.now() + dt.timedelta(days=1)
    deals = mt5.history_deals_get(now - dt.timedelta(days=args.deal_days), now, group=f"*{args.symbol}*")
    if deals:
        df = pd.DataFrame([d._asdict() for d in deals])
        df = df[(df["volume"] > 0) & (df["symbol"] == args.symbol)]
        if len(df):
            per_lot_side = (df["commission"].abs() / df["volume"])
            spec["commission_measured"] = {
                "deals": int(len(df)), "per_lot_per_side_median": float(per_lot_side.median()),
                "per_lot_per_side_min": float(per_lot_side.min()), "per_lot_per_side_max": float(per_lot_side.max()),
                "currency": acc.get("currency"), "note": "aus history_deals_get, |commission|/volume je Deal (Seite)"}
    (out / f"{args.symbol}_symbol_spec.json").write_text(json.dumps(spec, indent=2, default=str))

    # --- Ticks monatsweise
    end = dt.datetime.now()
    start = end - dt.timedelta(days=int(365 * args.years))
    logs = []
    for a, b in month_starts(start, end):
        fn = out / f"{args.symbol}_ticks_{a:%Y-%m}.parquet"
        t0 = time.time()
        ticks = mt5.copy_ticks_range(args.symbol, a, b, mt5.COPY_TICKS_ALL)
        if ticks is None or len(ticks) == 0:
            logs.append({"month": f"{a:%Y-%m}", "ticks": 0, "error": str(mt5.last_error())})
            print(f"{a:%Y-%m}: keine Ticks {mt5.last_error()}")
            continue
        df = pd.DataFrame(ticks)[["time_msc", "bid", "ask", "flags"]]
        df.to_parquet(fn, index=False)
        first = pd.to_datetime(df["time_msc"].iloc[0], unit="ms")
        last = pd.to_datetime(df["time_msc"].iloc[-1], unit="ms")
        logs.append({"month": f"{a:%Y-%m}", "ticks": int(len(df)), "first_server": str(first),
                     "last_server": str(last), "sec": round(time.time() - t0, 1)})
        print(f"{a:%Y-%m}: {len(df):,} Ticks  {first} – {last}")
    (out / "export_log.json").write_text(json.dumps(logs, indent=2))
    mt5.shutdown()


if __name__ == "__main__":
    main()
