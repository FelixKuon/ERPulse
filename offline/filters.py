"""offline/filters.py — nullphasige Filterung für die Nachverarbeitung.

Gegenstück zu `utils/filters.RealtimeFilter`: dieselben Filterentwürfe
(Butterworth, IIR-Notch), aber mit `sosfiltfilt` zweimal durchlaufen —
vorwärts und rückwärts. Das ist im Betrieb unmöglich (die Zukunft liegt
noch nicht vor), offline aber der bessere Weg:

  * keine Phasenverschiebung, die ERP-Latenzen verzerrt,
  * kein Einschwingen an der Chunk-Grenze,
  * dafür effektiv doppelte Filterordnung und Vor-Echos an steilen
    Artefakten — bei Ordnung 4 unkritisch.

Die Kette wird in der Reihenfolge angewandt, in der sie aufgebaut wurde,
gedacht ist zuerst Hochpass, dann Notch (wie in der Anwendung).
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, iirnotch, sosfilt_zi, sosfiltfilt, sosfreqz, tf2sos


class OfflineFilter:
    """Verkettbare Filterbank. Aufrufbar: `flt(daten)`.

        flt = OfflineFilter(fs=250).highpass(1.0).notch(50.0)
        eeg = flt(session.raw)
    """

    def __init__(self, fs: float = 250.0, detrend: bool = True):
        self.fs = float(fs)
        self.detrend = detrend
        self._stages: list[tuple[str, np.ndarray]] = []

    # ── Aufbau ───────────────────────────────────────────────────────
    def highpass(self, cutoff: float = 1.0, order: int = 4) -> "OfflineFilter":
        sos = butter(order, cutoff, btype="high", fs=self.fs, output="sos")
        self._stages.append((f"Hochpass {cutoff} Hz (Ord. {order})", sos))
        return self

    def lowpass(self, cutoff: float = 40.0, order: int = 4) -> "OfflineFilter":
        sos = butter(order, cutoff, btype="low", fs=self.fs, output="sos")
        self._stages.append((f"Tiefpass {cutoff} Hz (Ord. {order})", sos))
        return self

    def bandpass(self, low: float = 1.0, high: float = 40.0,
                 order: int = 4) -> "OfflineFilter":
        sos = butter(order, [low, high], btype="band", fs=self.fs, output="sos")
        self._stages.append((f"Bandpass {low}–{high} Hz (Ord. {order})", sos))
        return self

    def notch(self, freq: float = 50.0, q: float = 30.0,
              harmonics: int = 1) -> "OfflineFilter":
        """Netzbrumm entfernen. `harmonics=2` filtert zusätzlich 100 Hz —
        Vielfache oberhalb der Nyquistfrequenz werden übersprungen."""
        nyq = self.fs / 2
        for k in range(1, harmonics + 1):
            f0 = freq * k
            if f0 >= nyq:
                break
            b, a = iirnotch(f0, q, fs=self.fs)
            self._stages.append((f"Notch {f0:g} Hz (Q={q:g})", tf2sos(b, a)))
        return self

    # ── Anwendung ────────────────────────────────────────────────────
    def __call__(self, data: np.ndarray) -> np.ndarray:
        """data: (samples, kanäle) oder (samples,) → gleiche Form zurück."""
        x = np.asarray(data, dtype=float)
        one_d = x.ndim == 1
        if one_d:
            x = x[:, None]

        # Der Unicorn liefert Rohwerte mit sehr großem Gleichanteil
        # (~2·10^5 µV). sosfiltfilt spiegelt die Ränder; ohne vorheriges
        # Abziehen des Mittelwerts erzeugt dieser Sockel am Anfang und
        # Ende einen Einschwinger über mehrere Sekunden.
        if self.detrend:
            x = x - x.mean(axis=0, keepdims=True)

        min_len = 3 * max((len(sos) for _, sos in self._stages), default=1) * 2
        if len(x) <= min_len:
            raise ValueError(
                f"Signal zu kurz für filtfilt: {len(x)} Samples")

        for _, sos in self._stages:
            x = sosfiltfilt(sos, x, axis=0)

        return x[:, 0] if one_d else x

    # ── Auskunft ─────────────────────────────────────────────────────
    @property
    def stages(self) -> list:
        return [name for name, _ in self._stages]

    def frequency_response(self, n: int = 8192):
        """Betragsgang der gesamten Kette in dB — für filtfilt, also mit
        |H|² gerechnet, weil zweimal gefiltert wird.

        Rückgabe: (frequenzen_hz, daempfung_db)"""
        f = np.linspace(0, self.fs / 2, n)
        h = np.ones(n, dtype=complex)
        for _, sos in self._stages:
            _, hk = sosfreqz(sos, worN=f, fs=self.fs)
            h *= hk
        return f, 20 * np.log10(np.abs(h) ** 2 + 1e-12)

    def __repr__(self) -> str:
        if not self._stages:
            return f"<OfflineFilter fs={self.fs:g} Hz — leer>"
        return (f"<OfflineFilter fs={self.fs:g} Hz, filtfilt: "
                + " → ".join(self.stages) + ">")


def compare_zero_phase(data: np.ndarray, flt: "OfflineFilter") -> dict:
    """Nullphasig vs. einmalig vorwärts — zeigt die Laufzeit, die man sich
    im Betrieb einhandelt und die offline entfällt.

    Rückgabe: {'filtfilt': (n,k), 'forward': (n,k), 'stages': [...]}
    """
    from scipy.signal import sosfilt

    x = np.asarray(data, dtype=float)
    one_d = x.ndim == 1
    if one_d:
        x = x[:, None]
    if flt.detrend:
        x = x - x.mean(axis=0, keepdims=True)

    fwd = x.copy()
    for _, sos in flt._stages:
        zi = sosfilt_zi(sos)[:, :, None] * fwd[0][None, None, :]
        fwd, _ = sosfilt(sos, fwd, axis=0, zi=zi)

    zp = flt(data)
    if one_d:
        fwd = fwd[:, 0]
    return {"filtfilt": zp, "forward": fwd, "stages": flt.stages}
