import numpy as np
import csv
import os
from datetime import datetime
from collections import deque

class DataRecorder:
    """Zeichnet EEG + Trigger in CSV auf (Unicorn-Format-kompatibel)"""

    CH_NAMES = ["Fz","C3","Cz","C4","Pz","PO7","Oz","PO8","Trigger"]

    def __init__(self):
        self._buffer  = []
        self._triggers = {}   # sample_idx → trigger_val
        self._recording = False
        self._sample_count = 0

    def start(self, path: str = None):
        if path is None:
            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join("recordings", f"ERP_{ts}.csv")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._path     = path
        self._buffer   = []
        self._triggers = {}
        self._sample_count = 0
        self._recording = True
        print(f"[Recorder] Aufnahme gestartet: {path}")

    def add_sample(self, eeg8: np.ndarray, trigger: int = 0):
        """eeg8: 1D Array mit 8 Werten in µV"""
        if not self._recording:
            return
        row = list(eeg8) + [float(trigger)]
        self._buffer.append(row)
        self._sample_count += 1

    def add_trigger(self, trigger_val: int):
        """Trigger beim nächsten Sample eintragen"""
        if self._recording:
            self._triggers[self._sample_count] = trigger_val

    def stop(self) -> str:
        if not self._recording:
            return None
        self._recording = False

        # Trigger in Buffer eintragen
        for idx, val in self._triggers.items():
            if idx < len(self._buffer):
                self._buffer[idx][8] = float(val)

        # CSV schreiben
        with open(self._path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(self._buffer)

        duration = self._sample_count / 250.0
        print(f"[Recorder] Gespeichert: {self._path} "
              f"({self._sample_count} Samples, {duration:.1f}s)")
        return self._path

    @property
    def is_recording(self):
        return self._recording

    @property
    def duration_s(self):
        return self._sample_count / 250.0
