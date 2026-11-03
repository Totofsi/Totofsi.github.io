# Herkunft Proxy-Daten FTMO-Server4

- Quelle: öffentliches GitHub-Repository `Gianniskas/mt5-m1-bars-us500-eurusd-xauusd`,
  Commit `c00b90394dbaf0e51bbe1a9097094075d5487b45` (2026-05-24), abgerufen 2026-11-03.
- Inhalt laut Quelle: MT5-Export von FTMO-Server4; M1 = aus Broker-Ticks resampelt (Mid = (Bid+Ask)/2),
  M10..D1 = Broker-OHLC inkl. Median-Spread je Bar (Points); `symbol_specs.csv` = MT5 SymbolInfo;
  `spreads_summary.csv` = Live-Spread je UTC-Stunde, 16.–23.05.2026.
- Eigene Prüfung: Zeitstempel sind **Serverzeit (NY+7)**, nicht UTC wie im Quell-README angegeben
  (keine Sonntagsbars, Freitagsbars bis 23:5x, Spread-Spitze um Serverstunde 0).
- Plausibilität: große Bars fallen auf bekannte Termine (NFP 10.01.2025 und 03.07.2025 08:30 ET,
  Powell Jackson Hole 22.08.2025 10:00 ET, US-Zölle 02.04.2025 nach US-Schluss).
- Verworfen: `getdata-finance/eurusd-1m-ohlcv-forex-historical-data` (nur 6 Monate Stichprobe, keine
  Spreads, Kurse weichen im Überlappungszeitraum um ~90–100 Pips von FTMO ab; Herkunft unklar).
- Rohdateien nicht im Git (Größe). Prüfsummen: `SHA256SUMS`. Erneut beschaffen:
  `git clone --depth 1 https://github.com/Gianniskas/mt5-m1-bars-us500-eurusd-xauusd`.
