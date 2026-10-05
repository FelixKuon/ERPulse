"""
core/session_recorder.py — zeichnet eine komplette Messsitzung auf.

Geschrieben werden zwei Dateien pro Aufnahme:

  ERP_<zeitstempel>.csv    Sample für Sample, mit Kopfzeile:
        t          Zeitstempel in Sekunden seit Aufnahmebeginn
        counter    Sample-Counter des Geräts (Lücken = Paketverlust)
        raw_*      die 8 unverarbeiteten EEG-Kanäle in µV
        flt_*      dieselben Kanäle nach Filter (und ASR, falls aktiv)
        trigger    0, sonst die Trigger-Nummer beim betreffenden Sample
        asr        0 = aus, 1 = Kalibrierung läuft, 2 = ASR aktiv

  ERP_<zeitstempel>.json   Metadaten: Startzeit, Abtastrate, Kanalnamen,
        Filtereinstellungen, ASR-Grenzwert, sowie eine Ereignisliste
        (Trigger, Beginn/Ende der ASR-Kalibrierung, ASR ein/aus).

Die CSV wird fortlaufend geschrieben, nicht erst am Ende — eine lange
Sitzung belegt dadurch keinen wachsenden Arbeitsspeicher, und bei einem
Absturz ist alles bis dahin Aufgezeichnete erhalten.
"""

import csv
import json
import os
import time
from datetime import datetime

import numpy as np

ASR_CODE = {"idle": 0, "calibrating": 1, "ready": 0, "running": 2}


class SessionRecorder:

    def __init__(self, out_dir: str = "recordings", ch_labels=None):
        self.out_dir = out_dir
        self.ch_labels = ch_labels or ["Fz", "C3", "Cz", "C4",
                                        "Pz", "PO7", "Oz", "PO8"]
        self._fh = None
        self._writer = None
        self._recording = False
        self._path = None
        self._t0 = None
        self._sample_count = 0
        self._pending_triggers = []
        self._events = []
        self._meta = {}
        self._held = None            # zurückgehaltener Block, s. add_block()
        self._last_sample_t = None

    # ── Lebenszyklus ─────────────────────────────────────────────────
    def start(self, meta: dict = None) -> str:
        if self._recording:
            return self._path

        os.makedirs(self.out_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = os.path.join(self.out_dir, f"ERP_{stamp}.csv")

        self._fh = open(self._path, "w", newline="")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(
            ["t", "counter"]
            + [f"raw_{c}" for c in self.ch_labels]
            + [f"flt_{c}" for c in self.ch_labels]
            + ["trigger", "asr"]
        )

        self._recording = True
        self._t0 = None
        self._sample_count = 0
        self._pending_triggers = []
        self._events = []
        self._held = None
        self._last_sample_t = None
        self._meta = dict(meta or {})
        self._meta.update({
            "gestartet": datetime.now().isoformat(timespec="seconds"),
            "kanaele": self.ch_labels,
        })
        return self._path

    def stop(self) -> str:
        if not self._recording:
            return None
        self._flush_held()       # letzten zurückgehaltenen Block schreiben
        self._recording = False

        if self._fh is not None:
            self._fh.close()
            self._fh = None
            self._writer = None

        self._meta.update({
            "beendet": datetime.now().isoformat(timespec="seconds"),
            "samples": self._sample_count,
            "dauer_s": round(self.duration_s, 2),
            "ereignisse": self._events,
        })
        with open(os.path.splitext(self._path)[0] + ".json", "w") as f:
            json.dump(self._meta, f, indent=2, ensure_ascii=False)

        return self._path

    # ── Daten ────────────────────────────────────────────────────────
    def add_block(self, ts: np.ndarray, raw8: np.ndarray,
                  flt8: np.ndarray, counters: np.ndarray, asr_state: str):
        """Einen Block neuer Samples anhängen. ts in Sekunden (absolut),
        raw8/flt8 je (n, 8), counters (n,).

        Der jeweils jüngste Block wird zurückgehalten und erst beim nächsten
        Aufruf geschrieben. Grund: Ein Trigger trifft asynchron ein, oft erst
        nachdem sein Sample schon eingelesen wurde — durch das Zurückhalten
        kann er noch exakt dem richtigen Sample zugeordnet werden statt einem
        späteren."""
        if not self._recording or len(ts) == 0:
            return

        if self._t0 is None:
            self._t0 = float(ts[0])
        self._last_sample_t = float(ts[-1])

        self._flush_held()
        self._held = (np.asarray(ts, dtype=float),
                      np.asarray(raw8, dtype=float),
                      np.asarray(flt8, dtype=float),
                      np.asarray(counters, dtype=float),
                      ASR_CODE.get(asr_state, 0))

    def _flush_held(self):
        if self._held is None:
            return
        ts, raw8, flt8, counters, asr_code = self._held
        self._held = None

        rows = np.column_stack([
            ts - self._t0,
            counters,
            raw8,
            flt8,
            self._assign_triggers(ts),
            np.full(len(ts), asr_code, dtype=float),
        ])
        self._writer.writerows(np.round(rows, 4).tolist())
        self._sample_count += len(ts)

    def _assign_triggers(self, ts: np.ndarray) -> np.ndarray:
        """Ordnet wartende Trigger dem zeitlich nächstliegenden Sample zu.
        Trigger, die zeitlich noch hinter diesem Block liegen, bleiben für
        den nächsten liegen."""
        col = np.zeros(len(ts))
        if not self._pending_triggers:
            return col

        still_pending = []
        for t_trig, value in self._pending_triggers:
            if t_trig > ts[-1]:
                still_pending.append((t_trig, value))
                continue
            col[int(np.argmin(np.abs(ts - t_trig)))] = value
        self._pending_triggers = still_pending
        return col

    # ── Ereignisse ───────────────────────────────────────────────────
    def mark_trigger(self, ts: float, marker: str):
        """Trigger vormerken — die Zuordnung zum Sample erfolgt im nächsten
        Block anhand des Zeitstempels."""
        if not self._recording:
            return
        self._pending_triggers.append((ts, self._trigger_value(marker)))
        self._log_event(ts, "trigger", marker)

    def mark_event(self, kind: str, detail=None, ts: float = None):
        """Zustandswechsel festhalten, z. B. Beginn/Ende der ASR-Kalibrierung.

        Ohne ausdrücklichen Zeitstempel wird der Zeitpunkt des zuletzt
        eingetroffenen Samples verwendet — nicht die Wanduhr. Nur so liegt
        das Ereignis auf derselben Zeitachse wie die aufgezeichneten Daten."""
        if not self._recording:
            return
        if ts is None:
            ts = self._last_sample_t if self._last_sample_t is not None else time.time()
        self._log_event(ts, kind, detail)

    def _log_event(self, ts: float, kind: str, detail):
        t_rel = None if self._t0 is None else round(float(ts) - self._t0, 4)
        self._events.append({"t": t_rel, "typ": kind, "detail": detail})

    @staticmethod
    def _trigger_value(marker: str) -> float:
        """'TRIGGER:1,4210' -> 1.0 ; sonst 1.0 als Vorgabe."""
        try:
            return float(marker.split(":")[1].split(",")[0])
        except (IndexError, ValueError):
            return 1.0

    # ── Status ───────────────────────────────────────────────────────
    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def path(self):
        return self._path

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def duration_s(self) -> float:
        return self._sample_count / 250.0
