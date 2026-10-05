import pyqtgraph as pg
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import QTimer
from scipy.ndimage import uniform_filter1d

from gui.theme import CHANNEL_COLORS as COLORS

class RawPlotWidget(QWidget):
    def __init__(self, ch_labels, fs=250, window_s=5):
        super().__init__()
        self.labels   = ch_labels
        self.fs       = fs
        self._fs      = 250
        self.window_n = fs * window_s
        self.window_s = window_s
        self._aligned = True   # Y-Skalierung läuft dauerhaft automatisch
        self._last_std = [None] * len(ch_labels)   # zuletzt gesetzter Y-Bereich
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.pw = pg.GraphicsLayoutWidget(title="Rohdaten EEG")
        layout.addWidget(self.pw)
        self.plots  = []
        self.curves = []
        for i, label in enumerate(self.labels):
            p = self.pw.addPlot(row=i, col=0)
            p.setLabel('left', label, units='µV')
            p.showGrid(x=False, y=True, alpha=0.3)
            p.setXRange(-self.window_s, 0, padding=0)
            # Keine Maus-Interaktion: das Fenster ist fest (5 s, Y automatisch),
            # Zoom/Pan würde die Ansicht nur ungewollt verstellen.
            p.setMouseEnabled(x=False, y=False)
            p.hideButtons()
            p.setMenuEnabled(False)
            if i < len(self.labels) - 1:
                p.getAxis('bottom').setStyle(showValues=False)
            # antialias=False: 8 fortlaufend scrollende Kurven bei 25 fps sind
            # mit Kantenglättung auf macOS spürbar teurer — für die Live-Kurve
            # ist der Unterschied im Bild minimal.
            curve = p.plot(pen=pg.mkPen(color=COLORS[i], width=1.2),
                           connect='finite', antialias=False)
            self.plots.append(p)
            self.curves.append(curve)

    def add_trigger_marker(self, t_rel: float):
        """t_rel: Zeit relativ zu jetzt in Sekunden (negativ = Vergangenheit)"""
        for p in self.plots:
            line = pg.InfiniteLine(
                pos=t_rel, angle=90,
                pen=pg.mkPen(color='yellow', width=1.5,
                             style=pg.QtCore.Qt.PenStyle.DashLine)
            )
            p.addItem(line)
            QTimer.singleShot(5000, lambda l=line, pl=p: pl.removeItem(l))

    def update_data(self, timestamps, data, t_ref=None):
        """t_ref: Bezugszeit für den rechten Rand. Ohne Angabe ist das das
        neueste Sample — bei schubweise eintreffenden Daten ruckelt die
        Kurve dann. Mit einer gleichmäßig laufenden Playout-Zeit scrollt
        sie flüssig."""
        if len(timestamps) < 2:
            return
        n = min(len(timestamps), self.window_n)
        ts = timestamps[-n:]
        d  = data[-n:]

        # Timestamps reparieren: monoton linear interpolieren
        # falls Duplikate oder nicht-monotone Werte vorhanden
        if not np.all(np.diff(ts) > 0):
            ts = np.linspace(ts[0], ts[0] + n / self._fs, n)

        t = ts - (ts[-1] if t_ref is None else t_ref)

        # DC live abziehen
        if d.shape[0] > 10:
            d = d - d.mean(axis=0)

        # Smoothing (leicht, nur für Anzeige)
        d_smooth = np.array([uniform_filter1d(d[:, ch], size=3)
                             for ch in range(d.shape[1])]).T

        for i, curve in enumerate(self.curves):
            if i < d_smooth.shape[1]:
                curve.setData(t, d_smooth[:, i])
                if self._aligned and d.shape[0] > 50:
                    std = d[:, i].std()
                    # Y-Bereich nur nachziehen, wenn er sich spürbar ändert —
                    # ein setYRange pro Kanal und Frame kostet sonst jedes Mal
                    # einen kompletten Neu-Aufbau der Achse.
                    prev = self._last_std[i]
                    if std > 0 and (prev is None
                                    or abs(std - prev) > 0.1 * prev):
                        self.plots[i].setYRange(-4*std, 4*std, padding=0)
                        self._last_std[i] = std
