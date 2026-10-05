"""Prüfungen für offline/measures.py und offline/selection.py.

Die Latenzmaße sind der Punkt, an dem die inhaltliche Aussage hängt
("kommt der Reiz vom Fuß später an?"), und beim Vorzeichen einer
Kreuzkorrelation vertut man sich schnell. Deshalb wird hier gegen
künstlich erzeugte Kurven geprüft, deren Antwort man kennt.

Ausführen:  .venv/bin/python -m pytest tests/ -q
        oder .venv/bin/python tests/test_measures.py
"""

import sys
import pathlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from offline.measures import (peak_latency, fractional_area_latency,
                              crosscorr_shift, cluster_permutation_test)
from offline.selection import epoch_stats, select_triggers

FS = 250.0
T = np.arange(-200, 2000, 1000 / FS)


def _gauss(center_ms, width_ms=60, amp=5.0):
    return amp * np.exp(-0.5 * ((T - center_ms) / width_ms) ** 2)


# ── Gipfellatenz ─────────────────────────────────────────────────────
def test_peak_latency_findet_gipfel():
    for c in (120.0, 237.0, 480.0):
        got = peak_latency(_gauss(c), T, (0, 800), "max")
        assert abs(got["latenz_ms"] - c) < 2.0, (c, got)
        assert abs(got["amplitude_µV"] - 5.0) < 0.1


def test_peak_latency_zwischen_abtastpunkten():
    """Die Verfeinerung muss besser sein als das 4-ms-Raster."""
    fehler = [abs(peak_latency(_gauss(c), T, (0, 800), "max")["latenz_ms"] - c)
              for c in np.arange(200, 210, 0.7)]
    assert max(fehler) < 1.0, fehler


def test_peak_latency_min_und_fenster():
    x = _gauss(150, amp=-4) + _gauss(400, amp=6)
    assert abs(peak_latency(x, T, (0, 250), "min")["latenz_ms"] - 150) < 3
    assert abs(peak_latency(x, T, (250, 600), "max")["latenz_ms"] - 400) < 3


# ── Kreuzkorrelation: Vorzeichen und Betrag ──────────────────────────
def test_crosscorr_vorzeichen_positiv_heisst_spaeter():
    a = _gauss(200)
    b = _gauss(280)                      # b liegt 80 ms SPÄTER
    got = crosscorr_shift(a, b, T, (0, 800), max_lag_ms=300)
    assert got["verschiebung_ms"] > 0, got
    assert abs(got["verschiebung_ms"] - 80) < 5, got


def test_crosscorr_betrag_ueber_bereich():
    a = _gauss(300)
    for soll in (-120, -60, -20, 0, 20, 60, 120):
        got = crosscorr_shift(a, _gauss(300 + soll), T, (0, 800),
                              max_lag_ms=300)["verschiebung_ms"]
        assert abs(got - soll) < 5, (soll, got)


def test_crosscorr_unempfindlich_gegen_amplitude():
    """Ein doppelt so großer Ausschlag darf die Latenz nicht verschieben."""
    a = _gauss(250, amp=2.0)
    b = _gauss(300, amp=9.0)
    got = crosscorr_shift(a, b, T, (0, 800), max_lag_ms=300)["verschiebung_ms"]
    assert abs(got - 50) < 5, got


def test_crosscorr_bevorzugt_keine_kleinen_verschiebungen():
    """Mit fester Normierung auf die volle Länge würde eine große echte
    Verschiebung systematisch unterschätzt — hier darf das nicht passieren."""
    got = crosscorr_shift(_gauss(200), _gauss(400), T, (0, 900),
                          max_lag_ms=350)["verschiebung_ms"]
    assert abs(got - 200) < 10, got


# ── Flächenlatenz ────────────────────────────────────────────────────
def test_fractional_area_latency_mittig():
    got = fractional_area_latency(_gauss(300, width_ms=50), T, (0, 600), 0.5)
    assert abs(got - 300) < 8, got


