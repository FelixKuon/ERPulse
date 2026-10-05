"""offline/selection.py — auswählen, welche Trigger in die Mittelung gehen.

Zwei getrennte Fragen, die im Betrieb zusammenfallen, offline aber besser
auseinandergehalten werden:

  * **Welcher Abschnitt der Sitzung?** Am Anfang einer Messung sitzt die
    Person noch nicht ruhig, die Elektroden sind noch nicht eingelaufen.
    "nur die letzten 40 Trigger" ist deshalb eine übliche und ehrliche
    Einschränkung — solange man sie dazusagt.

  * **Welche Epochen sind brauchbar?** Die feste Grenze von 100 µV im
    `ERPProcessor` ist eine Annahme über den Amplitudenmaßstab. Der ändert
    sich zwischen Sitzungen (Impedanz, Verstärkung) erheblich. Ein
    robustes Maß am Median der Sitzung selbst passt sich an: es verwirft,
    was für DIESE Aufnahme untypisch ist.

Beide Schritte arbeiten auf der Trigger-Liste, bevor sie an `replay()`
geht. Die Epochierung selbst bleibt unangetastet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MAD_TO_SIGMA = 0.6745      # MAD → Standardabweichung bei Normalverteilung


def epoch_stats(eeg: np.ndarray, trigger_idx, fs: float = 250.0,
                pre_ms: float = 200, post_ms: float = 800,
                ch_labels=None) -> pd.DataFrame:
    """Kennzahlen je Trigger, ohne zu epochieren oder zu mitteln.

    Gerechnet wird auf denselben Fenstergrenzen und mit derselben
    Baseline-Korrektur wie im `ERPProcessor`, damit `max_abs` mit dessen
    Artefaktgrenze vergleichbar ist.

    Spalten:
      sample, t_s          Lage des Triggers
      vollstaendig         Fenster liegt ganz in der Datei
      max_abs              größter Betrag nach Baseline-Korrektur [µV]
      ptp                  größte Spanne über alle Kanäle [µV]
      rms                  quadratischer Mittelwert der Epoche [µV]
      basis_drift          Steigung der Grundlinie [µV] — verrät Elektroden-
                           bewegung, die der Betrag allein nicht zeigt
      worst_ch             Kanal mit dem größten Betrag
    """
    eeg = np.asarray(eeg, dtype=float)
    pre = int(pre_ms * fs / 1000)
    post = int(post_ms * fs / 1000)
    labels = list(ch_labels or [f"ch{i}" for i in range(eeg.shape[1])])

    rows = []
    for k, s in enumerate(np.asarray(trigger_idx).ravel().astype(int)):
        a, b = s - pre, s + post
        rec = {"nr": k + 1, "sample": int(s), "t_s": round(s / fs, 3)}
        if a < 0 or b > len(eeg):
            rec.update({"vollstaendig": False, "max_abs": np.nan,
                        "ptp": np.nan, "rms": np.nan,
                        "basis_drift": np.nan, "worst_ch": ""})
            rows.append(rec)
            continue

        base = eeg[a:s]
        ep = eeg[a:b] - base.mean(axis=0)
        peak_per_ch = np.abs(ep).max(axis=0)
        half = max(len(base) // 2, 1)
        rec.update({
            "vollstaendig": True,
            "max_abs": round(float(peak_per_ch.max()), 2),
            "ptp": round(float((ep.max(axis=0) - ep.min(axis=0)).max()), 2),
            "rms": round(float(np.sqrt((ep ** 2).mean())), 2),
            "basis_drift": round(float(np.abs(
                base[half:].mean(axis=0) - base[:half].mean(axis=0)).max()), 2),
            "worst_ch": labels[int(np.argmax(peak_per_ch))],
        })
        rows.append(rec)

    return pd.DataFrame(rows)


def select_triggers(stats: pd.DataFrame,
                    last: int | None = None,
                    first: int | None = None,
                    drop_first: int | None = None,
                    drop_last: int | None = None,
                    subset=None,
                    max_abs: float | None = None,
                    mad_k: float | None = None,
                    mad_on: str = "max_abs") -> pd.DataFrame:
    """Auswahl und Ausreißerabweisung auf der Trigger-Tabelle.

    last / first  nur die letzten bzw. ersten N Trigger verwenden
    drop_first    die ersten N Trigger verwerfen. Am Anfang einer Messung
                  ist die Person noch nicht eingestellt und der Reiz wird
                  oft noch nachjustiert — diese Epochen gehören nicht in
                  dieselbe Mittelung wie der Rest.
    drop_last     die letzten N Trigger verwerfen
    subset        ausdrückliche Auswahl: Liste von Trigger-Nummern (1-basiert)
                  oder eine boolesche Maske über alle Trigger
    max_abs       feste Obergrenze in µV
    mad_k         robuste Grenze: verwirft Epochen, deren `mad_on` mehr als
                  k robuste Standardabweichungen über dem Median liegt.
                  Gerechnet auf dem Logarithmus, weil Artefaktamplituden
                  stark rechtsschief verteilt sind — ohne Log zieht ein
                  einzelner großer Ausschlag die Grenze so weit nach oben,
                  dass er selbst noch hineinpasst.
                  Bezugsmenge ist die bereits durch last/first/subset
                  eingeschränkte Auswahl, nicht die ganze Sitzung.
    mad_k tritt zusätzlich zu max_abs in Kraft; es gewinnt, was zuerst greift.

    Rückgabe: `stats` mit den Spalten `gewaehlt` (bool) und `grund` (str),
    dazu `mad_z` wenn mad_k gesetzt ist. Die Reihenfolge bleibt erhalten.
    """
    out = stats.copy()
    n = len(out)
    keep = out["vollstaendig"].to_numpy().copy() if "vollstaendig" in out \
        else np.ones(n, bool)
    grund = np.where(keep, "", "unvollständig").astype(object)

    # ── Abschnitt der Sitzung ────────────────────────────────────────
    if subset is not None:
        sub = np.asarray(subset)
        mask = sub.astype(bool) if sub.dtype == bool else np.isin(
            out["nr"].to_numpy(), sub)
        grund[keep & ~mask] = "nicht gewählt"
        keep &= mask
    if drop_first is not None:
        pos = np.flatnonzero(keep)[:int(drop_first)]
        grund[pos] = "nicht gewählt"
        keep[pos] = False
    if drop_last is not None and int(drop_last) > 0:
        pos = np.flatnonzero(keep)[-int(drop_last):]
        grund[pos] = "nicht gewählt"
        keep[pos] = False
    if first is not None:
        pos = np.flatnonzero(keep)[:int(first)]
        drop = keep.copy()
        drop[pos] = False
        grund[drop] = "nicht gewählt"
        keep &= np.isin(np.arange(n), pos)
    if last is not None:
        pos = np.flatnonzero(keep)[-int(last):]
        drop = keep.copy()
        drop[pos] = False
        grund[drop] = "nicht gewählt"
        keep &= np.isin(np.arange(n), pos)

    # ── Ausreißer ────────────────────────────────────────────────────
    if max_abs is not None:
        bad = keep & (out["max_abs"].to_numpy() > float(max_abs))
        grund[bad] = f"> {max_abs:g} µV"
        keep &= ~bad

    if mad_k is not None:
        vals = out[mad_on].to_numpy(dtype=float)
        z = np.full(n, np.nan)
        ref = vals[keep]
        ref = ref[np.isfinite(ref) & (ref > 0)]
        if len(ref) >= 4:
            lg = np.log(np.where(vals > 0, vals, np.nan))
            med = np.median(np.log(ref))
            mad = np.median(np.abs(np.log(ref) - med))
            if mad > 0:
                z = MAD_TO_SIGMA * (lg - med) / mad
                bad = keep & (z > float(mad_k))
                for i in np.flatnonzero(bad):
                    grund[i] = f"Ausreißer (z={z[i]:.1f})"
                keep &= ~bad
        out["mad_z"] = np.round(z, 2)

    out["gewaehlt"] = keep
    out["grund"] = np.where(keep, "gewählt", grund)
    return out
