# Übergabebericht an den Strategie-Chat – Auftrag „EURUSD-Marktvermessung v1“ (2026-11-03)

## ⚠ Wichtig vorab: Das ist ein PROXY-Lauf, NICHT Eightcap
Die Cloud-Umgebung kommt nicht an Eightcap-MT5 heran (MT5 läuft nur unter Windows; Netzwerk-Policy
sperrt Eightcap und Dukascopy). Deshalb:
- **Pipeline komplett gebaut und getestet**, inkl. Eightcap-Exportskript (`scripts/mt5_export.py`).
- **Vermessen wurde eine echte MT5-Broker-Quelle als Ersatz:** FTMO-Server4, M1-Bars aus Broker-Ticks
  (Mid), 02.01.2025 – 15.05.2026 (355 Handelstage, 506 630 Minuten), mit Broker-Spreads und
  Symbolspezifikation. Kein Eightcap, nur ~16 Monate statt 2–3 Jahren, M1 statt Ticks.
- **Kommission und Swap von Eightcap: OFFEN** (nicht geschätzt).

## Befunde (Proxy, X = 10 Pips als Referenz; alle X im Bericht)
1. **Ausschlag vor X-Rücklauf = Zufallspfad-Verhalten → NEUTRAL.** MAE vor 10-Pip-Rücklauf:
   p50 7 · p90 23 · p99 45 · p99.9 64–76 · **Max 124 (Long) / 98 (Short) Pips**. Das ist fast exakt die
   Theorie eines driftlosen Zufallspfads (MAE ~ Exponential mit Mittel X: p99 = 4,6·X). Für alle X gilt
   grob: **p99 ≈ 4–5·X, Max ≈ 6–40·X** (X=3: Max 115 Pips = 38·X; X=20: Max 148 = 7·X).
   → Das Maximum hängt kaum von X ab (~100–150 Pips); es sind Ereignissprünge.
2. **Ohne Nachkauf (+X ab Einstieg) → SCHADET.** 3,8 % (Long) / 4,2 % (Short) der Einstiege erreichen
   +10 Pips nicht innerhalb von 30 Tagen; p99-MAE bis dahin 408 / 482 Pips, Max 507 / 839.
   (Zeitraum mit starkem EUR-Aufwärtstrend 1,03 → 1,20.)
3. **Stunde / Session / Wochentag → NEUTRAL (nicht stabil).** p99 je Serverstunde 40–62 Pips, aber die
   Rangfolge wiederholt sich zwischen erstem und zweitem Halbjahr kaum (Spearman 0,30–0,40; p90 sogar
   ≈ 0). Einzige halbwegs stabile Auffälligkeit: **Freitag Long** (p99 58 → 65 in beiden Hälften).
   Rollover (Serverstunde 0) ist v. a. ein **Kostenproblem**, nicht ein Ausschlagsproblem.
4. **Volatilitätsregime → NEUTRAL ex ante.** Vorab bekannte ATR (14 Vortage) trennt die Ausschläge
   **nicht** (p99 ruhigstes vs. wildestes Quintil 46 vs. 46 Pips). Erst die Range des laufenden Tages
   (ex post) trennt (38 → 53 Pips). Passt zur Theorie: Beim Zufallspfad ist die MAE vor X-Rücklauf
   unabhängig von der Volatilität – Vola ändert die **Dauer**, nicht die **Tiefe**.
5. **Trendtage → SCHADET; Früherkennung praktisch nicht möglich.** 19 % Trendtage, 28 % Rangetage,
   53 % Mischtage. Gegentrend-Einstiege an Trendtagen: p99 75 Pips (Long) / 53 (Short) vs. 46 / 42 an
   Rangetagen (Faktor 1,6). Früherkennung bis Serverstunde 10 (≈ 9 Uhr MEZ): AUC 0,59; die Regel
   „|Netto| ≥ 0,5·ATR bis 10 Uhr Server“ trifft nur 16 % Trendtage – **schlechter als die Basisrate 19 %**.
6. **Rückkehrneigung → HILFT, aber klein.** Varianz-Ratio < 1 und in beiden Halbjahren stabil:
   gesamt VR(60 min) = 0,93; **Asien 0,81, London 0,85**, Überlappung 0,89, NY 0,88. Halbwertszeit
   (240-min-Mittel) 97 min real vs. 111 min Zufallspfad. Ausnahme **Spät/Rollover (Serverstunde 0–2):
   VR(60) = 1,36** (Trendneigung, in beiden Halbjahren) – möglicherweise Rollover-Artefakt im Mid-Preis.
   Die Rückkehrneigung ist zu klein, um die Ausschlags-Tails (Befund 1) sichtbar zu verkürzen.
7. **Extremphasen → NEUTRAL (Tails wie Zufallspfad, aber ereignisgetrieben).** Längste Bewegung ohne
   10-Pip-Rücklauf: 135 Pips in ~11 min (23.03.2026, 11:56 MEZ, Auslöser unbekannt); ohne 20-Pip-Rücklauf:
   158 Pips (11.04.2025 Asien, Zollstreit). Top-Liste enthält NFP 01.08.2025 (124 Pips in 9 min),
   Zollpause 09.04.2025 (118 in 6 min), „Liberation Day“ 02.04.2025 (100), Wochenend-Gap 31.01.–03.02.2025 (126 Pips, Zölle Kanada/Mexiko).
   Viele dieser Sprünge liegen **außerhalb** der Standard-Daten-Slots (Abends/Nachts, Politik).
