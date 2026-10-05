from PyQt6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                              QCheckBox, QLabel, QPushButton)
from PyQt6.QtCore import pyqtSignal

from gui.widgets import NoWheelDoubleSpinBox

class FilterPanel(QGroupBox):
    filters_changed = pyqtSignal()

    def __init__(self, rt_filter, parent=None):
        super().__init__("Filter", parent)
        self.filt = rt_filter
        self._build_ui()
        # Defaults setzen
        self.filt.set_highpass(1.0)
        self.filt.set_lowpass(40.0)
        self.filt.set_notch(50.0)
        # Hochpass standardmäßig AUS — bei unseren Messungen eher störend
        # (langsame Grundlinien-Drift ist für die ERP-Baseline-Korrektur
        # kein Problem, der Filter frisst aber echte langsame Anteile weg).
        self.filt.toggle_hp(False)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Highpass ─────────────────────────────────────────────
        hp_row = QHBoxLayout()
        self.cb_hp  = QCheckBox("Highpass")
        self.cb_hp.setChecked(False)
        self.spin_hp = NoWheelDoubleSpinBox()
        self.spin_hp.setRange(0.1, 10.0)
        self.spin_hp.setValue(1.0)
        self.spin_hp.setSuffix(" Hz")
        self.spin_hp.setSingleStep(0.5)
        self.cb_hp.toggled.connect(lambda v: self._toggle("hp", v))
        self.spin_hp.valueChanged.connect(lambda v: self.filt.set_highpass(v))
        hp_row.addWidget(self.cb_hp)
        hp_row.addStretch()
        hp_row.addWidget(self.spin_hp)
        layout.addLayout(hp_row)

        # ── Lowpass ───────────────────────────────────────────────
        lp_row = QHBoxLayout()
        self.cb_lp  = QCheckBox("Lowpass")
        self.cb_lp.setChecked(True)
        self.spin_lp = NoWheelDoubleSpinBox()
        self.spin_lp.setRange(5.0, 100.0)
        self.spin_lp.setValue(40.0)
        self.spin_lp.setSuffix(" Hz")
        self.spin_lp.setSingleStep(5.0)
        self.cb_lp.toggled.connect(lambda v: self._toggle("lp", v))
        self.spin_lp.valueChanged.connect(lambda v: self.filt.set_lowpass(v))
        lp_row.addWidget(self.cb_lp)
        lp_row.addStretch()
        lp_row.addWidget(self.spin_lp)
        layout.addLayout(lp_row)

        # ── Notch ─────────────────────────────────────────────────
        notch_row = QHBoxLayout()
        self.cb_notch  = QCheckBox("Notch")
        self.cb_notch.setChecked(True)
        self.spin_notch = NoWheelDoubleSpinBox()
        self.spin_notch.setRange(49.0, 60.0)
        self.spin_notch.setValue(50.0)
        self.spin_notch.setSuffix(" Hz")
        self.cb_notch.toggled.connect(lambda v: self._toggle("notch", v))
        self.spin_notch.valueChanged.connect(lambda v: self.filt.set_notch(v))
        notch_row.addWidget(self.cb_notch)
        notch_row.addStretch()
        notch_row.addWidget(self.spin_notch)
        layout.addLayout(notch_row)

    def _toggle(self, which, state):
        {"hp": self.filt.toggle_hp,
         "lp": self.filt.toggle_lp,
         "notch": self.filt.toggle_notch}[which](state)
        self.filters_changed.emit()
