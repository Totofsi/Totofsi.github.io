"""Markdown-Bericht: Befunde zuerst, Methodik danach. Bewertungen regelbasiert
(Regeln im Abschnitt Methodik dokumentiert), damit Läufe auf anderen Märkten
vergleichbar sind."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

HILFT, SCHADET, NEUTRAL = "🟢 HILFT", "🔴 SCHADET", "⚪ NEUTRAL"


def md(df: pd.DataFrame, **kw) -> str:
    return df.to_markdown(index=False, floatfmt="g", **kw)


def _img(ctx, key, rep_path):
    rel = os.path.relpath(ctx["out_ch"] / ctx["charts"][key], rep_path.parent)
    return f"![{key}]({rel})"


def write_report(ctx: dict, rep_path: Path) -> Path:
    cfg = ctx["cfg"]
    X = ctx["main_x"]
    pcts = cfg["measurement"]["percentiles"]
    sA, sS, sB, sAf, theo = ctx["sA"], ctx["sS"], ctx["sB"], ctx["sAf"], ctx["theo"]
    q = ctx["quality"]
    L = []
    w = L.append
    findings = []

    src = ctx["args"].get("source_label") or ctx["args"]["name"]
    proxy = "eightcap" not in (src + ctx["args"]["name"]).lower()

    # ================================================================ M1
    def pval(df, x, side, col):
        return float(df[(df.X_pips == x) & (df.Seite == side)][col].iloc[0])
    r99 = np.mean([pval(sA, X, s, "p99") / pval(sS, X, s, "p99") for s in ("Long", "Short")])
    r999 = np.mean([pval(sA, X, s, "p99.9") / pval(sS, X, s, "p99.9") for s in ("Long", "Short")])
    rth = np.mean([pval(sA, X, s, "p99") / (X * np.log(100)) for s in ("Long", "Short")])
    v1 = HILFT if r99 < 0.93 else (SCHADET if r99 > 1.07 else NEUTRAL)
    mx_long, mx_short = pval(sA, X, "Long", "max"), pval(sA, X, "Short", "max")
    findings.append(("1 Ausschlag vor X-Rücklauf", v1,
                     f"MAE vor {X}-Pip-Rücklauf: p50 {pval(sA, X, 'Long', 'p50'):.1f}/{pval(sA, X, 'Short', 'p50'):.1f}, "
                     f"p99 {pval(sA, X, 'Long', 'p99'):.0f}/{pval(sA, X, 'Short', 'p99'):.0f}, "
                     f"Max {mx_long:.0f}/{mx_short:.0f} Pips (Long/Short). Verhältnis p99 real/Zufallspfad = {r99:.2f}, "
                     f"p99.9 = {r999:.2f}; real/Theorie-RW p99 = {rth:.2f}."))
    defb_c = pval(sB, X, "Long", "zensiert_%"), pval(sB, X, "Short", "zensiert_%")
    findings.append(("1b Gewinn +X ab Einstieg (ohne Nachkauf)", SCHADET if max(defb_c) > 1 else NEUTRAL,
                     f"Bis +{X} Pips ab Einstieg: p99-MAE {pval(sB, X, 'Long', 'p99'):.0f}/{pval(sB, X, 'Short', 'p99'):.0f} Pips; "
                     f"{defb_c[0]:.1f} % / {defb_c[1]:.1f} % der Einstiege erreichen +{X} nicht innerhalb von "
                     f"{cfg['measurement']['max_horizon_days']} Tagen (Long/Short). Ausschläge sind hier richtungs-/trendabhängig."))

    # ================================================================ M2
    g = ctx["g_hs"]; gx = g[g.X_pips == X]
    p99h = gx.groupby("hour_server")["p99"].max()
    hr_ratio = p99h.max() / p99h.min()
    worst = p99h.sort_values(ascending=False).head(3)
    best = p99h.sort_values().head(3)
    gse = ctx["g_se"]; gsx = gse[gse.X_pips == X].groupby("session", observed=True)["p99"].max()
    gwd = ctx["g_wd"]; gwx = gwd[gwd.X_pips == X].groupby("weekday", observed=True)["p99"].max()
    stab = ctx["stab"]
    rho_h = stab[(stab.Gruppierung == "hour_server") & (stab.Perzentil == 99)]["Spearman_H1_H2"].mean()
    rho_s = stab[(stab.Gruppierung == "session") & (stab.Perzentil == 99)]["Spearman_H1_H2"].mean()
    rho_w = stab[(stab.Gruppierung == "weekday") & (stab.Perzentil == 99)]["Spearman_H1_H2"].mean()
    v2 = HILFT if (hr_ratio >= 1.3 and rho_h >= 0.5) else NEUTRAL
    findings.append(("2 Stunde/Session/Wochentag", v2,
                     f"p99 (X={X}) je Serverstunde schwankt um Faktor {hr_ratio:.2f}: schlechteste Stunden "
                     + ", ".join(f"{h}h ({v:.0f})" for h, v in worst.items()) + "; beste "
                     + ", ".join(f"{h}h ({v:.0f})" for h, v in best.items())
                     + f". Sessions: höchstes p99 {gsx.idxmax()} ({gsx.max():.0f}), niedrigstes {gsx.idxmin()} ({gsx.min():.0f}). "
                     f"Wochentage: {gwx.idxmax()} am schlechtesten ({gwx.max():.0f}), {gwx.idxmin()} am besten ({gwx.min():.0f}). "
                     f"Stabilität (Spearman p99 erste vs. zweite Hälfte): Stunden {rho_h:.2f}, Sessions {rho_s:.2f}, "
                     f"Wochentage {rho_w:.2f} – "
                     + ("Muster wiederholt sich." if rho_h >= 0.5 else
                        "Stundenmuster wiederholt sich kaum (überwiegend von Einzelereignissen getrieben).")))

    # ================================================================ M3
    reg = ctx["reg"]
    ra = reg[(reg.X_pips == X) & (reg.Regimeart.str.startswith("ex ante"))].groupby("Regime")["p99"].max()
    rp = reg[(reg.X_pips == X) & (reg.Regimeart.str.startswith("ex post"))].groupby("Regime")["p99"].max()
    ratio_ante = ra.iloc[-1] / ra.iloc[0]
    ratio_post = rp.iloc[-1] / rp.iloc[0]
    v3 = HILFT if ratio_ante >= 1.25 else NEUTRAL
    findings.append(("3 Volatilitätsregime", v3,
                     f"p99 (X={X}) ex ante (ATR der Vortage): ruhigstes Quintil {ra.iloc[0]:.0f} → wildestes {ra.iloc[-1]:.0f} Pips "
                     f"(Faktor {ratio_ante:.2f}); ex post (Tagesrange): Faktor {ratio_post:.2f}. "
                     + ("Vorab bekanntes Regime trennt die Ausschläge brauchbar." if ratio_ante >= 1.25 else
                        "Vorab bekanntes Regime trennt die Ausschläge kaum; die Unterschiede zeigen sich erst ex post.")))

    # ================================================================ M4
    d = ctx["daily"]
    share = d["daytype"].value_counts(normalize=True) * 100
    auc = ctx["auc"]
    a_best = auc.loc[auc.groupby("bis_Serverstunde")["AUC"].idxmax()].set_index("bis_Serverstunde")
    auc10 = a_best["AUC"].get(10, np.nan)
    td = ctx["td"]; tdx = td[td.X_pips == X].groupby("Tagtyp")["p99"].max()
    ag = tdx.get("Trendtag gegen Trend", np.nan); rg = tdx.get("Rangetag", np.nan)
    v4 = SCHADET if ag / rg > 1.3 else NEUTRAL
    findings.append(("4 Trend- vs. Rangetage", v4,
                     f"Trendtage {share.get('Trendtag', 0):.0f} %, Rangetage {share.get('Rangetag', 0):.0f} %, "
                     f"Mischtage {share.get('Mischtag', 0):.0f} % ({len(d)} Tage). Gegentrend-Einstiege an Trendtagen: "
                     f"p99 {ag:.0f} Pips vs. Rangetage {rg:.0f} (Faktor {ag/rg:.2f}). Früherkennung: beste AUC bis "
                     f"Serverstunde 10 = {auc10:.2f} (0,5 = Zufall), bis 14 = {a_best['AUC'].get(14, np.nan):.2f}."))

    # ================================================================ M5
    vr = ctx["vr"]
    sig_lo = vr[(vr.Horizont_min > 1) & (vr.VR < vr["VR_Null_2.5%"])]
    sig_hi = vr[(vr.Horizont_min > 1) & (vr.VR > vr["VR_Null_97.5%"])]
    all_ = vr[vr.Session == "Alle"].set_index("Horizont_min")
    vq = vr[vr.Horizont_min > 1]
    both_lo = int(((vq["VR_1.Hälfte"] < 1) & (vq["VR_2.Hälfte"] < 1) & (vq.VR < vq["VR_Null_2.5%"])).sum())
    both_hi = int(((vq["VR_1.Hälfte"] > 1) & (vq["VR_2.Hälfte"] > 1) & (vq.VR > vq["VR_Null_97.5%"])).sum())
    v5 = HILFT if both_lo > both_hi + 2 else (SCHADET if both_hi > both_lo + 2 else NEUTRAL)
    hl = ctx["hl"]
    hlA = hl[(hl.Session == "Alle")].pivot(index="Fenster_min", columns="Reihe", values="Halbwertszeit_min")
    findings.append(("5 Rückkehrneigung", v5,
                     "VR(5/15/60) gesamt = " + "/".join(f"{all_.loc[h, 'VR']:.3f}" for h in all_.index if h > 1)
                     + f"; signifikant < 1 (Rückkehr) in {len(sig_lo)}, signifikant > 1 (Trend) in {len(sig_hi)} "
                     f"von {len(vr[vr.Horizont_min > 1])} Session×Horizont-Zellen; davon in beiden Halbjahren gleichgerichtet: "
                     f"{both_lo} (<1) bzw. {both_hi} (>1). Effektgröße klein: VR 0,93 auf 60 min heißt ~3,6 % weniger "
                     f"Schwankungsbreite (Std.) als ein Zufallspfad. AC1(1 min) gesamt = {all_.loc[1, 'AC1']:.4f}. "
                     "Halbwertszeit real vs. Zufallspfad: " + "; ".join(
                         f"{W} min-Mittel {r['real']:.0f} vs {r['Zufallspfad']:.0f} min" for W, r in hlA.iterrows()) + "."))

    # ================================================================ M6
    ext = ctx["ext"]
    xs6 = sorted(ext)
    e_main = ext[xs6[0]]
    b = pd.read_csv(ctx["out_res"] / f"m6_beinverteilung_X{xs6[0]:02d}.csv").set_index("stat")
    ratio6 = b.loc["max", "real"] / b.loc["max", "zufallspfad"]
    v6 = SCHADET if ratio6 > 1.3 else NEUTRAL
    top = e_main.iloc[0]
    findings.append(("6 Extremphasen", v6,
                     f"Längste Einbahnbewegung ohne {xs6[0]}-Pip-Rücklauf: {top['Länge_Pips']:.0f} Pips ({top['Richtung']}, "
                     f"Start {top['Start_MEZ']} MEZ, {top['Dauer_h']:.1f} h). Längstes Bein real/Zufallspfad = {ratio6:.2f}; "
                     f"p99 der Beinlänge real {b.loc['p99', 'real']:.0f} vs. {b.loc['p99', 'zufallspfad']:.0f} Pips. "
                     f"{(e_main['Ereignis_im_Fenster'] != '').sum()} der Top-{len(e_main)} enthalten einen Daten-/Ereignis-Slot."))

    # ================================================================ M7
    sp = ctx["sp_h"]
    if sp is not None:
        med = sp["Spread_Median"]
        typ = float(med.median())
        comm = cfg["costs"]["commission_per_lot_per_side"]
        comm_txt = ("Kommission OFFEN (nicht aus Eightcap-Kontodaten belegt)" if np.isnan(comm)
                    else f"Kommission {2*comm:.2f} USD RT/Lot")
        findings.append(("7 Kosten pro Zyklus", NEUTRAL,
                         f"Spread-Median typische Stunde {typ:.2f} Pips (günstigste {med.idxmin()}h {med.min():.2f}, "
                         f"teuerste {med.idxmax()}h {med.max():.2f}). Nur Spread: Kosten > 20 % ab Ziel < {typ/0.2:.1f} Pips, "
                         f"> 30 % ab < {typ/0.3:.1f}, > 50 % ab < {typ/0.5:.1f} Pips. {comm_txt}; bei 7 USD RT/Lot "
                         f"(= 0,70 Pips, nur Szenario) verschieben sich die Grenzen auf {(typ+0.7)/0.2:.1f} / {(typ+0.7)/0.3:.1f} / "
                         f"{(typ+0.7)/0.5:.1f} Pips."))

    # ================================================================ Kopf
    w(f"# Marktvermessung {cfg['market']['symbol']} – Lauf `{ctx['tag']}`\n")
    if proxy:
        w("> **⚠ PROXY-LAUF – NICHT EIGHTCAP.** Dieser Lauf nutzt eine öffentlich verfügbare MT5-Broker-Datenquelle, "
          "weil die Eightcap-Ticks in der Cloud-Umgebung nicht zugänglich sind. Alle Zahlen gelten für diese Quelle; "
          "Kommission/Swap von Eightcap sind **nicht** enthalten. Der Lauf ist mit Eightcap-Ticks 1:1 wiederholbar "
          "(siehe `CLAUDE.md`, Abschnitt Datenquellen).\n")
    w(f"- **Quelle:** {src}  ")
    w(f"- **Datenart:** {'Ticks (Bid/Ask) → 1-s-Basis' if ctx['kind']=='ticks' else 'M1-Bars (Mid), Intrabar-Reihenfolge unbekannt'}  ")
    w(f"- **Zeitraum (UTC):** {q['zeitraum_utc']} · {q['handelstage']} Handelstage · {q['m1_bars']:,} M1-Bars · "
      f"{ctx['n_entries']:,} Einstiegspunkte je Seite  ")
    w(f"- **Konfiguration:** `{Path(cfg['_path']).name}` · X = {cfg['measurement']['targets_pips']} Pips · "
      f"Kappung {cfg['measurement']['max_horizon_days']} Tage\n")

    w("## Befunde (Kurzfassung)\n")
    w("| Messung | Bewertung für Nachkauf-System | Kernaussage |\n|---|---|---|")
    for name, v, txt in findings:
        w(f"| {name} | {v} | {txt} |")
    w("\nBewertungsregeln siehe Methodik (M-Regeln). „Zufallspfad“ = gleiche Daten, Minutenbewegungen innerhalb "
      "jedes Tages zufällig gemischt (gleiche Volatilität, keine Trend-/Rückkehrstruktur).\n")

    # ================================================================ Details
    w("---\n## Messung 1 – Ausschlagsverteilung (MAE vor X-Pip-Rücklauf)\n")
    w("**Def. A (Hauptmaß):** Einstieg zu jeder Minute; MAE = größter Gegenlauf, bevor der Kurs X Pips vom "
      "tiefsten (Long) bzw. höchsten (Short) Punkt zurückkommt. Werte in Pips.\n")
    w(md(sA) + "\n")
    w("**Zufallspfad-Benchmark (Shuffle):**\n")
    w(md(sS[["X_pips", "Seite"] + [f"p{p}" for p in pcts] + ["max"]]) + "\n")
    w("**Theorie Random Walk** (MAE ~ Exponential mit Mittel X, Perzentil p = −X·ln(1−p)):\n")
    w(md(theo) + "\n")
    w("**Sensitivität Intrabar-Reihenfolge** (Erholung vor Gegenlauf im selben Bar, optimistisch):\n")
    w(md(sAf[["X_pips", "Seite"] + [f"p{p}" for p in pcts] + ["max"]]) + "\n")
    w(_img(ctx, "norm", rep_path) + "\n")
    w(_img(ctx, f"ccdf_{X}", rep_path) + "\n")
    w("Weitere X: " + ", ".join(f"[X={x}]({os.path.relpath(ctx['out_ch'] / ctx['charts'][f'ccdf_{x}'], rep_path.parent)})"
                                for x in cfg["measurement"]["targets_pips"]) + "\n")
    w("**Def. B (Zusatz):** MAE, bis der Kurs **+X ab Einstieg** erreicht (eine Position, kein Nachkauf):\n")
    w(md(sB) + "\n")
    w(_img(ctx, "defb", rep_path) + "\n")
    w(f"**Aussage:** {findings[0][1]} – {findings[0][2]}\n")

    w("---\n## Messung 2 – nach Stunde, Session, Wochentag\n")
    piv = gx.pivot_table(index="hour_server", columns="Seite", values=["p50", "p90", "p99", "max"])
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    w(f"MAE vor {X}-Pip-Rücklauf je Einstiegsstunde (Serverzeit; MEZ = Server − 1 h ganzjährig bei NY-Close-Server, "
      f"außer in den DST-Lücken März/Okt–Nov):\n")
    w(piv.reset_index().to_markdown(index=False, floatfmt="g") + "\n")
    w(_img(ctx, f"hs_{X}", rep_path) + "\n")
    w(_img(ctx, "hm", rep_path) + "\n")
    w("**Sessions:**\n")
    w(md(gse[gse.X_pips == X]) + "\n")
    w(_img(ctx, "se", rep_path) + "\n")
    w("**Wochentage:**\n")
    w(md(gwd[gwd.X_pips == X]) + "\n")
    w(_img(ctx, "wd", rep_path) + "\n")
    w("**Stabilität** (gleiche Rangfolge in erster und zweiter Hälfte des Zeitraums?):\n")
    w(md(ctx["stab"]) + "\n")
    w(f"Alle X und Gruppen: `{os.path.relpath(ctx['out_res'], rep_path.parent)}/m2_*.csv`\n")
    w(f"**Aussage:** {findings[2][1]} – {findings[2][2]}\n")

    w("---\n## Messung 3 – Volatilitätsregime\n")
    w("Tagesrange (Serverstunde 0–24) und ATR14 = Mittel der 14 Vortages-Ranges (ohne Vorschau). "
      "Quintile über den Zeitraum.\n")
    w(md(reg[reg.X_pips == X]) + "\n")
    w(_img(ctx, "reg", rep_path) + "\n")
    w(f"**Aussage:** {findings[3][1]} – {findings[3][2]}\n")

    w("---\n## Messung 4 – Trend- vs. Rangetage\n")
    w("Klassifikation je Servertag: **Trendtag** = |Close−Open|/Range ≥ 0,70 und Close im äußeren 15 %-Band in "
      "Bewegungsrichtung; **Rangetag** = |Close−Open|/Range ≤ 0,30; sonst **Mischtag**. Zusätzlich Effizienz = "
      "|Netto| / Summe |ΔM1| (in `m3_m4_tage.csv`).\n")
    w(md(d["daytype"].value_counts().rename_axis("Tagtyp").reset_index(name="Tage")) + "\n")
    w(f"Effizienz-Ratio (Netto/Gesamtweg) Median: Trendtage {d[d.daytype=='Trendtag']['eff_ratio'].median():.3f}, "
      f"Rangetage {d[d.daytype=='Rangetag']['eff_ratio'].median():.3f}, alle {d['eff_ratio'].median():.3f}.\n")
    w("**MAE je Tagtyp** (Einstiege dieses Tages):\n")
    w(md(td[td.X_pips == X]) + "\n")
    w("**Früherkennung** – Trennschärfe von Teiltagesmerkmalen (bis Serverstunde h) für „Trendtag“:\n")
    w(md(auc.pivot(index="bis_Serverstunde", columns="Merkmal", values="AUC").reset_index()) + "\n")
    w(md(ctx["rules"]) + "\n")
    w("Hinweis: Die Tagesklasse nutzt den ganzen Tag (Rückschau). Die MAE-Werte je Tagtyp zeigen, wie teuer "
      "Trendtage sind, nicht, dass man sie vorab meiden kann – dafür zählt nur die Früherkennung.\n")
    w("Hinweis: Teiltag ist Teil des Tages – AUC enthält mechanische Überlappung; späte Stunden sind daher kaum "
      "noch „Früh“-Erkennung.\n")
    w(_img(ctx, "days", rep_path) + "\n")
    w(f"**Aussage:** {findings[4][1]} – {findings[4][2]}\n")

    w("---\n## Messung 5 – Rückkehrneigung\n")
    w("Varianz-Ratio VR(q) = Var(q-min-Rendite)/(q·Var(1-min-Rendite)); < 1 = Rückkehrneigung, > 1 = Trendneigung. "
      f"AC1 = Autokorrelation aufeinanderfolgender q-min-Renditen. 95 %-Band aus {ctx['args']['n_shuffle']} Zufallspfaden.\n")
    w(md(vr) + "\n")
    w(_img(ctx, "vr", rep_path) + "\n")
    w("**Halbwertszeit** der Abweichung vom gleitenden Mittel (AR(1) auf 1-min-Basis), real vs. Zufallspfad "
      "(der gleitende Mittelwert erzeugt auch beim Zufallspfad eine scheinbare Rückkehr – nur die Differenz zählt):\n")
    w(md(hl) + "\n")
    w(_img(ctx, "hl", rep_path) + "\n")
    w(f"**Aussage:** {findings[5][1]} – {findings[5][2]}\n")

    w("---\n## Messung 6 – Extremphasen\n")
    for x, e in ext.items():
        w(f"**Top {len(e)} Einbahnbewegungen ohne {x}-Pip-Rücklauf:**\n")
        e2 = e.copy(); e2.index = np.arange(1, len(e2) + 1)
        w(e2.reset_index(names="#").to_markdown(index=False) + "\n")
        bb = pd.read_csv(ctx["out_res"] / f"m6_beinverteilung_X{x:02d}.csv")
        w(md(bb) + "\n")
        w(_img(ctx, f"ext_{x}", rep_path) + "\n")
    w("„Ereignis_im_Fenster“: regelbasierte Slots (US-Daten 08:30 ET, NFP = 1. Freitag) und ggf. ein mitgegebener "
      "Kalender. Ein Slot im Fenster ist ein **Hinweis, kein Beleg** für den Auslöser.\n")
    w(f"**Aussage:** {findings[6][1]} – {findings[6][2]}\n")

    w("---\n## Messung 7 – Kosten pro Zyklus\n")
    if sp is not None:
        w("Hinweis Auflösung: Bar-Spreads sind ganze Points (1 Point = 0,1 Pip); Median-Werte springen daher in "
          "0,1-Pip-Stufen – der Mittelwert ist feiner. Tickdaten liefern exakte Spreads.\n")
        w("Spread je Serverstunde (Pips). Kosten pro Zyklus = 1 × Spread (Kauf zu Ask, Verkauf zu Bid) + Kommission "
          "(Round-Turn). Slippage nicht enthalten.\n")
        w(sp.reset_index().to_markdown(index=False, floatfmt="g") + "\n")
        w(_img(ctx, "spread", rep_path) + "\n")
        for label, t in ctx["cost"].items():
            w(f"**Ziel-Schwellen – {label}** (Ziel kleiner als Wert ⇒ Kosten über Anteil):\n")
            w(md(t) + "\n")
        w(_img(ctx, "costshare", rep_path) + "\n")
    spec = ctx["spec"]
    if spec:
        w("**Symbolspezifikation der Datenquelle (Swap etc.):**\n")
        keys = [k for k in ["name", "spread", "trade_contract_size", "point", "digits", "swap_mode", "swap_long",
                            "swap_short", "swap_rollover3days", "commission"] if k in spec]
        w(pd.DataFrame([{k: spec[k] for k in keys}]).to_markdown(index=False) + "\n")
        if spec.get("swap_mode") in (1, "1"):
            pt = 10 ** (-cfg["market"]["digits"])
            w(f"swap_mode 1 = Punkte → Swap Long {float(spec['swap_long'])*pt/cfg['market']['pip_size']:.3f} Pips/Nacht, "
              f"Short {float(spec['swap_short'])*pt/cfg['market']['pip_size']:.3f} Pips/Nacht (dreifach am Mittwoch, "
              "sofern Broker-Standard). **Gilt für diese Quelle, nicht für Eightcap.**\n")
    w(f"**Aussage:** {findings[7][1] if len(findings) > 7 else ''} – {findings[7][2] if len(findings) > 7 else 'keine Spreaddaten'}\n")

    # ================================================================ Qualität
    w("---\n## Datenqualität\n")
    qq = {k: v for k, v in q.items()}
    w("| Prüfung | Ergebnis |\n|---|---|")
    for k, v in qq.items():
        w(f"| {k} | {v} |")
    w("")
    if len(ctx["gaps"]):
        w("**Größte Lücken außerhalb Wochenende/Rollover** (Serverzeit):\n")
        w(md(ctx["gaps"]) + "\n")
    w(_img(ctx, "quality", rep_path) + "\n")

    # ================================================================ Methodik
    w("---\n## Methodik\n")
    w(METHODIK)
    rep_path.parent.mkdir(parents=True, exist_ok=True)
    rep_path.write_text("\n".join(L), encoding="utf-8")
    return rep_path


METHODIK = """
**Zeit:** intern UTC. Serverzeit = New York + 7 h (GMT+2/+3, Tageswechsel = NY 17:00; Eightcap-Standard).
MEZ = Europe/Berlin (inkl. Sommerzeit). Sessions in Ortszeit (DST-korrekt): Asien = Tokio 09–18 JST ohne London/NY;
London = London 08–17 ohne NY; Überlappung = London und NY 08–17 ET gleichzeitig; New York = NY ohne London;
Spät/Rollover = Rest (NY-Nachmittag bis Tokio-Öffnung, enthält Rollover 23–01 Server).

