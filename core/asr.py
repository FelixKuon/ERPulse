import numpy as np
import threading

class ASRCalibrator:
    """
    Wrapper um meegkit ASR.
    Zustände: idle → calibrating → ready → running
    """
    # meegkit-Doku: 2.5 = aggressivster sinnvoller Wert, 5 = konservativ
    # (und meegkits eigener Standard). Höhere Werte greifen schwächer ein.
    def __init__(self, fs=250, cutoff=12.0):
        self.fs      = fs
        self.cutoff  = cutoff
        self.state   = "idle"     # idle | calibrating | ready | running
        self._asr    = None
        self._lock   = threading.Lock()
        self.status_callback = None   # GUI kann Callback registrieren

    def start_calibration(self, duration_s=30):
        """Startet Kalibrierung – GUI zeigt "Bitte stillhalten!" an"""
        self.state = "calibrating"
        self._calib_buffer = []
        self._calib_total  = 0
        self._last_countdown = None
        self._calib_samples_needed = int(duration_s * self.fs)
        self._notify(f"Kalibrierung: Bitte {duration_s}s stillhalten!")

    def feed_calibration(self, chunk: np.ndarray):
        """chunk: (samples, channels) – während Kalibrierungsphase aufrufen"""
        if self.state != "calibrating":
            return
        self._calib_buffer.append(chunk)
        self._calib_total += chunk.shape[0]
        total = self._calib_total

        # Sekundengenauer Countdown, unabhängig von der Chunk-Größe
        remaining_s = max(0, (self._calib_samples_needed - total)) // self.fs
        if remaining_s != self._last_countdown:
            self._last_countdown = remaining_s
            self._notify(f"Kalibrierung: noch {remaining_s} s — bitte stillhalten")

        if total >= self._calib_samples_needed:
            try:
                import meegkit
            except ImportError:
                self._notify("meegkit nicht installiert: pip install meegkit")
                self.state = "idle"
                return
            try:
                self._fit()
            except Exception as e:
                self.state = "idle"
                self._notify(f"ASR Fehler: {str(e)}")

    def _fit(self):
        from meegkit.asr import ASR
        data = np.concatenate(self._calib_buffer, axis=0).T  # (channels, samples)

        # Grobe Qualitätsprüfung: ASR erwartet weitgehend artefaktfreie
        # Ruhedaten. Sind die Kalibrierdaten selbst stark verrauscht, wird
        # die Schwelle zu hoch angesetzt und die Korrektur greift kaum.
        peak = float(np.abs(data).max())
        self._notify(f"Berechne ASR (Spitze {peak:.0f} µV) …")

        self._asr = ASR(sfreq=self.fs, cutoff=self.cutoff)
        self._asr.fit(data)
        self.state = "ready"

        hint = "" if peak < 200 else "  ⚠ unruhige Kalibrierdaten"
        self._notify(f"✓ ASR bereit (Grenzwert {self.cutoff:g}){hint}")

    def cancel_calibration(self):
        """Laufende Kalibrierung abbrechen. Nötig, wenn der Stream
        zwischendurch endet — sonst bliebe der Zustand für immer auf
        'calibrating' stehen."""
        if self.state != "calibrating":
            return
        self._calib_buffer = []
        self._calib_total = 0
        # War schon einmal kalibriert? Dann bleibt das alte Modell nutzbar.
        self.state = "ready" if self._asr is not None else "idle"
        self._notify("Kalibrierung abgebrochen")

    def process(self, chunk: np.ndarray) -> np.ndarray:
        """chunk: (samples, channels) → bereinigt zurück"""
        if self.state != "running" or self._asr is None:
            return chunk
        with self._lock:
            out = self._asr.transform(chunk.T)
            if isinstance(out, tuple) and len(out) >= 1:
                cleaned = out[0]
            else:
                cleaned = out
            return cleaned.T

    def start_processing(self):
        if self.state == "ready":
            self.state = "running"
            self._notify("ASR aktiv")

    def stop_processing(self):
        if self.state == "running":
            self.state = "ready"
            self._notify("ASR pausiert")

    def _notify(self, msg):
        if self.status_callback:
            self.status_callback(msg)
