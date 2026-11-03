# CLAUDE.md – Projekt EURUSD-Buckets (Marktvermessung)

> Jede neue Session liest zuerst diese Datei und danach `STATUS.md`.

## Ziel
Vermessung von EURUSD (später weitere Märkte) für ein geplantes **Bucket-/Nachkauf-System**:
Nachkauf bei Gegenbewegung, Teilgewinne, Kapital-Round-Turns (Einsatz K, Ziel = Vielfaches von K,
dann Abzug und Neustart; Totalverlust pro Round-Turn einkalkuliert).
Ein solches System ist nur profitabel, wenn der Markt messbar zur Rückkehr neigt und die Kosten pro
Zyklus klein sind. **Dieses Projekt misst genau das – noch kein EA, keine Signale, keine Optimierung.**

## Arbeitsweise
- **Rollen:** Strategie und Entscheidungen entstehen im **Strategie-Chat**. Claude Code setzt um:
  Daten beschaffen, vermessen, testen, später EA-Code schreiben. Claude Code trifft **keine eigenen
  Strategieentscheidungen**; Auffälligkeiten werden im Bericht als **Vorschlag** formuliert.
- `STATUS.md` nach **jedem** Auftrag aktualisieren (erledigt / offen / Befunde / Entscheidungen des
  Strategie-Chats).
- Jeder Auftrag endet mit einem **Übergabebericht** für den Strategie-Chat (`reports/<datum>_uebergabe_<name>.md`):
  kurze Befundliste, Pfade zu Bericht und Charts, offene Fragen.
- Ergebnisse **versioniert pro Auftrag** (`<datum>_<name>`), **nichts überschreiben**. Der Runner legt
  bei Namenskollision automatisch `_v2`, `_v3` … an.
- **Nichts schätzen, alles belegen.** Fehlt ein Beleg (z. B. Kommission), wird der Wert als OFFEN
  geführt; Szenarien sind als Szenarien gekennzeichnet.
- Freigaben: selbstständig im Projektordner arbeiten, Pakete installieren, Skripte ausführen,
  MT5-Daten exportieren. **Rückfrage nur** bei Löschungen außerhalb des Projektordners oder Aktionen
  am Live-Konto.
- Nicht tun (aktueller Auftragsstand): keine Strategie optimieren, keine Bucket-Parameter festlegen,
  kein EA-Code.

## Datenquellen
| Quelle | Status | Pfad |
|---|---|---|
| **Eightcap MT5 Real-Ticks** (Soll-Quelle, 2–3 Jahre) | **OFFEN** – nur lokal auf Windows mit MT5 exportierbar | `data/raw/eightcap/` via `scripts/mt5_export.py` |
| Eightcap Kommission / Swap | **OFFEN** – kommt aus `mt5_export.py` (symbol_info + Deal-Historie) | `data/raw/eightcap/EURUSD_symbol_spec.json` |
| FTMO-Server4 MT5, M1 aus Broker-Ticks (Mid), 2025-01-02 – 2026-05-15 | Proxy, genutzt im Lauf vom 2026-11-03 | `data/raw/proxy_ftmo_server4/` (Herkunft: `PROVENANCE.md`) |
| Ereignis-Kandidaten (FOMC/EZB/Zölle) | aus Modellwissen, **unverifiziert** | `data/reference/ereignisse_kandidaten.csv` |

Die Cloud-Umgebung (Claude Code im Web) erreicht weder Eightcap noch Dukascopy (Netzwerk-Policy);
MT5 läuft dort nicht. Eightcap-Daten müssen auf dem Windows-Rechner exportiert und in
`data/raw/eightcap/` abgelegt (oder dort direkt ausgewertet) werden.

### Eightcap-Lauf (Soll)
```powershell
pip install MetaTrader5 pandas pyarrow numpy numba matplotlib scipy tabulate
python scripts/mt5_export.py --symbol EURUSD --years 3 --out data/raw/eightcap
# Kommission aus EURUSD_symbol_spec.json -> commission_measured in config/EURUSD.toml eintragen
python scripts/run_vermessung.py --config config/EURUSD.toml --kind ticks `
  --input "data/raw/eightcap/EURUSD_ticks_*.parquet" `
  --spec data/raw/eightcap/EURUSD_symbol_spec.json `
  --events data/reference/ereignisse_kandidaten.csv `
  --name vermessung-v1_eightcap --source-label "Eightcap MT5 Real-Ticks"
```

## Kostenannahmen
- **Spread:** gemessen aus Daten (Ticks: Ask−Bid je Tick; Bars: MT5-Spalte `spread` in Points).
- **Kommission:** `config/EURUSD.toml` → `commission_per_lot_per_side`. Steht auf `nan` (= OFFEN), bis
  aus Eightcap-Kontodaten belegt. Szenarien 0/5/7 USD RT je Lot nur zur Darstellung.
- **Swap:** aus `symbol_info` (swap_mode, swap_long, swap_short, swap_rollover3days). Proxy-Werte gelten
  nicht für Eightcap.
- **Slippage:** nicht modelliert (mit Ticks später messbar).
- Pip EURUSD = 0,0001; 1 Lot = 100 000 EUR → 10 USD je Pip.

## Zeitkonventionen
Intern UTC. Serverzeit = New York + 7 h (GMT+2/+3, Tageswechsel NY 17:00) – Eightcap- und FTMO-Standard.
MEZ = Europe/Berlin. Sessions in Ortszeit (DST-korrekt), Details in `scripts/bmlib/timeutil.py`.
Achtung: Die FTMO-Proxydateien sind laut deren README „UTC“, tatsächlich aber Serverzeit
(keine Sonntagsbars, Freitag bis 23:59) – in der Konfiguration so behandelt.

## Ordnerstruktur
```
EURUSD-Buckets/
  CLAUDE.md, STATUS.md
  config/<SYMBOL>.toml          Marktparameter (Pip, Zeitzone, X-Werte, Kosten) – für neue Märkte kopieren
  data/raw/<quelle>/            Rohdaten (nicht im Git, nur PROVENANCE/SHA256SUMS/Spezifikation)
  data/reference/               Kalender, Referenztabellen
  scripts/run_vermessung.py     kompletter Lauf Messungen 1–7 + Bericht
  scripts/mt5_export.py         Eightcap-Export (Windows, nur lesend)
  scripts/bmlib/                Bibliothek: dataio, timeutil, kernels (numba), measure, charts, report
  tests/test_kernels.py         Methodentests (Random-Walk-Theorie, Handbeispiele)
  results/<datum>_<name>/       CSV-Tabellen, quality.json, summary.json
  charts/<datum>_<name>/        PNG-Charts
  reports/<datum>_<name>.md     Bericht; reports/<datum>_uebergabe_<name>.md Übergabe
```

## Weitere Märkte
`config/EURUSD.toml` kopieren (z. B. `GBPUSD.toml`), `symbol`, `pip_size`, `digits`, ggf. X-Werte und
Sessions anpassen; für Indizes `pip_size` = Indexpunkt setzen. Runner unverändert verwenden.
