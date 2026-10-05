import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, sosfilt_zi, tf2sos


class RealtimeFilter:
    """Fortlaufender IIR-Filter für Streaming-Daten.

    Wichtig: Der Filterzustand (zi) wird über die Aufrufe hinweg gehalten,
    d.h. process() darf immer nur mit NEUEN Samples aufgerufen werden —
    nicht wiederholt mit demselben (wachsenden) Puffer. Nur so entsteht ein
    durchgehend gefiltertes Signal ohne Sprünge an den Chunk-Grenzen.

    Bei Änderung der Grenzfrequenzen oder der Kanalzahl wird der Zustand
    verworfen und beim nächsten Chunk aus dessen erstem Sample neu
    initialisiert (verhindert einen Einschwing-Sprung durch den DC-Offset).
    """

    def __init__(self, fs=250):
        self.fs = fs
        self.hp_sos = self.lp_sos = self.notch_sos = None
        self.hp_zi  = self.lp_zi  = self.notch_zi  = None
        self.hp_active = self.lp_active = self.notch_active = False

    # ── Konfiguration ────────────────────────────────────────────────
    def set_highpass(self, cutoff=1.0, order=4):
        self.hp_sos = butter(order, cutoff, btype='high', fs=self.fs, output='sos')
        self.hp_zi  = None          # Zustand neu aufbauen
        self.hp_active = True

    def set_lowpass(self, cutoff=40.0, order=4):
        self.lp_sos = butter(order, cutoff, btype='low', fs=self.fs, output='sos')
        self.lp_zi  = None
        self.lp_active = True

    def set_notch(self, freq=50.0, q=30.0):
        b, a = iirnotch(freq, q, fs=self.fs)
        self.notch_sos = tf2sos(b, a)
        self.notch_zi  = None
        self.notch_active = True

    def toggle_hp(self, state: bool):
        if state != self.hp_active:
            self.hp_zi = None       # nach einer Pause sauber neu einschwingen
            # Der Hochpass nimmt (bzw. gibt) den Gleichanteil weg — beim
            # Unicorn Hunderte mV. Die Zustände von Lowpass und Notch
            # stammen noch vom alten Pegel und würden als riesiger Ausschlag
            # ausschwingen (Epochen bis >100 000 µV) — mit neu einschwingen.
            self.lp_zi = None
            self.notch_zi = None
        self.hp_active = state

    def toggle_lp(self, state: bool):
        if state != self.lp_active:
            self.lp_zi = None
        self.lp_active = state

    def toggle_notch(self, state: bool):
        if state != self.notch_active:
            self.notch_zi = None
        self.notch_active = state

    def reset_state(self):
        """Filterzustand verwerfen (z. B. nach einem Verbindungsabbruch)."""
        self.hp_zi = self.lp_zi = self.notch_zi = None

    # ── Verarbeitung ─────────────────────────────────────────────────
    @staticmethod
    def _init_zi(sos, first_sample):
        """Eingeschwungener Anfangszustand pro Kanal, skaliert auf den
        ersten Messwert — sonst würde der DC-Offset einen Sprung erzeugen.
        Ergebnis-Form: (n_sections, 2, n_channels)"""
        return sosfilt_zi(sos)[:, :, None] * first_sample[None, None, :]

    def _apply(self, data, sos, zi):
        if zi is None or zi.shape[2] != data.shape[1]:
            zi = self._init_zi(sos, data[0])
        out, zi = sosfilt(sos, data, axis=0, zi=zi)
        return out, zi

    def process(self, chunk: np.ndarray) -> np.ndarray:
        """chunk: (samples, channels) — nur neue Samples übergeben."""
        if chunk.size == 0:
            return chunk

        out = np.asarray(chunk, dtype=float)

        if self.hp_active and self.hp_sos is not None:
            out, self.hp_zi = self._apply(out, self.hp_sos, self.hp_zi)
        if self.lp_active and self.lp_sos is not None:
            out, self.lp_zi = self._apply(out, self.lp_sos, self.lp_zi)
        if self.notch_active and self.notch_sos is not None:
            out, self.notch_zi = self._apply(out, self.notch_sos, self.notch_zi)

        return out
