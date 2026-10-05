import sys, os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QGroupBox, QComboBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor
import glob

class ConnectWorker(QThread):
    result = pyqtSignal(bool, str)

    def __init__(self, receiver):
        super().__init__()
        self.receiver = receiver

    def run(self):
        ok, msg = self.receiver.connect(timeout=10)
        self.result.emit(ok, msg)


class StatusLight(QLabel):
    """Kleines farbiges Lämpchen"""
    def __init__(self):
        super().__init__("●")
        self.setFixedWidth(20)
        self.set_state("off")

    def set_state(self, state: str):
        colors = {"off": "gray", "searching": "orange", "ok": "lime", "error": "red"}
        self.setStyleSheet(f"color: {colors.get(state, 'gray')}; font-size: 18px;")


class ConnectionPanel(QGroupBox):
    connected = pyqtSignal(bool)   # an MainWindow weitergeben

    def __init__(self, receiver, asr_calibrator, parent=None):
        super().__init__("Geräte-Verbindung", parent)
        self.receiver   = receiver
        self.asr        = asr_calibrator
        self._worker    = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Unicorn Row ───────────────────────────────────────────
        unicorn_row = QHBoxLayout()
        self.light_unicorn = StatusLight()
        self.label_unicorn = QLabel("Unicorn EEG")
        self.btn_connect   = QPushButton("Verbinden")
        self.btn_connect.setEnabled(False)
        self.btn_connect.clicked.connect(self._on_connect)
        unicorn_row.addWidget(self.light_unicorn)
        unicorn_row.addWidget(self.label_unicorn)
        unicorn_row.addStretch()
        unicorn_row.addWidget(self.btn_connect)
        layout.addLayout(unicorn_row)

        # ── Arduino/Trigger Row ───────────────────────────────────
        trig_row = QHBoxLayout()
        self.light_trig  = StatusLight()
        self.label_trig  = QLabel("Trigger (Arduino)")

        # Ports auto-detect
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(160)
        self._refresh_ports()

        self.btn_refresh = QPushButton("↻")
        self.btn_refresh.setFixedWidth(30)
        self.btn_refresh.clicked.connect(self._refresh_ports)

        trig_row.addWidget(self.light_trig)
        trig_row.addWidget(self.label_trig)
        trig_row.addStretch()
        trig_row.addWidget(self.port_combo)
        trig_row.addWidget(self.btn_refresh)
        layout.addLayout(trig_row)

        # ── Status Text ───────────────────────────────────────────
        self.status_label = QLabel("Warte auf Unicorn-Prozess ...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.status_label)

    def set_unicorn_ready(self, ready: bool):
        """Wird von DeviceLauncher.unicorn_ready aufgerufen — gibt den
        'Verbinden'-Button erst frei, wenn der Unicorn-Prozess läuft."""
        self.btn_connect.setEnabled(ready)
        if ready:
            self.status_label.setText("Unicorn-Prozess bereit — kann verbunden werden")
            self.status_label.setStyleSheet("color: gray; font-style: italic;")
        else:
            self.light_unicorn.set_state("off")
            self.status_label.setText("Warte auf Unicorn-Prozess ...")
            self.status_label.setStyleSheet("color: gray; font-style: italic;")

    def _refresh_ports(self):
        self.port_combo.clear()
        ports = glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyUSB*")
        self.port_combo.addItems(ports if ports else ["Kein Port gefunden"])

    def _on_connect(self):
        self.btn_connect.setEnabled(False)
        self.btn_connect.setText("Suche...")
        self.light_unicorn.set_state("searching")
        self.light_trig.set_state("searching")
        self.status_label.setText("Suche LSL Streams...")

        self._worker = ConnectWorker(self.receiver)
        self._worker.result.connect(self._on_result)
        self._worker.start()

    def _on_result(self, ok: bool, msg: str):
        if ok:
            self.light_unicorn.set_state("ok")
            self.light_trig.set_state("ok")
            self.status_label.setText(f"✓ {msg}")
            self.status_label.setStyleSheet("color: lime;")
            self.btn_connect.setText("Verbunden")
        else:
            self.light_unicorn.set_state("error")
            self.light_trig.set_state("error")
            self.status_label.setText(f"✗ {msg}")
            self.status_label.setStyleSheet("color: red;")
            self.btn_connect.setText("Erneut versuchen")
            self.btn_connect.setEnabled(True)
        self.connected.emit(ok)

