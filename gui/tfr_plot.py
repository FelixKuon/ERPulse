import numpy as np
import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from gui.theme import BG_PLOT, TEXT_PRIMARY, BORDER

class TFRPlotWidget(QWidget):

    def __init__(self, fs=250, ch_labels=None, parent=None):
        super().__init__(parent)
        self.fs = fs
        self._img_hi   = None
        self._img_lo   = None
        self._cb_hi    = None
        self._cb_lo    = None
        self._norm     = TwoSlopeNorm(vmin=-4, vcenter=0, vmax=4)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Einmal Figure + Axes erstellen — werden NIE neu erstellt
        self._fig, (self._ax_hi, self._ax_lo) = plt.subplots(
            2, 1, figsize=(8, 4),
            facecolor=BG_PLOT,
            gridspec_kw={'hspace': 0.5}
        )
        for ax in (self._ax_hi, self._ax_lo):
            ax.set_facecolor(BG_PLOT)
            ax.tick_params(colors=TEXT_PRIMARY)
            ax.xaxis.label.set_color(TEXT_PRIMARY)
            ax.yaxis.label.set_color(TEXT_PRIMARY)
            ax.title.set_color(TEXT_PRIMARY)
            for sp in ax.spines.values():
                sp.set_color(BORDER)

        self._ax_hi.set_ylabel('Frequenz [Hz]')
        self._ax_lo.set_ylabel('Frequenz [Hz]')
        self._ax_lo.set_xlabel('Zeit [s]')

        # Placeholder-Bilder: einmal erstellen mit Dummy-Daten
        # set_data() updated nur die Pixel, nie die Axes-Struktur
        dummy_hi = np.zeros((9, 801))
        dummy_lo = np.zeros((10, 801))
        extent_hi = [-1.0, 3.0, 10.0, 50.0]
        extent_lo = [-1.0, 3.0,  1.0, 10.0]

        self._img_hi = self._ax_hi.imshow(
            dummy_hi, origin='lower', aspect='auto',
            cmap='RdYlGn_r', norm=self._norm,
            extent=extent_hi, interpolation='bilinear'
        )
        self._ax_hi.axvline(0, color=TEXT_PRIMARY, lw=1, ls='--', alpha=0.7)
        self._ax_hi.set_title('TFR High (10–50Hz) — n=0', color=TEXT_PRIMARY)
        self._cb_hi = self._fig.colorbar(
            self._img_hi, ax=self._ax_hi, label='z-Score')
        self._cb_hi.ax.yaxis.set_tick_params(color=TEXT_PRIMARY)
        plt.setp(self._cb_hi.ax.yaxis.get_ticklabels(), color=TEXT_PRIMARY)

        self._img_lo = self._ax_lo.imshow(
            dummy_lo, origin='lower', aspect='auto',
            cmap='RdYlGn_r', norm=self._norm,
            extent=extent_lo, interpolation='bilinear'
        )
        self._ax_lo.axvline(0, color=TEXT_PRIMARY, lw=1, ls='--', alpha=0.7)
        self._ax_lo.set_title('TFR Low (1–10Hz) — n=0', color=TEXT_PRIMARY)
        self._cb_lo = self._fig.colorbar(
            self._img_lo, ax=self._ax_lo, label='z-Score')
        self._cb_lo.ax.yaxis.set_tick_params(color=TEXT_PRIMARY)
        plt.setp(self._cb_lo.ax.yaxis.get_ticklabels(), color=TEXT_PRIMARY)

        self._canvas = FigureCanvasQTAgg(self._fig)
        layout.addWidget(self._canvas)

    def update_tfr(self, P_low, P_high, f_low, f_high,
                   t_all, n_epochs):
        if P_low is None or P_high is None:
            return
        if len(t_all) < 2:
            return

        t0, t1 = float(t_all[0]), float(t_all[-1])
        fh0, fh1 = float(f_high[0]), float(f_high[-1])
        fl0, fl1 = float(f_low[0]),  float(f_low[-1])

        # NUR set_data() + set_extent() — keine neuen Artists!
        self._img_hi.set_data(np.clip(P_high, -4, 4))
        self._img_hi.set_extent([t0, t1, fh0, fh1])
        self._ax_hi.set_xlim(t0, t1)
        self._ax_hi.set_ylim(fh0, fh1)
        self._ax_hi.set_title(
            f'TFR High (10–50Hz) — n={n_epochs}', color=TEXT_PRIMARY)

        self._img_lo.set_data(np.clip(P_low, -4, 4))
        self._img_lo.set_extent([t0, t1, fl0, fl1])
        self._ax_lo.set_xlim(t0, t1)
        self._ax_lo.set_ylim(fl0, fl1)
        self._ax_lo.set_title(
            f'TFR Low (1–10Hz) — n={n_epochs}', color=TEXT_PRIMARY)

        # Einmal neu zeichnen
        self._canvas.draw_idle()

    def reset(self):
        self._img_hi.set_data(np.zeros((9, 801)))
        self._img_lo.set_data(np.zeros((10, 801)))
        self._ax_hi.set_title('TFR High (10–50Hz) — n=0', color=TEXT_PRIMARY)
        self._ax_lo.set_title('TFR Low (1–10Hz) — n=0', color=TEXT_PRIMARY)
        self._canvas.draw_idle()
