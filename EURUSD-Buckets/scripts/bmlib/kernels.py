"""Numba-Kernels für Ausschlags-, ZigZag- und Rückkehrmessungen.

Pfad-Konvention innerhalb eines Bars (nur bei Bar-Daten relevant, bei
1-Sekunden-Bars aus Ticks praktisch irrelevant):
  adverse_first=True :  Long: O -> L -> H -> C   (Short: O -> H -> L -> C)
                        -> erst Gegenbewegung, dann Erholung (Standard)
  adverse_first=False:  Long: O -> H -> L -> C   (Sensitivität)
Beide Pfade sind physikalisch mögliche Kursverläufe; die Differenz der
Ergebnisse ist die Unschärfe durch fehlende Intrabar-Information.

Definitionen (Long; Short gespiegelt), Einstieg zum Close von Bar i:
  Def A  "Rücklauf X":   Suche vorwärts; laufendes Minimum m. Ende, sobald
                         Kurs >= m + X (X Pips Erholung vom tiefsten Punkt).
                         MAE = Einstieg - m.
  Def B  "Gewinn X":     Ende, sobald Kurs >= Einstieg + X.
                         MAE = Einstieg - Minimum vor dem Ende.
Kappung nach max_bars; dann zensiert (censored=1), MAE = bis dahin.
"""
from __future__ import annotations

import numpy as np
from numba import njit, prange


@njit(cache=True, parallel=True)
def excursion(h, l, c, entries, x, direction, mode_b, adverse_first, max_secs, tsec):
    """Gibt (mae, dur_sec, censored) je Einstieg zurück. Preise in Pips skaliert."""
    n = len(c)
    ne = len(entries)
    mae = np.empty(ne, np.float64)
    dur = np.empty(ne, np.float64)
    cen = np.zeros(ne, np.uint8)
    for k in prange(ne):
        i = entries[k]
        p0 = c[i]
        t0 = tsec[i]
        if direction == 1:
            m = p0           # laufendes Minimum (adverse Extrem)
            done = False
            j = i + 1
            while j < n:
                if tsec[j] - t0 > max_secs:
                    break
                hj = h[j]
                lj = l[j]
                if adverse_first:
                    if lj < m:
                        m = lj
                    tgt = (m + x) if not mode_b else (p0 + x)
                    if hj >= tgt:
                        done = True
                        break
                else:
                    tgt = (m + x) if not mode_b else (p0 + x)
                    if hj >= tgt:
                        done = True
                        break
                    if lj < m:
                        m = lj
                    tgt = (m + x) if not mode_b else (p0 + x)
                    if c[j] >= tgt:
                        done = True
                        break
                j += 1
            mae[k] = p0 - m
        else:
            m = p0           # laufendes Maximum
            done = False
            j = i + 1
            while j < n:
                if tsec[j] - t0 > max_secs:
                    break
                hj = h[j]
                lj = l[j]
                if adverse_first:
                    if hj > m:
                        m = hj
                    tgt = (m - x) if not mode_b else (p0 - x)
                    if lj <= tgt:
                        done = True
                        break
                else:
                    tgt = (m - x) if not mode_b else (p0 - x)
                    if lj <= tgt:
                        done = True
                        break
                    if hj > m:
                        m = hj
                    tgt = (m - x) if not mode_b else (p0 - x)
                    if c[j] <= tgt:
                        done = True
                        break
                j += 1
            mae[k] = m - p0
        jj = j if j < n else n - 1
        dur[k] = tsec[jj] - t0
        if not done:
            cen[k] = 1
    return mae, dur, cen


@njit(cache=True)
def zigzag(h, l, x):
    """ZigZag mit Umkehrschwelle x (Pips-Skala).

    Liefert Beine (start_idx, end_idx, richtung, länge). Ein Bein ist eine
    Einbahnbewegung ohne Rücklauf >= x. Intrabar: adverse-first Konvention
    bezogen auf das laufende Bein.
    """
    n = len(h)
    starts = []
    ends = []
    dirs = []
    lens = []
    # Initialisierung: Richtung festlegen, sobald x überschritten
    hi = h[0]; lo = l[0]; hi_i = 0; lo_i = 0
    d = 0
    i = 1
    while i < n and d == 0:
        if h[i] > hi:
            hi = h[i]; hi_i = i
        if l[i] < lo:
            lo = l[i]; lo_i = i
        if hi - lo >= x:
            d = 1 if hi_i > lo_i else -1
        i += 1
    if d == 0:
        return np.empty(0, np.int64), np.empty(0, np.int64), np.empty(0, np.int8), np.empty(0, np.float64)
    if d == 1:
        st_i = lo_i; st_p = lo; ex_i = hi_i; ex_p = hi
    else:
        st_i = hi_i; st_p = hi; ex_i = lo_i; ex_p = lo
    while i < n:
        if d == 1:
            if h[i] > ex_p:
                ex_p = h[i]; ex_i = i
            elif ex_p - l[i] >= x:
                starts.append(st_i); ends.append(ex_i); dirs.append(1); lens.append(ex_p - st_p)
                st_i = ex_i; st_p = ex_p; d = -1; ex_i = i; ex_p = l[i]
        else:
            if l[i] < ex_p:
                ex_p = l[i]; ex_i = i
            elif h[i] - ex_p >= x:
                starts.append(st_i); ends.append(ex_i); dirs.append(-1); lens.append(st_p - ex_p)
                st_i = ex_i; st_p = ex_p; d = 1; ex_i = i; ex_p = h[i]
        i += 1
    return (np.array(starts, np.int64), np.array(ends, np.int64),
            np.array(dirs, np.int8), np.array(lens, np.float64))
