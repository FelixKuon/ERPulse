"""offline/measures.py — Kennzahlen aus gemittelten Potentialen.

Für die eigentliche Frage — kommt der Reiz vom Fuß später an als vom
Oberarm? — reicht Hinsehen nicht. Drei Dinge braucht es:

  1. **Ein Latenzmaß, das nicht am Rauschen hängt.** Die Gipfellatenz ist
     das übliche, aber empfindlich: ein verrauschter Gipfel springt leicht
     um 50 ms. Deshalb hier zusätzlich die Flächenhälften-Latenz
     (`fractional_area_latency`) und die Verschiebung aus der
     Kreuzkorrelation (`crosscorr_shift`), die die ganze Kurvenform nutzt.

  2. **Ein Vertrauensbereich.** Über Epochen gebootstrapt: die Streuung
     der Einzelepochen sagt, wie stabil der Mittelwert ist.

  3. **Einen Test gegen die Nullhypothese.** Bei 550 Zeitpunkten × 8
     Kanälen findet man ohne Korrektur immer irgendwo einen Unterschied.
     `cluster_permutation_test` prüft zusammenhängende Zeitabschnitte
     gegen eine Verteilung, die aus vertauschten Bedingungsetiketten
     entsteht — das übliche Vorgehen für EEG-Zeitreihen.

Alles hier arbeitet auf einer Sitzung eines Menschen. Das erlaubt Aussagen
über DIESE Messung, nicht über die Allgemeinheit — dafür bräuchte es
mehrere Personen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _win(t: np.ndarray, window):
    """Boolesche Maske für ein Zeitfenster in ms."""
    if window is None:
        return np.ones(len(t), bool)
    lo, hi = window
    return (t >= lo) & (t <= hi)


# ── Latenzmaße ───────────────────────────────────────────────────────
def peak_latency(trace: np.ndarray, t: np.ndarray, window=None,
                 mode: str = "absmax") -> dict:
    """Gipfel im Fenster. mode: 'max' | 'min' | 'absmax'.

    Der Gipfel wird über eine Parabel durch die drei Punkte um das
    Abtastmaximum verfeinert — bei 250 Hz liegen die Stützstellen 4 ms
    auseinander, und diese Quantisierung wäre sonst ein guter Teil des
    gesuchten Unterschieds."""
    m = _win(t, window)
    tw, xw = t[m], trace[m]
    if mode == "max":
        i = int(np.argmax(xw))
    elif mode == "min":
        i = int(np.argmin(xw))
    else:
        i = int(np.argmax(np.abs(xw)))

    lat, amp = float(tw[i]), float(xw[i])
    if 0 < i < len(xw) - 1:                       # parabolische Verfeinerung
        y0, y1, y2 = xw[i - 1], xw[i], xw[i + 1]
        den = y0 - 2 * y1 + y2
        if den != 0:
            d = 0.5 * (y0 - y2) / den
            if abs(d) <= 1:
                dt = tw[1] - tw[0]
                lat = float(tw[i] + d * dt)
                amp = float(y1 - 0.25 * (y0 - y2) * d)
    return {"latenz_ms": lat, "amplitude_µV": amp}


def fractional_area_latency(trace: np.ndarray, t: np.ndarray, window,
                            fraction: float = 0.5,
                            rectify: bool = True) -> float:
    """Zeitpunkt, bis zu dem ein Anteil der Fläche im Fenster erreicht ist.

    Robuster als die Gipfellatenz, weil die ganze Auslenkung eingeht und
    nicht nur ihr Scheitel. `rectify=True` nimmt den Betrag — sinnvoll,
    wenn im Fenster eine zweiphasige Antwort liegt."""
    m = _win(t, window)
    tw = t[m]
    xw = np.abs(trace[m]) if rectify else trace[m]
    c = np.cumsum(xw)
    if c[-1] <= 0:
        return float("nan")
    return float(np.interp(fraction * c[-1], c, tw))


def crosscorr_shift(a: np.ndarray, b: np.ndarray, t: np.ndarray,
                    window=None, max_lag_ms: float = 500.0) -> dict:
    """Wie weit liegt `b` gegenüber `a` zeitlich versetzt?

    **Positiv heißt: `b` kommt später.** Geprüft wird das in
    `tests/test_measures.py` gegen künstlich verschobene Kurven — das
    Vorzeichen einer Kreuzkorrelation verdreht man leicht, und hier hängt
    die ganze Aussage daran.

    Für jede Verschiebung wird nur der überlappende Teil verglichen und
    dort einzeln zentriert und normiert. Sonst bevorzugt das Maß kleine
    Verschiebungen allein deshalb, weil dort mehr Kurve übrig ist.
    Amplitudenunterschiede spielen dadurch keine Rolle, die Kurvenform
    entscheidet. Zwischen den Abtastpunkten wird parabolisch verfeinert.
    """
    m = _win(t, window)
    x, y = np.asarray(a, float)[m], np.asarray(b, float)[m]
    n = len(x)
    dt = float(t[1] - t[0])
    max_lag = min(int(round(max_lag_ms / dt)), n - 4)
    if max_lag < 1:
        return {"verschiebung_ms": float("nan"), "r": float("nan")}

    lags = np.arange(-max_lag, max_lag + 1)
    r = np.full(len(lags), -np.inf)
    for i, k in enumerate(lags):
        # k > 0 prüft die Annahme "b liegt um k später", also b(t) = a(t−k).
        # Verglichen wird damit a am frühen Ende gegen b am späten.
        xs = x[:n - k] if k >= 0 else x[-k:]
        ys = y[k:] if k >= 0 else y[:n + k]
        if len(xs) < 4:
            continue
        xs = xs - xs.mean()
        ys = ys - ys.mean()
        den = np.linalg.norm(xs) * np.linalg.norm(ys)
        if den > 0:
            r[i] = float(np.dot(xs, ys) / den)

    i = int(np.argmax(r))
    shift = float(lags[i] * dt)
    if 0 < i < len(r) - 1 and np.isfinite(r[i - 1]) and np.isfinite(r[i + 1]):
        den = r[i - 1] - 2 * r[i] + r[i + 1]
        if den != 0:
            d = 0.5 * (r[i - 1] - r[i + 1]) / den
            if abs(d) <= 1:
                shift += d * dt
    return {"verschiebung_ms": shift, "r": float(r[i])}


# ── Vertrauensbereiche ───────────────────────────────────────────────
def bootstrap_measure(epochs: np.ndarray, t: np.ndarray, fn,
                      n_boot: int = 2000, ci: float = 95.0,
                      seed: int = 0) -> dict:
    """Vertrauensbereich eines Maßes durch Ziehen mit Zurücklegen über die
    Epochen. `fn(mittelwert, t)` gibt eine Zahl zurück.

    epochs: (n_epochen, n_zeit) — ein Kanal.
    """
    epochs = np.asarray(epochs, dtype=float)
    n = len(epochs)
    point = float(fn(epochs.mean(axis=0), t))
    if n < 3:
        return {"wert": point, "lo": np.nan, "hi": np.nan, "n": n}

    rng = np.random.default_rng(seed)
    vals = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        vals[i] = fn(epochs[idx].mean(axis=0), t)
    lo, hi = np.nanpercentile(vals, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return {"wert": point, "lo": float(lo), "hi": float(hi),
            "sd": float(np.nanstd(vals)), "n": n}


def bootstrap_shift(epochs_a: np.ndarray, epochs_b: np.ndarray,
                    t: np.ndarray, window=None, max_lag_ms: float = 500.0,
                    n_boot: int = 2000, ci: float = 95.0,
                    seed: int = 0) -> dict:
    """Vertrauensbereich der Kreuzkorrelations-Verschiebung zwischen zwei
    Bedingungen — in beiden Bedingungen wird unabhängig gezogen.

    `am_rand` ist der Anteil der Ziehungen, deren beste Verschiebung am
    Rand des Suchbereichs liegt. Ist der nennenswert größer als null,
    findet die Kreuzkorrelation in vielen Ziehungen gar kein echtes
    Maximum mehr — das Ergebnis ist dann kein Latenzmaß, sondern Rauschen,
    und der Vertrauensbereich täuscht Genauigkeit vor."""
    a, b = np.asarray(epochs_a, float), np.asarray(epochs_b, float)
    point = crosscorr_shift(a.mean(0), b.mean(0), t, window, max_lag_ms)

    rng = np.random.default_rng(seed)
    vals = np.empty(n_boot)
    for i in range(n_boot):
        ma = a[rng.integers(0, len(a), len(a))].mean(0)
        mb = b[rng.integers(0, len(b), len(b))].mean(0)
        vals[i] = crosscorr_shift(ma, mb, t, window, max_lag_ms)["verschiebung_ms"]
    lo, hi = np.nanpercentile(vals, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    dt = float(t[1] - t[0])
    rail = float(np.mean(np.abs(vals) >= max_lag_ms - 2 * dt))
    return {**point, "lo": float(lo), "hi": float(hi),
            "sd": float(np.nanstd(vals)), "am_rand": rail,
            "n_a": len(a), "n_b": len(b)}


def bootstrap_difference(epochs_a: np.ndarray, epochs_b: np.ndarray,
                         t: np.ndarray, fn, n_boot: int = 2000,
                         ci: float = 95.0, n_perm: int = 2000,
                         seed: int = 0) -> dict:
    """Unterschied eines Maßes zwischen zwei Bedingungen, direkt geschätzt.

    Zwei überlappende Vertrauensbereiche heißen nicht, dass kein
    Unterschied besteht — deshalb wird die Differenz selbst gebootstrapt.
    Dazu ein Permutationstest: die Epochen werden in einen Topf geworfen
    und neu verteilt, was die Nullverteilung der Differenz liefert."""
    a, b = np.asarray(epochs_a, float), np.asarray(epochs_b, float)
    point = float(fn(b.mean(0), t)) - float(fn(a.mean(0), t))

    rng = np.random.default_rng(seed)
    vals = np.empty(n_boot)
    for i in range(n_boot):
        vals[i] = (fn(b[rng.integers(0, len(b), len(b))].mean(0), t)
                   - fn(a[rng.integers(0, len(a), len(a))].mean(0), t))
    lo, hi = np.nanpercentile(vals, [(100 - ci) / 2, 100 - (100 - ci) / 2])

    pooled = np.vstack([a, b])
    na = len(a)
    null = np.empty(n_perm)
    for k in range(n_perm):
        p = rng.permutation(len(pooled))
        null[k] = (fn(pooled[p[na:]].mean(0), t) - fn(pooled[p[:na]].mean(0), t))
    pval = float((np.sum(np.abs(null) >= abs(point)) + 1) / (n_perm + 1))

    return {"differenz": point, "lo": float(lo), "hi": float(hi),
            "sd": float(np.nanstd(vals)), "p": pval,
            "n_a": len(a), "n_b": len(b)}


# ── Test ─────────────────────────────────────────────────────────────
def cluster_permutation_test(epochs_a: np.ndarray, epochs_b: np.ndarray,
                             t: np.ndarray, window=None,
                             n_perm: int = 5000, t_thresh: float = 2.0,
                             seed: int = 0) -> dict:
    """Cluster-basierter Permutationstest für zwei unabhängige Bedingungen.

    Vorgehen: an jedem Zeitpunkt ein t-Wert für den Gruppenunterschied,
    benachbarte Zeitpunkte mit |t| über der Schwelle zu Clustern
    zusammenfassen, deren Summen (Clustermasse) als Prüfgröße nehmen.
    Die Nullverteilung entsteht durch Vertauschen der Bedingungsetiketten
    über alle Epochen. Der p-Wert gilt für den Cluster als Ganzes; über
    seine genaue zeitliche Ausdehnung sagt der Test nichts.

    Rückgabe: Liste der Cluster mit Zeitgrenzen, Masse und p, dazu die
    t-Kurve. `epochs_*`: (n_epochen, n_zeit) für EINEN Kanal.
    """
    a, b = np.asarray(epochs_a, float), np.asarray(epochs_b, float)
    m = _win(t, window)
    tw = t[m]
    A, B = a[:, m], b[:, m]
    na, nb = len(A), len(B)
    if na < 3 or nb < 3:
        raise ValueError("zu wenige Epochen für einen Test")

    def tstat(X, Y):
        vx, vy = X.var(axis=0, ddof=1), Y.var(axis=0, ddof=1)
        se = np.sqrt(vx / len(X) + vy / len(Y)) + 1e-12
        return (X.mean(axis=0) - Y.mean(axis=0)) / se

    def clusters(tv):
        out, sig = [], np.abs(tv) > t_thresh
        i = 0
        while i < len(sig):
            if sig[i]:
                j = i
                while j + 1 < len(sig) and sig[j + 1]:
                    j += 1
                out.append((i, j, float(tv[i:j + 1].sum())))
                i = j + 1
            else:
                i += 1
        return out

    t_obs = tstat(A, B)
    obs = clusters(t_obs)

    pooled = np.vstack([A, B])
    rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    for k in range(n_perm):
        p = rng.permutation(na + nb)
        cl = clusters(tstat(pooled[p[:na]], pooled[p[na:]]))
        null[k] = max((abs(c[2]) for c in cl), default=0.0)

    res = [{"von_ms": float(tw[i]), "bis_ms": float(tw[j]),
            "masse": mass, "t_max": float(t_obs[i:j + 1][
                np.argmax(np.abs(t_obs[i:j + 1]))]),
            "p": float((np.sum(null >= abs(mass)) + 1) / (n_perm + 1))}
           for i, j, mass in obs]
    res.sort(key=lambda c: -abs(c["masse"]))
    return {"cluster": pd.DataFrame(res), "t": t_obs, "t_zeit": tw,
            "t_thresh": t_thresh, "n_a": na, "n_b": nb}


# ── Übersichtstabellen ───────────────────────────────────────────────
def component_table(results: dict, channel, windows: dict,
                    n_boot: int = 1000, seed: int = 0) -> pd.DataFrame:
    """Gipfellatenz und -amplitude je Bedingung und Suchfenster.

    results: {name: ReplayResult}
    windows: {'N2': (150, 400), 'P2': (250, 700)}  — Fenster in ms,
             optional als (lo, hi, mode) mit mode 'min'|'max'|'absmax'
    """
    rows = []
    for name, res in results.items():
        t = res.time_axis
        ep = res.epoch_traces(channel)
        for comp, spec in windows.items():
            lo, hi, mode = (*spec, "absmax")[:3] if len(spec) == 2 else spec
            lat = bootstrap_measure(
                ep, t, lambda x, tt: peak_latency(x, tt, (lo, hi), mode)["latenz_ms"],
                n_boot=n_boot, seed=seed)
            amp = bootstrap_measure(
                ep, t, lambda x, tt: peak_latency(x, tt, (lo, hi), mode)["amplitude_µV"],
                n_boot=n_boot, seed=seed)
            rows.append({
                "bedingung": name, "komponente": comp, "n": lat["n"],
                "latenz_ms": round(lat["wert"], 1),
                "latenz_KI": f"{lat['lo']:.0f}–{lat['hi']:.0f}",
                "amplitude_µV": round(amp["wert"], 2),
                "amplitude_KI": f"{amp['lo']:.2f}–{amp['hi']:.2f}",
            })
    return pd.DataFrame(rows)


def snr_table(results: dict, channel, signal_window,
              baseline_window=(-200, 0)) -> pd.DataFrame:
    """Wie deutlich hebt sich die Antwort vom Grundrauschen ab?

    `rms_signal / rms_baseline` des Mittelwerts. Weil sich beim Mitteln
    das Rauschen mit √n verkleinert, hängt die Zahl an der Epochenanzahl —
    Bedingungen mit sehr unterschiedlichem n sind nur eingeschränkt
    vergleichbar; deshalb steht n mit in der Tabelle."""
    rows = []
    for name, res in results.items():
        t, x = res.time_axis, res.trace(channel)
        s = np.sqrt((x[_win(t, signal_window)] ** 2).mean())
        b = np.sqrt((x[_win(t, baseline_window)] ** 2).mean())
        rows.append({"bedingung": name, "n": res.n_accepted,
                     "rms_signal_µV": round(float(s), 2),
                     "rms_basis_µV": round(float(b), 2),
                     "verhältnis": round(float(s / (b + 1e-12)), 2)})
    return pd.DataFrame(rows)


# ── Güte der evozierten Antwort (für Applikator-Vergleiche) ──────────
#
# Gipfelamplituden taugen für den Vergleich zweier Reizköpfe schlecht: die
# Suche nach dem Größten in einem Fenster findet auch im reinen Rauschen
# etwas, und zwar umso mehr, je weniger Epochen gemittelt wurden. Wer zwei
# Bedingungen mit unterschiedlichem n so vergleicht, misst am Ende n.
#
# Die drei Maße hier sind entweder unverzerrt (mittlere Amplitude,
# rauschbereinigte Leistung) oder bewusst bei gleicher Epochenzahl zu
# verwenden (Reliabilität, Einzeltrial-Konsistenz).

def mean_amplitude(epochs: np.ndarray, t: np.ndarray, window) -> float:
    """Mittlere Amplitude im Fenster — unverzerrt, anders als die
    Gipfelsuche. Setzt voraus, dass das Fenster vorab festgelegt wurde
    und nicht nach Sichtung der Daten gewählt wird."""
    m = _win(t, window)
    return float(np.asarray(epochs, float).mean(axis=0)[m].mean())


def evoked_rms(epochs: np.ndarray, t: np.ndarray, window,
               baseline_window=(-200, 0)) -> dict:
    """Stärke der evozierten Antwort, um den Rauschanteil bereinigt.

    Der Mittelwert über n Epochen enthält noch Rauschen der Leistung
    σ²/n. Ohne Abzug wächst jedes Amplitudenmaß, wenn n kleiner wird —
    eine Bedingung mit weniger Epochen sähe stärker aus. Hier wird der
    erwartete Rauschanteil abgezogen, geschätzt aus der Streuung über die
    Epochen in der Grundlinie:

        Signal² ≈ Mittelwert² − σ²_Grundlinie / n

    Das Ergebnis ist von n weitgehend unabhängig und damit zwischen
    Bedingungen mit ungleicher Epochenzahl vergleichbar. Bleibt nach dem
    Abzug nichts übrig, ist die Antwort im Rauschen nicht nachweisbar —
    `rms` ist dann 0.
    """
    ep = np.asarray(epochs, float)
    n = len(ep)
    w, bl = _win(t, window), _win(t, baseline_window)
    mittel = ep.mean(axis=0)

    p_beob = float((mittel[w] ** 2).mean())
    sigma2 = float(ep[:, bl].var(axis=0, ddof=1).mean())
    p_rausch = sigma2 / n
    return {"rms": float(np.sqrt(max(p_beob - p_rausch, 0.0))),
            "rms_unkorrigiert": float(np.sqrt(p_beob)),
            "rauschen_im_mittel": float(np.sqrt(p_rausch)),
            "snr": float(np.sqrt(max(p_beob - p_rausch, 0.0) / p_rausch))
            if p_rausch > 0 else np.nan,
            "n": n}


def split_half_reliability(epochs: np.ndarray, t: np.ndarray, window,
                           n_rep: int = 500, seed: int = 0) -> float:
    """Wie reproduzierbar ist die Antwort innerhalb der Bedingung?

    Die Epochen werden wiederholt zufällig halbiert und die beiden
    Mittelwerte im Fenster korreliert; zurückgegeben wird der nach
    Spearman-Brown auf die volle Epochenzahl hochgerechnete Median.

    Für einen Reizkopf ist das ein direkteres Gütemaß als die Amplitude:
    ein Applikator, der zuverlässiger reizt, erzeugt von Versuch zu
    Versuch dieselbe Antwort — unabhängig davon, wie groß sie ist.

    **Hängt von n ab.** Bedingungen nur bei gleicher Epochenzahl
    vergleichen, siehe `matched_subsample`.
    """
    ep = np.asarray(epochs, float)[:, _win(t, window)]
    n = len(ep)
    if n < 6:
        return float("nan")
    rng = np.random.default_rng(seed)
    h = n // 2
    rs = []
    for _ in range(n_rep):
        p = rng.permutation(n)
        a, b = ep[p[:h]].mean(0), ep[p[h:2 * h]].mean(0)
        if a.std() > 0 and b.std() > 0:
            rs.append(float(np.corrcoef(a, b)[0, 1]))
    if not rs:
        return float("nan")
    r = float(np.median(rs))
    return 2 * r / (1 + r) if r > -1 else float("nan")   # Spearman-Brown


def single_trial_consistency(epochs: np.ndarray, t: np.ndarray,
                             window) -> dict:
    """Wie deutlich trägt der einzelne Versuch die Antwort schon?

    Jede Epoche wird mit dem Mittelwert der *übrigen* verglichen — der
    eigene Beitrag muss heraus, sonst korreliert jede Epoche schon
    deshalb, weil sie im Mittelwert steckt.

    **Hängt von n ab** (der Vergleichsmittelwert wird mit wachsendem n
    sauberer). Nur bei gleicher Epochenzahl vergleichen.
    """
    ep = np.asarray(epochs, float)[:, _win(t, window)]
    n = len(ep)
    if n < 4:
        return {"r_mittel": float("nan"), "anteil_positiv": float("nan"), "n": n}
    gesamt = ep.sum(axis=0)
    rs = []
    for i in range(n):
        rest = (gesamt - ep[i]) / (n - 1)
        if ep[i].std() > 0 and rest.std() > 0:
            rs.append(float(np.corrcoef(ep[i], rest)[0, 1]))
    rs = np.array(rs)
    return {"r_mittel": float(rs.mean()), "r_sd": float(rs.std()),
            "anteil_positiv": float((rs > 0).mean()), "n": n}


def matched_subsample(epochs_list, n_ziel: int | None = None, seed: int = 0):
    """Mehrere Epochensätze auf dieselbe Anzahl bringen.

    Ohne Angabe wird die kleinste vorkommende Anzahl genommen. Nötig für
    jedes Maß, das von n abhängt — sonst vergleicht man Epochenzahlen
    statt Bedingungen."""
    rng = np.random.default_rng(seed)
    n_ziel = n_ziel or min(len(e) for e in epochs_list)
    return [np.asarray(e, float)[np.sort(rng.choice(len(e), n_ziel,
                                                    replace=False))]
            for e in epochs_list]
