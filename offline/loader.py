"""offline/loader.py — Aufnahmen des SessionRecorders einlesen.

Gelesen wird das Format aus `core/session_recorder.py`:
Kopfzeile `t, counter, raw_*, flt_*, trigger, asr`, dazu optional eine
gleichnamige .json mit Metadaten und Ereignisliste.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

CH_LABELS = ["Fz", "C3", "Cz", "C4", "Pz", "PO7", "Oz", "PO8"]


@dataclass
class Session:
    """Eine eingelesene Aufnahme."""

    path: str
    df: pd.DataFrame
    ch_labels: list = field(default_factory=lambda: list(CH_LABELS))
    meta: dict = field(default_factory=dict)
    fs: float = 250.0

    # ── Spalten als Arrays ───────────────────────────────────────────
    @property
    def t(self) -> np.ndarray:
        """Zeit in Sekunden seit Aufnahmebeginn, (n,)."""
        return self.df["t"].to_numpy()

    @property
    def raw(self) -> np.ndarray:
        """Ungefilterte Kanäle in µV, (n, 8)."""
        return self.df[[f"raw_{c}" for c in self.ch_labels]].to_numpy()

    @property
    def flt(self) -> np.ndarray:
        """Wie die Anwendung sie live gefiltert hat, (n, 8) — nur zum
        Vergleich, nicht als Ausgangspunkt der Offline-Auswertung."""
        return self.df[[f"flt_{c}" for c in self.ch_labels]].to_numpy()

    @property
    def trigger(self) -> np.ndarray:
        """Trigger-Spalte, 0 außer beim Trigger-Sample, (n,)."""
        return self.df["trigger"].to_numpy()

    @property
    def asr(self) -> np.ndarray:
        """ASR-Zustand je Sample: 0 aus, 1 Kalibrierung, 2 aktiv."""
        return self.df["asr"].to_numpy()

    @property
    def trigger_idx(self) -> np.ndarray:
        """Sample-Indizes der Trigger — das jeweilige Sample gilt als das
        erste NACH dem Reiz (t = 0)."""
        return np.flatnonzero(self.df["trigger"].to_numpy() > 0)

    @property
    def trigger_values(self) -> np.ndarray:
        """Trigger-Nummern in Reihenfolge des Auftretens."""
        return self.df["trigger"].to_numpy()[self.trigger_idx]

    @property
    def events(self) -> list:
        """Ereignisliste aus der .json — leer, wenn keine vorliegt."""
        return self.meta.get("ereignisse", [])

    @property
    def reset_times(self) -> list:
        """Zeitpunkte in s, an denen die Mittelung im Betrieb zurückgesetzt
        wurde.

        Das setzt die Anzeige auf null, die Aufnahme läuft weiter. Für die
        Offline-Auswertung ist das eine Blockgrenze: die Bedienung hat dort
        neu angefangen, meist weil die Bedingung wechselte oder die
        vorherigen Epochen verworfen werden sollten. Trigger vor dem letzten
        Reset gehören deshalb in der Regel nicht in dieselbe Mittelung wie
        die danach — siehe `triggers_after_last_reset`."""
        return [e["t"] for e in self.events
                if e.get("typ") == "mittelung_zurueckgesetzt"
                and e.get("t") is not None]

    def triggers_after_last_reset(self) -> "np.ndarray":
        """Sample-Indizes der Trigger nach dem letzten Reset der Mittelung.
        Ohne Reset alle Trigger."""
        rs = self.reset_times
        if not rs:
            return self.trigger_idx
        cut = int(max(rs) * self.fs)
        return self.trigger_idx[self.trigger_idx >= cut]

    @property
    def n_samples(self) -> int:
        return len(self.df)

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.fs

    @property
    def live_filter(self) -> dict:
        """Filtereinstellungen, mit denen die flt_*-Spalten entstanden sind."""
        return self.meta.get("filter", {})

    @property
    def dropped_samples(self) -> int:
        """Lücken im Geräte-Counter = verlorene Pakete."""
        c = self.df["counter"].to_numpy()
        d = np.diff(c)
        return int(np.sum(d[d > 1] - 1))

    def __repr__(self) -> str:
        return (f"<Session {os.path.basename(self.path)}: "
                f"{self.n_samples} Samples / {self.duration_s:.1f}s, "
                f"{len(self.trigger_idx)} Trigger, "
                f"{self.dropped_samples} verlorene Samples>")


def load_session(csv_path: str, fs: float = 250.0) -> Session:
    """Eine Aufnahme laden. Die .json mit den Metadaten wird mitgelesen,
    falls vorhanden (bei einem Absturz während der Aufnahme fehlt sie)."""
    df = pd.read_csv(csv_path)

    required = {"t", "counter", "trigger", "asr"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path}: Spalten fehlen: {sorted(missing)}")

    labels = [c[4:] for c in df.columns if c.startswith("raw_")]
    if not labels:
        raise ValueError(f"{csv_path}: keine raw_*-Spalten gefunden")

    meta = {}
    json_path = os.path.splitext(csv_path)[0] + ".json"
    if os.path.exists(json_path):
        with open(json_path) as f:
            meta = json.load(f)

    # Der Recorder schreibt den Schlüssel "abtastrate_hz"; ältere Aufnahmen
    # haben gar keine .json. Beide Schreibweisen werden akzeptiert, damit ein
    # Tippfehler nicht stillschweigend auf die Vorgabe zurückfällt.
    fs_meta = meta.get("abtastrate_hz", meta.get("abtastrate", fs))

    return Session(path=csv_path, df=df, ch_labels=labels,
                   meta=meta, fs=float(fs_meta))


def list_sessions(directory: str = "recordings") -> pd.DataFrame:
    """Übersicht aller Aufnahmen im Ordner — ohne die Daten zu laden.

    Nützlich, um vor der Auswertung zu sehen, welche Datei überhaupt
    genug Trigger enthält."""
    rows = []
    for p in sorted(glob.glob(os.path.join(directory, "*.csv"))):
        try:
            df = pd.read_csv(p, usecols=["t", "trigger"])
        except Exception as e:                       # unvollständige Datei
            rows.append({"datei": os.path.basename(p), "fehler": str(e)})
            continue
        rows.append({
            "datei":    os.path.basename(p),
            "dauer_s":  round(float(df["t"].iloc[-1]), 1) if len(df) else 0.0,
            "samples":  len(df),
            "trigger":  int((df["trigger"] > 0).sum()),
            "mb":       round(os.path.getsize(p) / 1e6, 1),
        })
    return pd.DataFrame(rows)


def channel_report(data: np.ndarray, ch_labels=None,
                   rail_uv: float = 750_000.0) -> pd.DataFrame:
    """Kurze Kanalgüte: Streuung, Extremwerte und Anteil festgefahrener
    Samples.

    Der Unicorn liefert bei abgerissener Elektrode einen konstanten
    Anschlagwert (±750000 µV). So ein Kanal fällt in Mittelwerten sonst
    nicht auf, verdirbt aber jede ROI-Mittelung — deshalb hier getrennt
    ausgewiesen."""
    labels = ch_labels or CH_LABELS[:data.shape[1]]
    rows = []
    for i, lab in enumerate(labels):
        x = data[:, i]
        railed = np.mean(np.abs(np.abs(x) - rail_uv) < 1.0)
        flat = np.mean(np.diff(x) == 0.0) if len(x) > 1 else 0.0
        rows.append({
            "kanal":      lab,
            "mittel":     round(float(x.mean()), 1),
            "std":        round(float(x.std()), 1),
            "p99_abs":    round(float(np.percentile(np.abs(x), 99)), 1),
            "max_abs":    round(float(np.abs(x).max()), 1),
            "anschlag_%": round(float(railed) * 100, 2),
            "konstant_%": round(float(flat) * 100, 2),
        })
    return pd.DataFrame(rows).set_index("kanal")
