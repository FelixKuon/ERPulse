"""offline/replay.py — die Aufnahme durch die Prozessoren der App fahren.

Statt die Epochierung nachzubauen, wird hier der aufgezeichnete Datenstrom
blockweise durch die echten `ERPProcessor` und `TFRProcessor` geschickt —
in derselben Reihenfolge wie im Live-Fenster
(`gui/connection_dev_window.py`; `gui/main_window.py` ist stillgelegt):

    erp.feed(block) → tfr.feed(block) → bei Ablehnung tfr.reject_current()

Damit stimmen Offline-Ergebnis und Live-Anzeige überein, und eine Änderung
an der Epochierung muss nur an einer Stelle gemacht werden.

Der Trigger-Zeitpunkt: das Sample mit `trigger > 0` ist das erste Sample
NACH dem Reiz, also t = 0. `on_trigger()` wird deshalb aufgerufen, bevor
dieses Sample eingespeist wird — genau wie im Betrieb, wo das
Trigger-Signal den Puffer unterbricht.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.erp_processor import ERPProcessor
from core.tfr_processor import TFRProcessor
from offline.selection import epoch_stats, select_triggers

# Blockgröße der Wiedergabe. Im Betrieb liefert der GUI-Timer rund 25
# Samples (100 ms bei 250 Hz). Die Epochengrenzen hängen nicht davon ab —
# nur die Kopplung "ERP lehnt ab → TFR verwirft dieselbe Epoche" setzt
# voraus, dass nicht zwei Epochen im selben Block fertig werden.
DEFAULT_CHUNK = 25


def make_tfr_processor(fs: float = 250.0, pre_ms: float = 1500,
                       post_ms: float = 3500, roi=(0, 2, 4)) -> TFRProcessor:
    """`TFRProcessor` mit abweichenden Fenstern/ROI erzeugen.

    Die Klasse legt Abtastrate, Fenster und ROI als Klassenattribute fest;
    offline will man daran drehen, ohne den Live-Code anzufassen. Deshalb
    eine Ad-hoc-Ableitung statt einer Änderung an `core/`."""
    cls = type("TFRProcessorOffline", (TFRProcessor,), {
        "FS": float(fs), "PRE_MS": float(pre_ms),
        "POST_MS": float(post_ms), "ROI": list(roi),
    })
    return cls()


@dataclass
class ReplayResult:
    """Ergebnis eines Durchlaufs — hält die Prozessoren selbst, damit auch
    alles Übrige (einzelne Epochen, Zwischengrößen) greifbar bleibt."""

    erp: ERPProcessor
    tfr: TFRProcessor | None
    triggers: pd.DataFrame
    fs: float
    ch_labels: list = field(default_factory=list)
    label: str = ""
    pre_ms: float = 200.0
    post_ms: float = 800.0
    params: dict = field(default_factory=dict)

    # ── ERP ──────────────────────────────────────────────────────────
    @property
    def time_axis(self) -> np.ndarray:
        """Zeitachse der Epoche in ms, (pre+post,)."""
        return self.erp.time_axis

    @property
    def erp_mean(self) -> np.ndarray:
        """Mittelwert über akzeptierte Epochen, (pre+post, 8)."""
        return self.erp.erp_mean

    @property
    def epochs(self) -> np.ndarray:
        """Alle akzeptierten Epochen, (n_epochen, pre+post, 8)."""
        return np.array(self.erp.epochs)

    @property
    def n_accepted(self) -> int:
        return self.erp.n_accepted

    @property
    def n_rejected(self) -> int:
        return self.erp.n_rejected

    def erp_sem(self) -> np.ndarray:
        """Standardfehler des Mittelwerts je Zeitpunkt und Kanal."""
        ep = self.epochs
        if len(ep) < 2:
            return np.zeros_like(self.erp_mean)
        return ep.std(axis=0, ddof=1) / np.sqrt(len(ep))

    def ch(self, name) -> int:
        """Kanalindex zu einem Namen ('Cz') — Indizes gehen unverändert durch."""
        if isinstance(name, (int, np.integer)):
            return int(name)
        return self.ch_labels.index(str(name))

    def trace(self, channel) -> np.ndarray:
        """Gemittelte Kurve eines Kanals, (pre+post,)."""
        return self.erp_mean[:, self.ch(channel)]

    def epoch_traces(self, channel) -> np.ndarray:
        """Einzelepochen eines Kanals, (n_epochen, pre+post)."""
        return self.epochs[:, :, self.ch(channel)]

    def summary(self) -> dict:
        counts = self.triggers["status"].value_counts().to_dict()
        return {"label": self.label, "fenster_ms": (-self.pre_ms, self.post_ms),
                "n_epochen": self.n_accepted,
                "tfr_epochen": self.tfr.n_epochs if self.tfr else 0,
                **self.params, **counts}

    def __repr__(self) -> str:
        tfr_n = self.tfr.n_epochs if self.tfr is not None else 0
        p = self.params
        sel = ""
        if p.get("n_trigger_gesamt"):
            sel = f" [{p['n_trigger_gewaehlt']}/{p['n_trigger_gesamt']} Trigger gewählt]"
        return (f"<ReplayResult {self.label or ''} "
                f"{-self.pre_ms:.0f}…{self.post_ms:.0f} ms · "
                f"ERP: {self.n_accepted} akzeptiert / "
                f"{self.n_rejected} abgelehnt, TFR: {tfr_n}{sel}>")


def replay(eeg: np.ndarray, trigger_idx, fs: float = 250.0,
           pre_ms: float = 200, post_ms: float = 800,
           threshold: float | None = 100.0,
           last: int | None = None, first: int | None = None,
           drop_first: int | None = None, drop_last: int | None = None,
           subset=None, mad_k: float | None = None,
           with_tfr: bool = True,
           tfr_pre_ms: float = 1500, tfr_post_ms: float = 3500,
           tfr_roi=(0, 2, 4),
           chunk: int = DEFAULT_CHUNK,
           ch_labels=None, label: str = "",
           verbose: bool = False) -> ReplayResult:
    """Gefiltertes EEG samt Triggern durch ERP- und TFR-Prozessor fahren.

    eeg:         (samples, kanäle), bereits gefiltert
    trigger_idx: Sample-Indizes der Reize (`Session.trigger_idx`)
    pre_ms/post_ms  ERP-Fenster; post_ms=2000 für späte Komponenten
    threshold:   feste Artefaktgrenze in µV wie in der App, `None` = keine

    Auswahl der Trigger — greift VOR der Epochierung, siehe
    `offline.selection`:
    last:        nur die letzten N Trigger (z. B. last=40)
    first:       nur die ersten N
    drop_first:  die ersten N verwerfen (Einlaufphase der Messung)
    drop_last:   die letzten N verwerfen
    subset:      ausdrückliche Trigger-Nummern (1-basiert) oder Maske
    mad_k:       robuste Ausreißergrenze in robusten Standardabweichungen
                 über dem Median der gewählten Epochen (üblich 3–4)

    with_tfr:    TFR mitrechnen (deutlich langsamer als das ERP allein)
    verbose:     die Meldungen der Prozessoren durchlassen

    Weil verworfene Trigger gar nicht erst gemeldet werden, wächst der
    Abstand zwischen den verbleibenden — dadurch fallen weniger Epochen
    dem Doppel-Trigger-Schutz zum Opfer als bei einer Abweisung im
    Prozessor.
    """
    eeg = np.asarray(eeg, dtype=float)
    if eeg.ndim != 2:
        raise ValueError(f"eeg muss (samples, kanäle) sein, ist {eeg.shape}")

    n = len(eeg)
    all_trig = sorted(int(i) for i in np.asarray(trigger_idx).ravel()
                      if 0 <= int(i) < n)

    stats = epoch_stats(eeg, all_trig, fs=fs, pre_ms=pre_ms, post_ms=post_ms,
                        ch_labels=ch_labels)
    stats = select_triggers(stats, last=last, first=first,
                            drop_first=drop_first, drop_last=drop_last,
                            subset=subset, mad_k=mad_k)
    trig = [int(s) for s in stats.loc[stats["gewaehlt"], "sample"]]

    erp = ERPProcessor(fs=fs, pre_ms=pre_ms, post_ms=post_ms,
                       threshold=np.inf if threshold is None else threshold)
    tfr = make_tfr_processor(fs, tfr_pre_ms, tfr_post_ms, tfr_roi) \
        if with_tfr else None

    records = []       # je Trigger ein Eintrag, Status wird nachgetragen
    pending = []       # Indizes in `records`, deren Epoche noch läuft

    sink = io.StringIO()
    ctx = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(sink)

    with ctx:
        pos, ti = 0, 0
        while pos < n:
            # Trigger, die genau auf diesem Sample liegen, zuerst melden
            while ti < len(trig) and trig[ti] == pos:
                # `_collecting` heißt: die vorige Epoche läuft noch, der
                # Prozessor verwirft diesen Trigger (Doppel-Trigger).
                ignored = erp._collecting
                records.append({"sample": pos, "t_s": pos / fs,
                                "status": "ignoriert" if ignored else "offen"})
                if not ignored:
                    pending.append(len(records) - 1)
                erp.on_trigger()
                if tfr is not None:
                    tfr.on_trigger()
                ti += 1

            stop = trig[ti] if ti < len(trig) else n
            stop = min(stop, pos + chunk)
            block = eeg[pos:stop]

            new_epoch, accepted = erp.feed(block)
            if tfr is not None:
                tfr.feed(block)
            if new_epoch:
                if not accepted and tfr is not None:
                    tfr.reject_current()
                if pending:
                    records[pending.pop(0)]["status"] = \
                        "akzeptiert" if accepted else "abgelehnt"

            pos = stop

    # Trigger am Dateiende: das Nachfenster ist nicht vollständig
    for i in pending:
        records[i]["status"] = "unvollständig"

    # Die Durchlauf-Ergebnisse zurück in die vollständige Trigger-Tabelle
    # tragen: sie enthält auch die vorher aussortierten, damit man in einer
    # einzigen Übersicht sieht, was aus jedem Reiz geworden ist.
    played = {r["sample"]: r["status"] for r in records}
    for i in pending:
        played[records[i]["sample"]] = "unvollständig"

    df = stats.copy()
    df["status"] = [played.get(int(s), g)
                    for s, g in zip(df["sample"], df["grund"])]
    df = df.drop(columns=["grund", "gewaehlt", "vollstaendig"])

    return ReplayResult(erp=erp, tfr=tfr, triggers=df, fs=fs,
                        ch_labels=list(ch_labels or []), label=label,
                        pre_ms=pre_ms, post_ms=post_ms,
                        params={"threshold": threshold, "last": last,
                                "first": first, "mad_k": mad_k,
                                "n_trigger_gesamt": len(all_trig),
                                "n_trigger_gewaehlt": len(trig)})