**Einstiege:** jede Minute (Close des M1-Bars bzw. letzter Tick der Minute), Long und Short. Preise = Mid (Ticks)
bzw. gelieferte Bar-Preise; Kosten werden getrennt in Messung 7 betrachtet (MAE ist spreadfrei).

**Def. A (Hauptmaß, Nachkauf-relevant):** Long: laufendes Minimum m ab Einstieg; Ende, sobald Kurs ≥ m + X.
MAE = Einstieg − m. Short gespiegelt. **Def. B:** Ende erst bei Einstieg + X. Kappung nach 30 Kalendertagen →
„zensiert“ (MAE bis dahin, als Untergrenze in Perzentilen; enthält auch Einstiege kurz vor Datenende). Wochenenden werden durchlaufen (Position bleibt offen).

**Intrabar (nur Bar-Daten):** Standard „adverse first“ (Long: O→L→H→C). Sensitivität „favorable first“
(O→H→L→C) im Bericht. Mit Tickdaten (1-s-Basis) entfällt die Unschärfe praktisch.

**Zufallspfad-Benchmark:** Bar-Formen (High/Low/Close relativ zum Vor-Close) innerhalb jedes Servertages zufällig
permutiert. Erhält Tagesvolatilität, Bar-Ranges, Tageslücken; zerstört Trend/Rückkehr innerhalb des Tages.
Theorie (Brownsche Bewegung ohne Drift): MAE vor X-Rücklauf ist exponentialverteilt mit Mittel X,
unabhängig von der Volatilität.

