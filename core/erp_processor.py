import numpy as np
from collections import deque

class ERPProcessor:
    """
    Epochierung durch Forward-Collection:
    Bei Trigger werden pre_ms vor dem Trigger (aus Ring-Buffer)
    + post_ms nach dem Trigger (live gesammelt) kombiniert.
    """

    def __init__(self, fs=250, pre_ms=200, post_ms=800,
                 threshold=100.0, store_epochs=True):
        self.fs        = fs
        self.pre       = int(pre_ms  * fs / 1000)   # 50
        self.post      = int(post_ms * fs / 1000)   # 200
        self.threshold = threshold
        self.pre_ms    = pre_ms
        self.post_ms   = post_ms
        # Einzelepochen aufheben? Für die Offline-Auswertung ja (SEM,
        # Einzeltrials, Permutationstest). Im Live-Betrieb nein — sie
        # werden dort nie gelesen und der Speicher wächst nur mit.
        self.store_epochs = store_epochs

        # Ring-Buffer für pre-Stimulus Daten
        self._pre_buf  = deque(maxlen=self.pre * 4)

        # Epoch-Sammlung nach Trigger
        self._collecting   = False
        self._post_buf     = []
        self._pre_snapshot = None

        # Ergebnisse
        self.epochs    = []
        self._sum      = None          # laufende Summe der akzeptierten Epochen
        self.erp_mean  = np.zeros((self.pre + self.post, 8))
        self.time_axis = np.linspace(-pre_ms, post_ms,
                                      self.pre + self.post)
        self.n_accepted = 0
        self.n_rejected = 0

    def feed(self, eeg8: np.ndarray):
        """
        Jeden Frame aufrufen mit gefiltertem EEG (n_samples, 8).
        Gibt (new_epoch, accepted) zurück.
        """
        new_epoch = False
        accepted  = False
        for sample in eeg8:
            self._pre_buf.append(sample.copy())

            if self._collecting:
                self._post_buf.append(sample.copy())
                if len(self._post_buf) >= self.post:
                    accepted  = self._finalize_epoch()
                    new_epoch = True
                    self._collecting = False

        return new_epoch, accepted

    def on_trigger(self):
        """Bei Trigger aufrufen — startet Epoch-Sammlung."""
        # Ignoriere Trigger wenn noch collecting (Doppel-Trigger)
        if self._collecting:
            print(f"[ERP.on_trigger] Doppel-Trigger ignoriert "
                  f"(post_buf={len(self._post_buf)}/{self.post})")
            return
            
        if len(self._pre_buf) >= self.pre:
            pre_data = list(self._pre_buf)[-self.pre:]
            self._pre_snapshot = np.array(pre_data)
        else:
            print(f"[ERP] Pre-Buffer zu klein: "
                  f"{len(self._pre_buf)}/{self.pre}")
            self._pre_snapshot = np.zeros((self.pre, 8))

        self._post_buf   = []
        self._collecting = True
        print(f"[ERP.on_trigger] Sammle Epoche "
              f"(pre_buf={len(self._pre_buf)})") 

    def _finalize_epoch(self) -> bool:
        pre  = self._pre_snapshot
        post = np.array(self._post_buf[:self.post])
        ep   = np.vstack([pre, post])    # (pre+post, 8)

        # Baseline-Korrektur
        ep -= ep[:self.pre].mean(axis=0)

        # Artefakt-Check
        if np.abs(ep).max() > self.threshold:
            self.n_rejected += 1
            print(f"[ERP] Abgelehnt — max={np.abs(ep).max():.1f} µV")
            return False

        if self.store_epochs:
            self.epochs.append(ep)
        self.n_accepted += 1
        # Laufende Summe statt np.mean über die ganze Liste — sonst wächst
        # der Aufwand pro Epoche linear mit der Sitzungsdauer.
        self._sum = ep.copy() if self._sum is None else self._sum + ep
        self.erp_mean = self._sum / self.n_accepted
        print(f"[ERP] Epoche {self.n_accepted} akzeptiert")
        return True

    def reset(self):
        self.epochs     = []
        self._sum       = None
        self.erp_mean   = np.zeros((self.pre + self.post, 8))
        self.n_accepted = 0
        self.n_rejected = 0
        self._collecting   = False
        self._pre_snapshot = None
        self._post_buf     = []
