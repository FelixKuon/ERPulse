"""
core/replay_reader.py — spielt eine aufgezeichnete Messung wie einen Live-
Stream in die Anwendung ein (Demo / Präsentation, kein Gerät nötig).

Der ReplayReader ist ein Drop-in-Ersatz für den UnicornReader: gleiche
Signale (`samples_received`, `status_changed`, `error`) und gleiche Steuerung
(`pause()`, `resume()`, `stop()`, `is_paused`). Zusätzlich meldet er die
Trigger der Aufnahme selbst über `trigger_received` — die Signatur ist
dieselbe wie beim TriggerReader. Alles danach (Filter, ASR, ERP, TFR,
Rohdaten-Plot) läuft unverändert durch die echte Verarbeitungskette.

Gelesen werden zwei Dateiformate (automatisch erkannt):

  * Aufnahmen dieser Anwendung (`recordings/ERP_*.csv`, mit Kopfzeile
    `t, counter, raw_*, flt_*, trigger, asr`). Abgespielt werden die
    UNGEFILTERTEN `raw_*`-Kanäle, damit die Filter der Oberfläche wirken
    wie im Livebetrieb.
  * Der ältere Unicorn-Recorder (`data/UnicornRecorder_*.csv`, ohne
    Kopfzeile, 8 EEG-Spalten in µV + Trigger-Spalte).

Trigger-Semantik wie überall in der Anwendung: das Sample mit trigger > 0
ist das erste NACH dem Reiz (t = 0). Der Trigger wird deshalb NACH allen
früheren Samples und VOR diesem Sample gemeldet.
"""

import os
import threading
import time

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

FSAMPLE = 250


def load_recording(path: str):
    """Liest eine Aufnahme. Gibt (eeg[n, 8] in µV, trigger[n], counter[n])
    zurück. Wirft ValueError bei unbrauchbaren Dateien."""
    import pandas as pd

    with open(path, "r") as f:
        first = f.readline().strip()

    if first[:1].isalpha():                       # Kopfzeile → Session-Format
        df = pd.read_csv(path)
        cols = [c for c in df.columns if c.startswith("raw_")]
        if len(cols) < 8 or "trigger" not in df.columns:
            raise ValueError("Spalten raw_* / trigger fehlen")
        eeg = df[cols[:8]].to_numpy(dtype=float)
        trig = df["trigger"].to_numpy(dtype=float)
        counter = (df["counter"].to_numpy(dtype=float)
                   if "counter" in df.columns else np.arange(1, len(df) + 1))
    else:                                         # Unicorn-Recorder, ohne Kopfzeile
        df = pd.read_csv(path, header=None)
        if df.shape[1] < 9:
            raise ValueError(f"9 Spalten erwartet, {df.shape[1]} gefunden")
        eeg = df.iloc[:, :8].to_numpy(dtype=float)
        trig = df.iloc[:, 8].to_numpy(dtype=float)
        counter = np.arange(1, len(df) + 1, dtype=float)

    if len(eeg) < FSAMPLE:
        raise ValueError("Aufnahme ist kürzer als eine Sekunde")
    return (np.nan_to_num(eeg), np.nan_to_num(trig), counter)


def trigger_indices(trig: np.ndarray) -> np.ndarray:
    """Sample-Indizes der Reize: Trigger-Wert > 0, der sich gegenüber dem
    Vorgänger ändert (ein über mehrere Samples gehaltener Wert zählt einmal)."""
    prev = np.r_[0.0, trig[:-1]]
    return np.flatnonzero((trig > 0) & (trig != prev))


class ReplayReader(QThread):
    samples_received = pyqtSignal(object, object)   # (ts[n], data[n, 16])
    trigger_received = pyqtSignal(float, str)       # (ts, "TRIGGER:<wert>,<sample>")
    status_changed   = pyqtSignal(str)
    error            = pyqtSignal(str)

    TICK_S    = 0.02    # wie oft Samples nachgeliefert werden (≈ UnicornReader)
    BLOCK_MAX = 50      # Samples pro Signal-Emission

    def __init__(self, path: str, speed: float = 1.0):
        super().__init__()
        self._path  = path
        self._speed = float(speed)
        self._stop_event   = threading.Event()
        self._pause_event  = threading.Event()
        self._resume_event = threading.Event()
        self.dropped_samples = 0     # Schnittstelle wie UnicornReader

    # ── Steuerung (wie UnicornReader) ────────────────────────────────
    def stop(self):
        self._stop_event.set()
        self._resume_event.set()

    def pause(self):
        self._resume_event.clear()
        self._pause_event.set()

    def resume(self):
        self._pause_event.clear()
        self._resume_event.set()

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def force_close_port(self):
        pass    # kein Port — nur für die Schnittstelle

    # ── Thread ───────────────────────────────────────────────────────
    def run(self):
        name = os.path.basename(self._path)
        self.status_changed.emit(f"Lade {name} …")
        try:
            eeg, trig, counter = load_recording(self._path)
        except Exception as e:
            self.error.emit(f"Aufnahme konnte nicht gelesen werden: {e}")
            return

        n = len(eeg)
        trig_idx = trigger_indices(trig)
        nt = len(trig_idx)
        speed_txt = f"  ·  {self._speed:g}× Tempo" if self._speed != 1 else ""
        self.status_changed.emit(
            f"Wiedergabe: {name}  ({n / FSAMPLE:.0f} s, {nt} Trigger){speed_txt}")

        pos, ti = 0, 0
        # Uhr: Sample `pos0` war zur Wanduhrzeit `wall0` fällig. Die Zeit-
        # stempel laufen in Datenzeit (250 Hz) ab `t_base`, unabhängig vom
        # Tempo — das Fenster dreht seine Playout-Uhr entsprechend schneller.
        pos0, wall0 = 0, time.perf_counter()
        i_base, t_base = 0, time.time()

        def ts_of(i):
            return t_base + (i - i_base) / FSAMPLE

        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                self.status_changed.emit("Pausiert")
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    self._resume_event.wait(timeout=0.1)
                if self._stop_event.is_set():
                    break
                pos0, wall0 = pos, time.perf_counter()     # nahtlos weiter
                i_base, t_base = pos, time.time()
                self.status_changed.emit(f"Wiedergabe: {name}{speed_txt}")
                continue

            due = min(n, pos0 + int((time.perf_counter() - wall0)
                                    * FSAMPLE * self._speed))
            while pos < due and not self._stop_event.is_set():
                if ti < nt and trig_idx[ti] == pos:
                    self.trigger_received.emit(
                        ts_of(pos), f"TRIGGER:{int(round(trig[pos]))},{pos}")
                    ti += 1
                    continue
                end = min(due, pos + self.BLOCK_MAX)
                if ti < nt:
                    end = min(end, int(trig_idx[ti]))
                self._emit_block(eeg, counter, pos, end, ts_of)
                pos = end

            if pos >= n:
                self.status_changed.emit(f"Wiedergabe beendet ({name})")
                return
            self._stop_event.wait(self.TICK_S)

    def _emit_block(self, eeg, counter, a, b, ts_of):
        k = b - a
        data = np.zeros((k, 16))
        data[:, :8]  = eeg[a:b]
        data[:, 14]  = 100.0            # Batterie
        data[:, 15]  = counter[a:b]
        ts = ts_of(np.arange(a, b))
        self.samples_received.emit(ts, data)