8. **Kosten (nur Spread, FTMO-Raw) → 0,2 Pips Median; Rollover 2,5 Pips (p90 4,8).** Nur-Spread-Grenzen:
   Kosten > 20 % bei Zielen < 1 Pip. **Mit Kommission (OFFEN)** verschiebt sich das stark: z. B. 7 USD RT
   je Lot (= 0,7 Pips, nur Szenario) → > 20 % bei Zielen < 4,5 Pips, > 30 % < 3,0, > 50 % < 1,8 Pips.
   In Serverstunde 0 frisst schon der Spread allein bei 12,5-Pip-Zielen 20 %.
   Swap (FTMO, nicht Eightcap): Long −1,07 Pips/Nacht, Short +0,04.

**Gesamtbild (Vorschlag zur Diskussion, keine Entscheidung):** EURUSD verhält sich auf Minuten- bis
Stundenskala sehr nah am Zufallspfad, mit leichter, stabiler Rückkehrneigung in Asien/London und
ereignisgetriebenen Ausreißern von 100–160 Pips ohne nennenswerten Rücklauf. Ein Nachkauf-System
gewinnt seine Kante also kaum aus „Rückkehr“, sondern müsste die Tail-Tiefe (~150 Pips Max bisher,
mehr in anderen Jahren möglich) kapitalseitig überleben – genau das adressiert der Round-Turn-Ansatz.

## Dateien
- Bericht (Befunde zuerst, Methodik danach): `EURUSD-Buckets/reports/2026-11-03_vermessung-v1_proxy-ftmo.md`
- Charts (22 PNG, Ausreißer rot/grün markiert): `EURUSD-Buckets/charts/2026-11-03_vermessung-v1_proxy-ftmo/`
  - Kern: `01_mae_ccdf_X10.png`, `01_mae_normiert.png`, `01b_defB_gewinn_ab_einstieg.png`,
    `02_stunde_server_X10.png`, `03_regime_X10.png`, `04_trend_range_tage.png`, `05_varianz_ratio.png`,
    `06_extreme_X10.png`, `07_spread_je_stunde.png`, `07_kostenanteil.png`, `00_datenqualitaet.png`
- Tabellen (CSV): `EURUSD-Buckets/results/2026-11-03_vermessung-v1_proxy-ftmo/`
- Datenherkunft: `EURUSD-Buckets/data/raw/proxy_ftmo_server4/PROVENANCE.md`

## Datenqualität (Proxy)
Keine Duplikate, keine inkonsistenten OHLC, keine Wochenend-Bars, keine Lücken > 5 min außer
Wochenende (73) und täglichem Rollover (290). 5 Eröffnungs-Gaps > 10 Pips (alle Montag 00:05, max.
115 Pips am 03.02.2025). 188 Spread-Spitzen > 5 Pips, 183 davon in Serverstunde 0.
Bar-Spreads nur in 0,1-Pip-Auflösung. Intrabar-Reihenfolge unbekannt → Sensitivität geprüft:
p99 ändert sich um 2–3 Pips (X=10), bei X=3 um ~3 Pips (11,8 → 14,8).

## Offene Fragen an den Strategie-Chat
1. **Eightcap-Daten:** Kannst du `scripts/mt5_export.py` auf dem Windows-Rechner laufen lassen (nur
   lesend) oder eine lokale Claude-Code-Session dort starten? Danach ist der Lauf ein Befehl
   (siehe `CLAUDE.md`).
2. **Kommission:** Welcher Eightcap-Kontotyp (Raw/Standard)? Ohne Deals im Konto liefert das
   Exportskript keine gemessene Kommission – dann bitte Kontospezifikation als Beleg.
3. **MAE-Definition:** Hauptmaß ist „Rücklauf X vom Extrem“ (Def. A). Zusätzlich „+X ab Einstieg“
   (Def. B). Welche passt zur geplanten Teilgewinnlogik – oder beide behalten?
4. **Trendtag-Definition** (Body/Range ≥ 0,7 und Close im äußeren 15 %-Band) – so übernehmen?
5. **Zeitraum:** Proxy deckt 2025–2026 (EUR-Aufwärtstrend). Für Eightcap 3 Jahre (ab Ende 2023) anfragen,
   um auch eine Seitwärts-/Abwärtsphase zu enthalten?
6. **Ereigniskalender:** FOMC/EZB-Termine sind nur Kandidaten aus Modellwissen. Soll ein echter
   Kalender-Export (z. B. aus MT5-Wirtschaftskalender) beschafft werden?
7. **Vorschlag zur Prüfung:** Rollover-Session (Serverstunde 0–2) zeigt Trendneigung (VR 1,36). Mit
   Eightcap-Bid/Ask-Ticks klären, ob das echt ist oder ein Mid-Preis-Artefakt der Spreadspitze.
