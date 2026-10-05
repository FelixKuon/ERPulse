import numpy as np
from collections import deque
from scipy.signal import stft, get_window
from scipy.ndimage import gaussian_filter

class TFRProcessor:
    FS      = 250
    PRE_MS  = 1500
    POST_MS = 3500
    ROI     = [0, 2, 4]

    def __init__(self):
        self.pre  = int(self.PRE_MS  * self.FS / 1000)   # 375
        self.post = int(self.POST_MS * self.FS / 1000)   # 875

        self._pre_buf      = deque(maxlen=self.pre * 4)
        self._collecting   = False
        self._post_buf     = []
        self._pre_snapshot = None

        self.P_total    = None
        self.f_all      = None
        self.t_all      = None
        self.n_epochs   = 0
        self._n_lo      = 0
        self.new_result = False

        # Inkrementelle Mittelung
        self._sum_PL = None
        self._sum_PH = None
        self._axes   = None
        self._reject_current = False

    def feed(self, eeg8: np.ndarray):
        roi = eeg8[:, self.ROI].mean(axis=1)
        for v in roi:
            self._pre_buf.append(v)
            if self._collecting:
                self._post_buf.append(v)
                if len(self._post_buf) >= self.post:
                    self._finalize()
                    self._collecting = False

    def on_trigger(self):
        if self._collecting:
            print(f"[TFR.on_trigger] Doppel-Trigger ignoriert "
                  f"(post_buf={len(self._post_buf)}/{self.post})")
            return
        if len(self._pre_buf) >= self.pre:
            self._pre_snapshot = np.array(
                list(self._pre_buf)[-self.pre:])
        else:
            self._pre_snapshot = np.zeros(self.pre)
        self._post_buf   = []
        self._collecting = True
        print(f"[TFR.on_trigger] Sammle Epoche "
              f"(pre_buf={len(self._pre_buf)})")

    def _finalize(self):
        ep = np.concatenate([
            self._pre_snapshot,
            np.array(self._post_buf[:self.post])
        ])
        ep -= ep[:self.pre].mean()

        if self._reject_current:
            self._reject_current = False
            print("[TFR] Epoche verworfen (Artefakt im ERP)")
            return

        # Nur zählen — die Einzelepochen werden nach dem Aufsummieren nicht
        # mehr gebraucht (die Mittelung läuft inkrementell über _sum_PL/_PH).
        self.n_epochs += 1
        self._accumulate(ep)
        self._recompute()

    def _stft_pow(self, x, win_ms, step_ms=5):
        nperseg  = int(self.FS * win_ms / 1000)
        hop      = int(self.FS * step_ms / 1000)
        noverlap = max(nperseg - hop, 0)
        t_off    = -self.PRE_MS / 1000
        f, t, Z  = stft(x, fs=self.FS,
                        window=get_window('hann', nperseg),
                        nperseg=nperseg, noverlap=noverlap,
                        boundary=None, padded=False)
        return f, t + t_off, np.abs(Z)**2

    def _accumulate(self, ep: np.ndarray):
        """Nur die NEUE Epoche transformieren und zur laufenden Summe
        addieren — statt bei jeder Epoche die STFT aller Epochen erneut zu
        rechnen (das wuchs linear mit der Sitzungsdauer). Der Mittelwert
        ist derselbe, der Aufwand bleibt konstant."""
        fL, tL, PL_e = self._stft_pow(ep, 1000)
        fH, tH, PH_e = self._stft_pow(ep, 200)

        if self._axes is None:
            mL = (fL >= 1) & (fL <= 10)
            mH = (fH >= 10) & (fH <= 50)
            self._axes = (fL[mL], tL, mL, fH[mH], tH, mH)

        _, _, mL, _, _, mH = self._axes
        PL_e, PH_e = PL_e[mL], PH_e[mH]

        if self._sum_PL is None:
            self._sum_PL = PL_e.copy()
            self._sum_PH = PH_e.copy()
        else:
            self._sum_PL += PL_e
            self._sum_PH += PH_e

    def _recompute(self):
        fL, tL, _, fH, tH, _ = self._axes
        PL = self._sum_PL / self.n_epochs
        PH = self._sum_PH / self.n_epochs

        step_s = 0.005
        t_com  = np.arange(max(tL[0],tH[0]),
                           min(tL[-1],tH[-1])+1e-9, step_s)
        PL_i = np.array([np.interp(t_com,tL,PL[k])
                         for k in range(len(fL))])
        PH_i = np.array([np.interp(t_com,tH,PH[k])
                         for k in range(len(fH))])
        P_all = np.vstack([PL_i, PH_i])

        bl_mask = (t_com >= -1.0) & (t_com <= -0.2)
        if bl_mask.sum() == 0:
            bl_mask = t_com < 0
        P_db = 10 * np.log10(P_all + 1e-30)
        bl   = P_db[:, bl_mask].mean(axis=1, keepdims=True)
        sd   = P_db[:, bl_mask].std(axis=1,  keepdims=True) + 1e-12
        P_norm = gaussian_filter((P_db - bl) / sd, sigma=(0.5, 0.5))

        self._n_lo    = len(fL)
        self.P_total  = P_norm
        self.f_all    = np.r_[fL, fH]
        self.t_all    = t_com
        self.new_result = True
        print(f"[TFR._recompute] fertig: P={P_norm.shape} "
              f"min={P_norm.min():.2f} max={P_norm.max():.2f}")

    def reject_current(self):
        """Verwirft die gerade laufende Epochensammlung.

        Wichtig: Das ERP-Fenster endet nach 800 ms, das TFR-Fenster erst
        nach 3500 ms. Wenn das ERP eine Epoche als Artefakt ablehnt, ist
        die zugehörige TFR-Epoche also noch in der Sammlung — sie wird hier
        vorgemerkt und beim Abschluss verworfen. (Zuvor wurde stattdessen
        die letzte bereits fertige Epoche entfernt, also die des
        vorherigen Triggers.)
        """
        if self._collecting:
            self._reject_current = True

    @property
    def P_low(self):
        if self.P_total is None: return None
        return self.P_total[:self._n_lo]

    @property
    def P_high(self):
        if self.P_total is None: return None
        return self.P_total[self._n_lo:]

    @property
    def f_low(self):
        if self.f_all is None: return None
        return self.f_all[:self._n_lo]

    @property
    def f_high(self):
        if self.f_all is None: return None
        return self.f_all[self._n_lo:]

    def reset(self):
        self.P_total     = None
        self.f_all       = None
        self.t_all       = None
        self.n_epochs    = 0
        self._collecting = False
        self.new_result  = False
        self._sum_PL     = None
        self._sum_PH     = None
        self._axes       = None
        self._reject_current = False
