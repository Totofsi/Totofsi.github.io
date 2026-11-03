"""PNG-Charts (matplotlib). Einheitliche Farben, Ausreißer markiert."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LONG = "#2a78d6"
SHORT = "#eb6834"
BENCH = "#8a8984"
THEORY = "#52514e"
POS = "#008300"     # positiver Ausreißer (gut für Nachkauf-System)
NEG = "#e34948"     # negativer Ausreißer (schlecht)
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SIDE_COL = {"Long": LONG, "Short": SHORT}

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 160, "font.size": 9.5, "axes.titlesize": 11,
    "axes.titleweight": "bold", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#e4e3df", "grid.linewidth": 0.6, "axes.edgecolor": "#8a8984",
    "axes.labelcolor": "#2b2a27", "xtick.color": "#52514e", "ytick.color": "#52514e",
    "legend.frameon": False, "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
})


def _save(fig, path: Path, note: str | None = None):
    if note:
        fig.text(0.01, 0.005, note, fontsize=7.5, color="#6b6a66", ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03 if note else 0, 1, 1))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path.name


def _annot(ax, x, y, text, color):
    ax.annotate(text, (x, y), xytext=(0, 9), textcoords="offset points", ha="center",
                fontsize=8, color=color, fontweight="bold")


# ------------------------------------------------------------- Messung 1
def mae_ccdf(res_real, res_shuf, x, path, note):
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    grid = np.linspace(0, 12 * x, 400)
    for side in ("Long", "Short"):
        mae = np.sort(res_real[(x, side)][0])
        p = 1 - np.searchsorted(mae, grid, side="right") / len(mae)
        ax.semilogy(grid, np.maximum(p, 1e-7), color=SIDE_COL[side], lw=2, label=f"{side} real")
        ms = np.sort(res_shuf[(x, side)][0])
        ps = 1 - np.searchsorted(ms, grid, side="right") / len(ms)
        ax.semilogy(grid, np.maximum(ps, 1e-7), color=SIDE_COL[side], lw=1, ls=":", label=f"{side} Zufallspfad (Shuffle)")
    ax.semilogy(grid, np.exp(-grid / x), color=THEORY, lw=1.2, ls="--", label="Theorie Random Walk: exp(−MAE/X)")
    for side in ("Long", "Short"):
        mx = res_real[(x, side)][0].max()
        ax.plot([mx], [1 / len(res_real[(x, side)][0])], "v", color=NEG, ms=8)
        _annot(ax, mx, 1 / len(res_real[(x, side)][0]), f"Max {side} {mx:.0f}", NEG)
    ax.set_ylim(1e-6, 1.2)
    ax.set_xlabel(f"MAE (Pips) vor {x} Pips Rücklauf")
    ax.set_ylabel("Anteil Einstiege mit MAE > Wert")
    ax.set_title(f"Messung 1 – Ausschlag vor {x}-Pip-Rücklauf: real vs. Zufallspfad")
    ax.legend(fontsize=8, loc="upper right")
    return _save(fig, path, note)


def mae_normalized(summary_real, summary_shuf, pcts, path, note):
    """MAE-Perzentile in Vielfachen von X; Theorie -ln(1-p)."""
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    xs = np.arange(len(pcts))
    theory = [-np.log(1 - p / 100) for p in pcts]
    ax.plot(xs, theory, color=THEORY, ls="--", lw=1.5, marker="", label="Theorie Random Walk")
    markers = {3: "o", 5: "s", 10: "^", 20: "D"}
    for _, r in summary_real.iterrows():
        vals = [r[f"p{p}"] / r["X_pips"] for p in pcts]
        ax.plot(xs, vals, color=SIDE_COL[r["Seite"]], marker=markers.get(r["X_pips"], "o"), lw=1, ms=5,
                alpha=0.85, label=f"{r['Seite']} X={r['X_pips']}")
    ax.set_xticks(xs, [f"p{p}" for p in pcts])
    ax.set_ylabel("MAE / X")
    ax.set_title("Messung 1 – MAE-Perzentile in Vielfachen von X")
    ax.legend(ncol=3, fontsize=7.5)
    return _save(fig, path, note)


def defb_bars(sum_b, path, note):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, col, title in [(axes[0], "p99", "MAE p99 bis +X Gewinn ab Einstieg"),
                           (axes[1], "zensiert_%", "Anteil ohne Erreichen von +X in 30 Tagen (%)")]:
        xs = np.arange(len(sum_b["X_pips"].unique()))
        for k, side in enumerate(("Long", "Short")):
            s = sum_b[sum_b["Seite"] == side]
            ax.bar(xs + (k - 0.5) * 0.38, s[col].to_numpy(), width=0.36, color=SIDE_COL[side], label=side)
            for xx, v in zip(xs + (k - 0.5) * 0.38, s[col].to_numpy()):
                ax.text(xx, v, f"{v:.0f}" if col == "p99" else f"{v:.1f}", ha="center", va="bottom", fontsize=7.5)
        ax.set_xticks(xs, [f"X={x}" for x in sum_b["X_pips"].unique()])
        ax.set_title(title, fontsize=10)
        ax.legend()
    fig.suptitle("Messung 1b – Def. B: Einstieg muss +X ins Plus (kein Nachkauf)", fontweight="bold")
    return _save(fig, path, note)


# ------------------------------------------------------------- Messung 2
def by_hour(grp: pd.DataFrame, x: int, col_hour: str, path, title, note):
    fig, ax = plt.subplots(figsize=(9, 4.4))
    d = grp[grp["X_pips"] == x]
    for side in ("Long", "Short"):
        s = d[d["Seite"] == side].sort_values(col_hour)
        ax.plot(s[col_hour], s["p99"], color=SIDE_COL[side], lw=2, marker="o", ms=4, label=f"{side} p99")
        ax.plot(s[col_hour], s["p90"], color=SIDE_COL[side], lw=1, ls="--", label=f"{side} p90")
    both = d.groupby(col_hour)["p99"].max()
    hi, lo = both.idxmax(), both.idxmin()
    ax.axvspan(hi - 0.5, hi + 0.5, color=NEG, alpha=0.12)
    ax.axvspan(lo - 0.5, lo + 0.5, color=POS, alpha=0.12)
    _annot(ax, hi, both[hi], f"höchstes p99: {both[hi]:.0f}", NEG)
    _annot(ax, lo, both[lo], f"niedrigstes p99: {both[lo]:.0f}", POS)
    ax.axhline(x * np.log(100), color=THEORY, ls=":", lw=1)
    ax.text(23.4, x * np.log(100), "RW-Theorie p99", fontsize=7.5, color=THEORY, va="bottom", ha="right")
    ax.set_xticks(range(24))
    ax.set_xlabel("Stunde des Einstiegs (" + ("Serverzeit" if "server" in col_hour else "MEZ/MESZ") + ")")
    ax.set_ylabel(f"MAE (Pips) vor {x} Pips Rücklauf")
    ax.set_title(title)
    ax.legend(ncol=4, fontsize=8)
    return _save(fig, path, note)


def by_category(grp: pd.DataFrame, x: int, col: str, path, title, note):
    d = grp[grp["X_pips"] == x]
    cats = list(dict.fromkeys(d[col].tolist()))
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    xs = np.arange(len(cats))
    for k, side in enumerate(("Long", "Short")):
        s = d[d["Seite"] == side].set_index(col).reindex(cats)
        ax.bar(xs + (k - 0.5) * 0.38, s["p99"], width=0.36, color=SIDE_COL[side], label=f"{side} p99")
        ax.scatter(xs + (k - 0.5) * 0.38, s["p90"], color="#1b1b1a", marker="_", s=120, zorder=3,
                   label="p90" if k == 0 else None)
        for xx, v in zip(xs + (k - 0.5) * 0.38, s["p99"]):
            ax.text(xx, v, f"{v:.0f}", ha="center", va="bottom", fontsize=7.5)
    agg = d.groupby(col, observed=True)["p99"].max().reindex(cats)
    ax.get_xticklabels()
    ax.set_xticks(xs, cats, rotation=0)
    for lab, c in [(agg.idxmax(), NEG), (agg.idxmin(), POS)]:
        i = cats.index(lab)
        ax.axvspan(i - 0.48, i + 0.48, color=c, alpha=0.10)
    ax.axhline(x * np.log(100), color=THEORY, ls=":", lw=1, label="RW-Theorie p99")
    ax.set_ylabel(f"MAE (Pips) vor {x} Pips Rücklauf")
    ax.set_title(title)
    ax.legend(fontsize=8, ncol=4)
    return _save(fig, path, note)


# ------------------------------------------------------------- Messung 3
def regime_chart(reg: pd.DataFrame, x: int, path, note):
    d = reg[reg["X_pips"] == x]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, kind, ttl in [(axes[0], "ex ante (ATR14 Vortage)", "Regime ex ante – vorab bekannt"),
                          (axes[1], "ex post (Tagesrange)", "Regime ex post – erst am Abend bekannt")]:
        s = d[d["Regimeart"] == kind]
        cats = list(dict.fromkeys(s["Regime"].tolist()))
        xs = np.arange(len(cats))
        for k, side in enumerate(("Long", "Short")):
            ss = s[s["Seite"] == side].set_index("Regime").reindex(cats)
            ax.bar(xs + (k - 0.5) * 0.38, ss["p99"], width=0.36, color=SIDE_COL[side], label=f"{side} p99")
            for xx, v in zip(xs + (k - 0.5) * 0.38, ss["p99"]):
                ax.text(xx, v, f"{v:.0f}", ha="center", va="bottom", fontsize=7.5)
        ax.set_xticks(xs, cats)
        ax.set_title(ttl, fontsize=10)
        ax.set_ylabel(f"MAE p99 (Pips), X={x}")
        ax.legend(fontsize=8)
    fig.suptitle("Messung 3 – Ausschlag je Volatilitätsregime (Quintile)", fontweight="bold")
    return _save(fig, path, note)


# ------------------------------------------------------------- Messung 4
def daytype_chart(days: pd.DataFrame, auc: pd.DataFrame, path, note):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3))
    ax = axes[0]
    colmap = {"Trendtag": NEG, "Rangetag": POS, "Mischtag": BENCH}
    for t, c in colmap.items():
        s = days[days["daytype"] == t]
        ax.scatter(s["body_range"], s["range_pips"], s=12, color=c, alpha=0.75,
                   label=f"{t} ({len(s)}, {100*len(s)/len(days):.0f} %)")
    top = days.nlargest(5, "range_pips")
    for idx, r in top.iterrows():
        ax.annotate(idx.strftime("%d.%m.%y"), (r["body_range"], r["range_pips"]), xytext=(4, 2),
                    textcoords="offset points", fontsize=7, color="#2b2a27")
    ax.set_xlabel("|Close − Open| / Tagesrange")
    ax.set_ylabel("Tagesrange (Pips)")
    ax.set_title("Tagesklassen", fontsize=10)
    ax.legend(fontsize=8)
    ax = axes[1]
    for feat, c, lab in [("p_net_atr", LONG, "|Netto bis h| / ATR"), ("p_body", SHORT, "Body/Range bis h"),
                         ("p_range_atr", BENCH, "Range bis h / ATR")]:
        s = auc[auc["Merkmal"] == feat]
        ax.plot(s["bis_Serverstunde"], s["AUC"], marker="o", color=c, lw=2, label=lab)
    ax.axhline(0.5, color=THEORY, ls=":", lw=1)
    ax.text(auc["bis_Serverstunde"].max(), 0.47, "Zufall (0,5)", ha="right", fontsize=7.5, color=THEORY)
    ax.set_ylim(0.4, 1.0)
    ax.set_xlabel("Information bis Serverstunde h")
    ax.set_ylabel("AUC (Trendtag ja/nein)")
    ax.set_title("Früherkennung – Trennschärfe", fontsize=10)
    ax.legend(fontsize=8)
    fig.suptitle("Messung 4 – Trend- vs. Rangetage", fontweight="bold")
    return _save(fig, path, note)


# ------------------------------------------------------------- Messung 5
def vr_chart(vr: pd.DataFrame, path, note):
    sess = list(dict.fromkeys(vr["Session"].tolist()))
    fig, axes = plt.subplots(1, len(sess), figsize=(13, 3.8), sharey=True)
    for ax, s in zip(axes, sess):
        d = vr[vr["Session"] == s]
        hz = d["Horizont_min"].astype(str)
        ax.fill_between(hz, d["VR_Null_2.5%"], d["VR_Null_97.5%"], color=BENCH, alpha=0.25, label="Zufall 95 %")
        col = [NEG if v > hi else (POS if v < lo else LONG)
               for v, lo, hi in zip(d["VR"], d["VR_Null_2.5%"], d["VR_Null_97.5%"])]
        ax.plot(hz, d["VR"], color=LONG, lw=1.5)
        ax.scatter(hz, d["VR"], color=col, s=40, zorder=3)
        ax.axhline(1, color=THEORY, ls=":", lw=1)
        ax.set_title(s, fontsize=9)
        ax.set_xlabel("Horizont (min)")
    axes[0].set_ylabel("Varianz-Ratio VR(q)")
    axes[0].legend(fontsize=7.5)
    fig.suptitle("Messung 5 – Varianz-Ratio (<1 = Rückkehrneigung; grün = signifikant <1, rot = signifikant >1)",
                 fontweight="bold", fontsize=10.5)
    return _save(fig, path, note)


def halflife_chart(hl: pd.DataFrame, path, note):
    fig, axes = plt.subplots(1, len(hl["Fenster_min"].unique()), figsize=(11, 4))
    for ax, W in zip(np.atleast_1d(axes), hl["Fenster_min"].unique()):
        d = hl[hl["Fenster_min"] == W]
        sess = list(dict.fromkeys(d["Session"].tolist()))
        xs = np.arange(len(sess))
        for k, (ser, c) in enumerate([("real", LONG), ("Zufallspfad", BENCH)]):
            s = d[d["Reihe"] == ser].set_index("Session").reindex(sess)
            ax.bar(xs + (k - 0.5) * 0.38, s["Halbwertszeit_min"], width=0.36, color=c, label=ser)
            for xx, v in zip(xs + (k - 0.5) * 0.38, s["Halbwertszeit_min"]):
                ax.text(xx, v, f"{v:.0f}", ha="center", va="bottom", fontsize=7)
        ax.set_xticks(xs, [s.replace("Überlappung ", "Überl. ") for s in sess], rotation=20, fontsize=8)
        ax.set_title(f"Abweichung vom {W}-min-Mittel", fontsize=10)
        ax.set_ylabel("Halbwertszeit (min)")
        ax.legend(fontsize=8)
    fig.suptitle("Messung 5 – Halbwertszeit der Rückkehr zum gleitenden Mittel (real vs. Zufallspfad)",
                 fontweight="bold", fontsize=10.5)
    return _save(fig, path, note)


# ------------------------------------------------------------- Messung 6
def extremes_chart(m1: pd.DataFrame, ext: pd.DataFrame, legs_real, legs_shuf, x, path, note, tz):
    from .timeutil import from_utc
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3), gridspec_kw={"width_ratios": [1.6, 1]})
    ax = axes[0]
    c = m1["c"].resample("1h").last().dropna()
    srv = from_utc(c.index, tz)
    ax.plot(srv, c.to_numpy(), color=BENCH, lw=0.7)
    for k, r in ext.iterrows():
        t = pd.Timestamp(r["Start_Server"])
        y = c.iloc[min(np.searchsorted(srv, t), len(c) - 1)]
        col = NEG
        ax.plot([t], [y], "o", color=col, ms=4 + r["Länge_Pips"] / 40)
        if k < 5:
            ax.annotate(f"{k+1}: {r['Länge_Pips']:.0f} P", (t, y), xytext=(3, 6), textcoords="offset points",
                        fontsize=7.5, color=col, fontweight="bold")
    ax.set_title(f"Top-{len(ext)} Einbahnbewegungen ohne {x}-Pip-Rücklauf", fontsize=10)
    ax.set_ylabel("Kurs")
    ax = axes[1]
    bins = np.linspace(0, max(legs_real.max(), legs_shuf.max()) * 1.02, 50)
    ax.hist(legs_real, bins=bins, color=LONG, alpha=0.8, label=f"real (n={len(legs_real)})", log=True)
    ax.hist(legs_shuf, bins=bins, histtype="step", color=THEORY, lw=1.2, label="Zufallspfad", log=True)
    ax.set_xlabel(f"Beinlänge (Pips) ohne {x}-Pip-Rücklauf")
    ax.set_ylabel("Anzahl (log)")
    ax.legend(fontsize=8)
    ax.set_title("Verteilung aller Beine", fontsize=10)
    fig.suptitle("Messung 6 – Extremphasen", fontweight="bold")
    return _save(fig, path, note)


# ------------------------------------------------------------- Messung 7
def spread_chart(sp: pd.DataFrame, path, note, ext_ref: pd.Series | None = None):
    fig, ax = plt.subplots(figsize=(9, 4.2))
    hrs = sp.index.to_numpy()
    ax.bar(hrs, sp["Spread_Median"], color=LONG, width=0.7, label="Median")
    ax.plot(hrs, sp["Spread_p90"], color=SHORT, marker="o", lw=1.5, ms=4, label="p90")
    ax.plot(hrs, sp["Spread_p99"], color=NEG, marker="v", lw=1, ms=4, ls="--", label="p99")
    if ext_ref is not None:
        ax.plot(ext_ref.index, ext_ref.values, color=THEORY, marker="x", lw=0, ms=6, label="Live-Konto Median (Ref.)")
    hi = sp["Spread_Median"].idxmax(); lo = sp["Spread_Median"].idxmin()
    _annot(ax, hi, sp.loc[hi, "Spread_p90"], f"teuerste Std. {hi}", NEG)
    _annot(ax, lo, sp.loc[lo, "Spread_Median"], f"günstigste {lo}", POS)
    ax.set_xticks(range(24))
    ax.set_xlabel("Serverstunde")
    ax.set_ylabel("Spread (Pips)")
    ax.set_yscale("log")
    ax.set_title("Messung 7 – Spread je Stunde (log-Skala)")
    ax.legend(fontsize=8, ncol=4)
    return _save(fig, path, note)


def cost_share_chart(sp: pd.DataFrame, comm_scen_pips: dict, path, note):
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    tgt = np.linspace(1, 30, 300)
    lo_h = sp["Spread_Median"].idxmin()
    cols = [LONG, SHORT, "#1baf7a", "#6250d6"]
    for k, (label, cp) in enumerate(comm_scen_pips.items()):
        cost_typ = sp["Spread_Median"].median() + cp
        ax.plot(tgt, 100 * cost_typ / tgt, lw=2, color=cols[k % 4], label=f"typ. Stunde, {label}")
    ax.plot(tgt, 100 * (sp["Spread_Median"].max()) / tgt, lw=1.2, ls="--", color=NEG,
            label=f"teuerste Std. ({sp['Spread_Median'].idxmax()}), nur Spread")
    for th in (20, 30, 50):
        ax.axhline(th, color=THEORY, ls=":", lw=1)
        ax.text(30, th, f"{th} %", fontsize=7.5, color=THEORY, va="bottom", ha="right")
    ax.set_ylim(0, 100)
    ax.set_xlabel("Zielgröße pro Teilgewinn (Pips brutto)")
    ax.set_ylabel("Kosten in % des Bruttogewinns")
    ax.set_title("Messung 7 – Kostenanteil je Zielgröße")
    ax.legend(fontsize=7.5)
    return _save(fig, path, note)


# ------------------------------------------------------------- Datenqualität
def quality_chart(m1: pd.DataFrame, spread_bars: pd.DataFrame | None, tz, path, note):
    from .timeutil import from_utc
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8))
    srv = from_utc(m1.index, tz).normalize()
    cnt = pd.Series(1, index=srv).groupby(level=0).count()
    axes[0].bar(cnt.index, cnt.values, color=LONG, width=1)
    low = cnt[cnt < 1000]
    axes[0].scatter(low.index, low.values, color=NEG, s=14, zorder=3, label=f"< 1000 Bars ({len(low)} Tage)")
    axes[0].set_title("M1-Bars je Servertag", fontsize=10)
    axes[0].legend(fontsize=8)
    if spread_bars is not None:
        sp = spread_bars["spread_med_pips"]
        h = from_utc(sp.index, tz).hour
        axes[1].scatter(h + np.random.default_rng(0).uniform(-0.3, 0.3, len(sp)), sp.values, s=2, alpha=0.3, color=LONG)
        axes[1].set_yscale("log")
        axes[1].set_xticks(range(24))
        axes[1].set_xlabel("Serverstunde")
        axes[1].set_ylabel("Spread (Pips, 10-min-Median)")
        axes[1].set_title("Spread-Spitzen (Rollover 23–01 Server)", fontsize=10)
    fig.suptitle("Datenqualität", fontweight="bold")
    return _save(fig, path, note)
