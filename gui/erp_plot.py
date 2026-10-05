import pyqtgraph as pg
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from gui.theme import CHANNEL_COLORS as COLORS

class ERPPlotWidget(QWidget):
    def __init__(self, ch_labels):
        super().__init__()
        self.labels = ch_labels
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pw    = pg.GraphicsLayoutWidget(title="Evoziertes Potential (ERP)")
        layout.addWidget(self.pw)
        self.plot  = self.pw.addPlot()
        self.plot.setLabel('bottom', 'Zeit', units='ms')
        self.plot.setLabel('left', 'Amplitude', units='µV')
        self.plot.addLegend()
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        # Keine Maus-Interaktion: die Achsen skalieren automatisch mit; Zoom/Pan
        # per Maus würde die Ansicht nur ungewollt verstellen. Zum genauen
        # Vermessen gibt es die Offline-Auswertung.
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.setMenuEnabled(False)
        self.plot.enableAutoRange(x=True, y=True)

        # Stimulus-Linie bei t=0
        self.plot.addItem(pg.InfiniteLine(pos=0, angle=90,
                          pen=pg.mkPen('w', width=1, style=pg.QtCore.Qt.PenStyle.DashLine)))

        self.curves = []
        for i, label in enumerate(self.labels):
            c = self.plot.plot(name=label, pen=pg.mkPen(color=COLORS[i], width=2))
            self.curves.append(c)

        self.title_label = self.pw.addLabel("n=0", row=1, col=0)

    def update_erp(self, time_axis, erp_mean, n):
        for i, curve in enumerate(self.curves):
            if i < erp_mean.shape[1]:
                curve.setData(time_axis, erp_mean[:, i])
        self.title_label.setText(f"n = {n} Epochen")
