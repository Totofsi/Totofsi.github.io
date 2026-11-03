# STATUS – EURUSD-Buckets

_Letzte Aktualisierung: 2026-11-03 (Auftrag „Marktvermessung v1“)_

## Erledigt
- [x] Projektordner, `CLAUDE.md`, `STATUS.md`, Ordnerstruktur, `.gitignore` (Rohdaten nicht im Git).
- [x] Wiederverwendbare Pipeline `scripts/run_vermessung.py` + `scripts/bmlib/` (Messungen 1–7,
      Datenqualität, Charts, Markdown-Bericht mit regelbasierten Bewertungen); marktunabhängig über
      `config/<SYMBOL>.toml`.
- [x] Eightcap-Exportskript `scripts/mt5_export.py` (Ticks monatsweise, symbol_info inkl. Swap,
      Kommission aus Deal-Historie; nur lesend). **Noch nicht ausgeführt** (braucht Windows + MT5).
- [x] Methodentests `tests/test_kernels.py` (Random-Walk-Theorie, Handbeispiele, ZigZag) – bestanden.
- [x] **Proxy-Lauf** auf FTMO-Server4-M1-Daten (2025-01-02 – 2026-05-15):
      Bericht `reports/2026-11-03_vermessung-v1_proxy-ftmo.md`, Charts
      `charts/2026-11-03_vermessung-v1_proxy-ftmo/`, Tabellen `results/2026-11-03_vermessung-v1_proxy-ftmo/`.
- [x] Übergabebericht `reports/2026-11-03_uebergabe_vermessung-v1.md`.

## Offen
- [ ] **Eightcap-Ticks exportieren** (2–3 Jahre) und Lauf `--kind ticks` wiederholen.
- [ ] **Eightcap-Kommission belegen** (Deal-Historie oder Kontospezifikation) → `config/EURUSD.toml`.
- [ ] **Eightcap-Swap** (long/short, swap_mode, Dreifach-Tag) aus Export übernehmen.
- [ ] Echter Ereigniskalender statt Kandidatenliste (`data/reference/ereignisse_kandidaten.csv`).
- [ ] Rollover-Trendneigung (VR 1,36, Serverstunde 0–2) mit Bid/Ask-Ticks auf Artefakt prüfen.
- [ ] Slippage-Messung (erst mit Ticks/Live-Ausführungen möglich).
- [ ] Weitere Märkte (GBPUSD, Indizes) – Config kopieren, sobald gewünscht.

## Befunde (Proxy FTMO, nicht Eightcap)
| # | Messung | Bewertung | Kurz |
|---|---|---|---|
| 1 | MAE vor X-Rücklauf | NEUTRAL | entspricht Zufallspfad (p99 ≈ 4,6·X); Max 98–148 Pips, kaum X-abhängig |
| 1b | +X ab Einstieg | SCHADET | 3,8–4,2 % erreichen +10 nicht in 30 Tagen |
| 2 | Stunde/Session/Tag | NEUTRAL | Unterschiede vorhanden, aber zwischen Halbjahren nicht stabil; Freitag-Long auffällig |
| 3 | Vola-Regime | NEUTRAL | ex ante keine Trennung (46 vs. 46 Pips p99); ex post 38 → 53 |
| 4 | Trendtage | SCHADET | 19 % Trendtage, Gegentrend-p99 ×1,6; Früherkennung ≈ Zufall |
| 5 | Rückkehrneigung | HILFT (klein) | VR(60) 0,93 gesamt, Asien 0,81, London 0,85, stabil; Rollover 1,36 |
| 6 | Extremphasen | NEUTRAL | Tails wie Zufallspfad; Top-Bewegungen 100–160 Pips, ereignisgetrieben |
| 7 | Kosten | – | Spread 0,2 Pips (Rollover 2,5); Kommission OFFEN |

## Entscheidungen des Strategie-Chats
_(noch keine – siehe offene Fragen im Übergabebericht)_