# ── Permutationstest ─────────────────────────────────────────────────
def test_cluster_test_findet_echten_unterschied():
    rng = np.random.default_rng(1)
    a = _gauss(250)[None, :] + rng.normal(0, 2, (40, len(T)))
    b = rng.normal(0, 2, (40, len(T)))
    cl = cluster_permutation_test(a, b, T, (0, 800), n_perm=400)["cluster"]
    top = cl.iloc[0]
    assert top["p"] < 0.05
    assert top["von_ms"] < 250 < top["bis_ms"], top


def test_cluster_test_ohne_unterschied_ist_still():
    rng = np.random.default_rng(2)
    a = rng.normal(0, 2, (40, len(T)))
    b = rng.normal(0, 2, (40, len(T)))
    cl = cluster_permutation_test(a, b, T, (0, 800), n_perm=400)["cluster"]
    assert len(cl) == 0 or (cl["p"] < 0.05).sum() == 0, cl


# ── Auswahl ──────────────────────────────────────────────────────────
def _daten(n_trig=50, n=40000):
    rng = np.random.default_rng(3)
    eeg = rng.normal(0, 5, (n, 8))
    idx = np.arange(400, n - 700, (n - 1200) // n_trig)[:n_trig]
    return eeg, idx


def test_select_last_nimmt_die_letzten():
    eeg, idx = _daten()
    st = select_triggers(epoch_stats(eeg, idx, FS), last=40)
    assert st["gewaehlt"].sum() == 40
    assert st["gewaehlt"].to_numpy()[-40:].all()
    assert not st["gewaehlt"].to_numpy()[:-40].any()


def test_select_mad_findet_eingebauten_ausreisser():
    eeg, idx = _daten()
    eeg[idx[7] + 20] += 800.0                      # ein grober Ausschlag
    st = select_triggers(epoch_stats(eeg, idx, FS), mad_k=3.5)
    assert not st.loc[7, "gewaehlt"], st.loc[7]
    assert st["gewaehlt"].sum() >= len(idx) - 3    # nicht die halbe Sitzung

def test_select_mad_bezieht_sich_auf_die_auswahl():
    """mad_k darf nur innerhalb der durch last/first gewählten Menge
    urteilen — sonst entscheidet ein verworfener Abschnitt mit."""
    eeg, idx = _daten()
    eeg[idx[1] + 20] += 3000.0                     # liegt VOR der Auswahl
    st = select_triggers(epoch_stats(eeg, idx, FS), last=40, mad_k=3.5)
    gewaehlt = st.loc[st["gewaehlt"]]
    assert len(gewaehlt) >= 38, st["grund"].value_counts()


def test_drop_first_verwirft_die_einlaufphase():
    eeg, idx = _daten(n_trig=50)
    st = select_triggers(epoch_stats(eeg, idx, FS), drop_first=10)
    assert st["gewaehlt"].sum() == 40
    assert not st["gewaehlt"].to_numpy()[:10].any()
    assert st["gewaehlt"].to_numpy()[10:].all()


def test_drop_first_und_last_kombiniert():
    eeg, idx = _daten(n_trig=50)
    st = select_triggers(epoch_stats(eeg, idx, FS), drop_first=10, last=20)
    g = st["gewaehlt"].to_numpy()
    assert g.sum() == 20, st["grund"].value_counts()
    assert not g[:30].any() and g[30:].all()


def test_select_unvollstaendige_fenster_fallen_raus():
    eeg, _ = _daten()
    idx = [10, 5000, len(eeg) - 5]                 # erster und letzter zu nah am Rand
    st = select_triggers(epoch_stats(eeg, idx, FS, pre_ms=200, post_ms=2000))
    assert list(st["gewaehlt"]) == [False, True, False], st


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok    {name}")
            except AssertionError as e:
                fails += 1
                print(f"  FEHLT {name}: {e}")
    print("\nalle bestanden" if not fails else f"\n{fails} fehlgeschlagen")
    sys.exit(1 if fails else 0)