**Regime:** Tagesrange je Servertag (≥ 600 M1-Bars), ATR14 = Mittel der 14 Vortage (ex ante). Quintile.

**Rückkehrneigung:** 1-min-Raster (Lücken ≤ 30 min vorwärts gefüllt), nur Renditen innerhalb eines Servertags.
VR mit überlappenden q-Renditen; AC1 nicht überlappend. Nullband: n Permutationen der 1-min-Renditen innerhalb
des Tages. Halbwertszeit: d_t = log P − gleitendes Mittel(W); d_{t+1} = β·d_t; HWZ = −ln2/ln β.

**Extremphasen:** ZigZag mit Umkehrschwelle X auf M1-High/Low; Bein = Bewegung ohne X-Rücklauf.

**Kosten:** Spread je Serverstunde (Median/p90/p99 über Bars). Ziel-Schwelle für Kostenanteil s: Ziel < Kosten/s.
Kommission nur, wenn in der Konfiguration belegt; sonst Szenarien (ausdrücklich keine Annahme).

**Bewertungsregeln (M-Regeln):**
- M1: p99 real/Zufallspfad < 0,93 → HILFT, > 1,07 → SCHADET, sonst NEUTRAL. M1b: zensiert > 1 % → SCHADET.
- M2: max/min p99 über Stunden ≥ 1,3 **und** Halbjahres-Stabilität (Spearman p99) ≥ 0,5 → HILFT (als Zeitfilter nutzbar), sonst NEUTRAL.
- M3: p99 wildestes/ruhigstes Quintil ex ante ≥ 1,25 → HILFT (vorab skalierbar), sonst NEUTRAL.
- M4: p99 gegen Trend an Trendtagen / Rangetage > 1,3 → SCHADET, sonst NEUTRAL.
- M5: Zellen (Session×Horizont), die signifikant < 1 sind **und** in beiden Halbjahren < 1 liegen, übersteigen die entsprechenden > 1-Zellen um > 2 → HILFT (umgekehrt SCHADET).
- M6: längstes Bein real/Zufallspfad > 1,3 → SCHADET (fette Schwänze), sonst NEUTRAL.
- M7: ohne Bewertung (reine Kostengrenzen).
"""
