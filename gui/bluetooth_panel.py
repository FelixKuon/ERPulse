"""
BluetoothPanel — Steuerung der macOS-Bluetooth-Verbindung zum Unicorn
Hybrid Black via `blueutil` (Homebrew: brew install blueutil).

Hintergrund: Nach einem Aus-/Einschalten des Geräts hängt die
Bluetooth-Classic-Verbindung auf macOS gelegentlich fest. Die einzige
robuste Lösung ist die Sequenz Disconnect → Unpair → Pair → (warten) →
Connect — das übernimmt der Button "Unicorn verbinden (automatisch)"
(core/bluetooth_ctl.py: AutoConnectWorker). Kein automatisches
Zeit-Retry: bei Fehlschlag bricht die Sequenz klar ab, ein erneuter Klick
startet sie einfach neu. Die 5 Einzel-Buttons bleiben für manuelle
Diagnose erhalten.

Manuelle Testanleitung (falls die automatische Sequenz fehlschlägt):
  1. Unicorn-Gerät ausschalten, kurz warten, wieder einschalten.
  2. In diesem Panel nacheinander klicken: Disconnect, Unpair, Pair, Connect.
     (Jeder Klick wartet auf das Ergebnis des vorherigen Befehls, bevor die
     Buttons wieder aktiv werden. Pairing braucht ein paar Sekunden.)
  3. "Status" klicken und in der Ausgabe "connected" verifizieren.
"""

import sys

from PyQt6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
                              QPushButton, QLabel, QLineEdit)
from PyQt6.QtCore import pyqtSignal

from config import UNICORN_BLUETOOTH_MAC
from core.bluetooth_ctl import BlueutilWorker, AutoConnectWorker, MAC_RE
from core.ports import find_unicorn_port
from gui.theme import status_color


class BluetoothPanel(QGroupBox):
    """Bluetooth-Ebene: automatische Reset-Sequenz + manuelle Einzel-Buttons."""

    auto_connect_finished = pyqtSignal(bool, str)   # (wirklich verbunden, Log)

    def __init__(self, parent=None):
        super().__init__("Bluetooth (Unicorn)", parent)
        self._worker = None
        self._auto_worker = None
        self._build_ui()

    def _build_ui(self):
        if sys.platform != "darwin":
            self._build_manual_ui()   # blueutil gibt es nur auf macOS
            return
        layout = QVBoxLayout(self)

        mac_row = QHBoxLayout()
        mac_row.addWidget(QLabel("MAC:"))
        self.mac_edit = QLineEdit(UNICORN_BLUETOOTH_MAC)
        self.mac_edit.setPlaceholderText("xx-xx-xx-xx-xx-xx")
        mac_row.addWidget(self.mac_edit)
        layout.addLayout(mac_row)

        self.btn_auto = QPushButton("Unicorn verbinden")
        self.btn_auto.setProperty("variant", "primary")
        self.btn_auto.clicked.connect(self._run_auto)
        layout.addWidget(self.btn_auto)

        manual_caption = QLabel("Manuelle Steuerung")
        manual_caption.setProperty("role", "caption")
        layout.addWidget(manual_caption)

        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_unpair     = QPushButton("Unpair")
        self.btn_pair       = QPushButton("Pair")
        self.btn_connect    = QPushButton("Connect")
        self.btn_status     = QPushButton("Status")

        self.buttons = [self.btn_disconnect, self.btn_unpair,
                         self.btn_pair, self.btn_connect, self.btn_status]

        self.btn_disconnect.clicked.connect(lambda: self._run("--disconnect"))
        self.btn_unpair.clicked.connect(lambda: self._run("--unpair"))
        self.btn_pair.clicked.connect(lambda: self._run("--pair"))
        self.btn_connect.clicked.connect(lambda: self._run("--connect"))
        self.btn_status.clicked.connect(lambda: self._run("--info"))

        # Zwei Spalten statt einer engen Reihe — die Beschriftungen bleiben lesbar
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, b in enumerate(self.buttons):
            b.setProperty("variant", "compact")
            grid.addWidget(b, i // 2, i % 2)
        layout.addLayout(grid)

        self.status_label = QLabel("Bereit")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {status_color('off')};")
        layout.addWidget(self.status_label)

    # ── Windows / Linux: Kopplung übernimmt das Betriebssystem ───────
    def _build_manual_ui(self):
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Unicorn einschalten und einmalig im Betriebssystem koppeln "
            "(Windows: Einstellungen › Bluetooth › Gerät hinzufügen › "
            "„UN-…“, PIN 1234 falls gefragt). Es entsteht ein COM-Port. "
            "Danach hier den Port prüfen und „Streaming starten“ drücken.")
        hint.setWordWrap(True)
        hint.setProperty("role", "caption")
        layout.addWidget(hint)

        self.btn_find = QPushButton("Unicorn-Port suchen")
        self.btn_find.setProperty("variant", "primary")
        self.btn_find.clicked.connect(self._find_port)
        layout.addWidget(self.btn_find)

        self.status_label = QLabel("Bereit")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {status_color('off')};")
        layout.addWidget(self.status_label)

    def _find_port(self):
        try:
            port = find_unicorn_port()
        except RuntimeError as e:
            self._set_status("error", str(e))
            self.auto_connect_finished.emit(False, str(e))
            return
        self._set_status("ok", f"Unicorn gefunden: {port}")
        self.auto_connect_finished.emit(True, port)

    # ── Automatische Sequenz ─────────────────────────────────────────
    def _run_auto(self):
        mac = self.mac_edit.text().strip()
        if not MAC_RE.match(mac):
            self._set_status("error", f"Ungültiges MAC-Format: '{mac}'")
            return

        self._set_all_enabled(False)
        self._set_status("running", "Starte automatische Verbindungssequenz …")

        self._auto_worker = AutoConnectWorker(mac)
        self._auto_worker.step_changed.connect(lambda msg: self._set_status("running", msg))
        self._auto_worker.finished_ok.connect(self._on_auto_finished)
        self._auto_worker.start()

    def _on_auto_finished(self, connected: bool, log: str):
        self._set_status("ok" if connected else "error",
                          "Verbunden" if connected else "Verbindung fehlgeschlagen")
        self._set_all_enabled(True)
        self.auto_connect_finished.emit(connected, log)

    # ── Manuelle Einzel-Buttons ──────────────────────────────────────
    def _run(self, blueutil_flag: str):
        mac = self.mac_edit.text().strip()
        if not MAC_RE.match(mac):
            self._set_status("error", f"Ungültiges MAC-Format: '{mac}'")
            return

        self._set_all_enabled(False)
        self._set_status("running", f"{blueutil_flag} {mac} läuft ...")

        self._worker = BlueutilWorker([blueutil_flag, mac])
        self._worker.result.connect(self._on_result)
        self._worker.start()

    def _on_result(self, ok: bool, output: str):
        self._set_status("ok" if ok else "error", output)
        self._set_all_enabled(True)

    def _set_all_enabled(self, enabled: bool):
        self.btn_auto.setEnabled(enabled)
        for b in self.buttons:
            b.setEnabled(enabled)

    def _set_status(self, state: str, msg: str):
        self.status_label.setStyleSheet(f"color: {status_color(state)};")
        self.status_label.setText(msg)
