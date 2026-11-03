"""Selbsttest der Messkernels gegen bekannte Theorie (synthetischer Random Walk).

Nur Methodenprüfung – keine Marktaussage.  python tests/test_kernels.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bmlib.kernels import excursion, zigzag  # noqa: E402


def test_random_walk_exponential():
    rng = np.random.default_rng(1)
    n = 4_000_000
    c = np.cumsum(rng.normal(0, 0.3, n))          # Tick-Pfad in Pips (h=l=c)
    t = np.arange(n, dtype=np.float64)
    ent = np.arange(0, n - 200_000, 50, dtype=np.int64)
    for x in (5.0,):
        for d in (1, -1):
            mae, dur, cen = excursion(c, c, c, ent, x, d, False, True, 1e12, t)
            # Theorie: P(MAE > a) = exp(-a/x) -> Median x ln2, p90 x ln10 (diskrete Schritte: leichte Abweichung)
            assert abs(np.median(mae) / (x * np.log(2)) - 1) < 0.08, np.median(mae)
            assert abs(np.percentile(mae, 90) / (x * np.log(10)) - 1) < 0.08
            assert cen.sum() == 0


def test_hand_example():
    # Long, Einstieg 100: fällt auf 95, steigt auf 98 (3 vom Tief) -> X=3: MAE 5
    c = np.array([100, 99, 97, 95, 96, 98, 99], float)
    t = np.arange(len(c), dtype=float)
    mae, dur, cen = excursion(c, c, c, np.array([0]), 3.0, 1, False, True, 1e9, t)
    assert mae[0] == 5 and dur[0] == 5 and cen[0] == 0
    # Def B: +3 ab Einstieg (103) nie erreicht -> zensiert, MAE 5
    mae, dur, cen = excursion(c, c, c, np.array([0]), 3.0, 1, True, True, 1e9, t)
    assert cen[0] == 1 and mae[0] == 5
    # Short gespiegelt
    mae, _, _ = excursion(-c, -c, -c, np.array([0]), 3.0, -1, False, True, 1e9, t)
    assert mae[0] == 5


def test_zigzag():
    h = np.array([0, 5, 12, 20, 15, 9, 14, 30], float)
    s, e, d, ln = zigzag(h, h, 10.0)
    assert list(d) == [1, -1] and list(ln) == [20, 11]


if __name__ == "__main__":
    test_hand_example(); test_zigzag(); test_random_walk_exponential()
    print("OK – alle Kernel-Tests bestanden")
