"""
gui/connection_dev_window.py — Hauptfenster des neu aufgebauten Builds.

Datenfluss (alles in-process, kein LSL, keine Subprozesse):

    UnicornReader (QThread) ──samples_received─┐
                                                ├─► _pending ──(Timer 25 fps)──►
    TriggerReader (QThread) ──trigger_received──┘

        RealtimeFilter  ──►  RawPlotWidget (oben, immer sichtbar)
                        ├──►  ERPProcessor   ──►  ERPPlotWidget  (Tab)
                        └──►  TFRProcessor   ──►  TFRPlotWidget  (Tab)

Wichtig: An die Prozessoren gehen ausschließlich NEUE Samples, nie der
gesamte Puffer erneut — sonst würden Epochen aus mehrfach gefütterten
Daten entstehen und der fortlaufende Filter doppelt rechnen.
"""

import os
import time
from collections import deque

import numpy as np
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QGroupBox, QTextEdit,
                              QTabWidget, QSplitter, QScrollArea, QCheckBox,
                              QFileDialog)
from PyQt6.QtCore import QTimer, Qt

from gui.bluetooth_panel import BluetoothPanel
from gui.filter_panel import FilterPanel
from gui.widgets import NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSlider
from gui.raw_plot import RawPlotWidget
from gui.erp_plot import ERPPlotWidget
from gui.tfr_plot import TFRPlotWidget
from gui.theme import SIDEBAR_WIDTH, status_color
from core.unicorn_reader import UnicornReader
from core.replay_reader import ReplayReader
from core.trigger_reader import TriggerReader
from core.erp_processor import ERPProcessor
from core.tfr_processor import TFRProcessor
from core.asr import ASRCalibrator
from core.session_recorder import SessionRecorder
from utils.filters import RealtimeFilter

EEG_LABELS = ["Fz", "C3", "Cz", "C4", "Pz", "PO7", "Oz", "PO8"]
FS = 250
PLOT_WINDOW_S = 5
# Anzeige läuft bewusst etwas hinterher, um die schubweise Ankunft der
# Bluetooth-Pakete auszugleichen (Playout-/De-Jitter-Puffer)
PLAYOUT_LAG_S = 0.25
ASR_CALIB_S = 30          # Dauer der ASR-Kalibrierung


class ConnectionDevWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ERP Viewer — Schmerzstimulation")
        self.resize(1280, 820)

        self._unicorn_reader = None
        self._trigger_reader = None

        self._pending      = []                                  # neue, noch unverarbeitete Samples
        self._display_buf  = deque(maxlen=FS * PLOT_WINDOW_S)    # gefiltert, für den Rohdaten-Plot
        self._sample_count = 0
        self._last_rate_check = None
        self._last_rate_count = 0
        self._battery = None
        self._erp_dirty = False   # Ergebnis liegt vor, Tab war aber nicht sichtbar
        self._tfr_dirty = False
        self._playout_t    = None
        self._playout_wall = None
        self._playout_rate = 1.0   # >1 bei beschleunigter Wiedergabe
        self._asr_was_calibrating = False

        self.filter    = RealtimeFilter(fs=FS)
        # store_epochs=False: die Live-Anzeige braucht nur den Mittelwert,
        # das Aufheben aller Einzelepochen würde nur Speicher fressen.
        self.processor = ERPProcessor(fs=FS, pre_ms=200, post_ms=800,
                                       store_epochs=False)
        self.tfr_proc  = TFRProcessor()
        self.asr       = ASRCalibrator(fs=FS)
        self.asr.status_callback = self._on_asr_status
        self.recorder  = SessionRecorder(ch_labels=EEG_LABELS)

        self._build_ui()
        self._start_plot_timer()

    # ── UI Aufbau ────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_plot_area(), stretch=1)

    def _build_sidebar(self):
        inner = QWidget()
        sidebar = QVBoxLayout(inner)
        sidebar.setContentsMargins(0, 0, 6, 0)
        sidebar.setSpacing(10)

        self.bt_panel = BluetoothPanel()
        self.bt_panel.auto_connect_finished.connect(self._on_bt_auto_finished)
        sidebar.addWidget(self.bt_panel)

        sidebar.addWidget(self._build_unicorn_panel())
        sidebar.addWidget(self._build_trigger_panel())

        self.filter_panel = FilterPanel(self.filter)
        sidebar.addWidget(self.filter_panel)

        sidebar.addWidget(self._build_asr_panel())
        sidebar.addWidget(self._build_recorder_panel())
        sidebar.addWidget(self._build_epoch_panel())
        sidebar.addWidget(self._build_trigger_log())
        sidebar.addStretch()

        # Scrollbar, damit bei kleinen Fenstern nichts abgeschnitten wird
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(SIDEBAR_WIDTH)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    def _build_plot_area(self):
        self.raw_plot = RawPlotWidget(ch_labels=EEG_LABELS, fs=FS,
                                       window_s=PLOT_WINDOW_S)
        self.erp_plot = ERPPlotWidget(ch_labels=EEG_LABELS)
        self.tfr_plot = TFRPlotWidget(fs=FS, ch_labels=EEG_LABELS)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.erp_plot, "ERP")
        self.tabs.addTab(self.tfr_plot, "Zeit-Frequenz")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Direkt an den Auswertungsfenstern, damit man beim Wechsel der
        # Messstelle nicht in die Seitenleiste greifen muss
        btn_reset = QPushButton("Mittelung zurücksetzen")
        btn_reset.setProperty("variant", "compact")
        btn_reset.setToolTip("Verwirft alle gesammelten Epochen von ERP "
                              "und Zeit-Frequenz und leert beide Plots.")
        btn_reset.clicked.connect(self._reset_epochs)
        self.tabs.setCornerWidget(btn_reset)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.raw_plot)
        splitter.addWidget(self.tabs)
        splitter.setSizes([340, 460])
        return splitter

    def _build_unicorn_panel(self):
        box = QGroupBox("Unicorn EEG-Stream")
        lay = QVBoxLayout(box)

        self.unicorn_status = QLabel("Nicht gestartet")
        self.unicorn_status.setWordWrap(True)
        self.unicorn_status.setProperty("role", "secondary")

        self.unicorn_stats = QLabel("Samples: 0  |  Rate: –  |  Batterie: –")
        self.unicorn_stats.setProperty("role", "caption")

        self.btn_unicorn_start = QPushButton("Streaming starten")
        self.btn_unicorn_start.clicked.connect(self._start_unicorn)
        self.btn_unicorn_stop = QPushButton("Streaming stoppen")
        self.btn_unicorn_stop.setEnabled(False)
        self.btn_unicorn_stop.clicked.connect(self._stop_unicorn)

        lay.addWidget(self.unicorn_status)
        lay.addWidget(self.btn_unicorn_start)
        lay.addWidget(self.btn_unicorn_stop)
        lay.addWidget(self.unicorn_stats)

        # Demo-Modus: eine Aufnahme wie einen Live-Stream abspielen
        replay_row = QHBoxLayout()
        self.btn_replay = QPushButton("Aufnahme abspielen …")
        self.btn_replay.setToolTip(
            "Spielt eine gespeicherte Messung wie einen Live-Stream ab — "
            "Filter, ASR, ERP und Zeit-Frequenz laufen genau wie sonst.\n"
            "Dabei wird nichts neu aufgezeichnet. „Streaming stoppen\" "
            "pausiert die Wiedergabe.")
        self.btn_replay.clicked.connect(self._choose_and_start_replay)
        self.combo_replay_speed = NoWheelComboBox()
        for label, speed in (("1×", 1.0), ("2×", 2.0), ("4×", 4.0)):
            self.combo_replay_speed.addItem(label, speed)
        self.combo_replay_speed.setToolTip("Wiedergabe-Tempo")
        replay_row.addWidget(self.btn_replay, stretch=1)
        replay_row.addWidget(self.combo_replay_speed)
        lay.addLayout(replay_row)
        return box

    def _build_trigger_panel(self):
        box = QGroupBox("Arduino Trigger")
        lay = QVBoxLayout(box)

        self.trigger_status = QLabel("Nicht gestartet")
        self.trigger_status.setWordWrap(True)
        self.trigger_status.setProperty("role", "secondary")

        self.btn_trigger_start = QPushButton("Trigger verbinden")
        self.btn_trigger_start.clicked.connect(self._start_trigger)
        self.btn_trigger_stop = QPushButton("Trigger trennen")
        self.btn_trigger_stop.setEnabled(False)
        self.btn_trigger_stop.clicked.connect(self._stop_trigger)

        lay.addWidget(self.trigger_status)
        lay.addWidget(self.btn_trigger_start)
        lay.addWidget(self.btn_trigger_stop)
        return box

    def _build_asr_panel(self):
        box = QGroupBox("Artefaktkorrektur (ASR)")
        lay = QVBoxLayout(box)

        self.asr_status = QLabel("Nicht kalibriert")
        self.asr_status.setWordWrap(True)
        self.asr_status.setProperty("role", "secondary")

        cut_row = QHBoxLayout()
        cut_caption = QLabel("Grenzwert")
        cut_caption.setProperty("role", "caption")
        self.spin_asr_cutoff = NoWheelDoubleSpinBox()
        self.spin_asr_cutoff.setRange(2.0, 30.0)
        self.spin_asr_cutoff.setSingleStep(0.5)
        self.spin_asr_cutoff.setValue(self.asr.cutoff)
        self.spin_asr_cutoff.setToolTip(
            "Standardabweichungs-Schwelle. 2,5 = aggressiv, 5 = konservativ "
            "(Standard). Höhere Werte korrigieren kaum noch.\n"
            "Wirkt erst ab der nächsten Kalibrierung.")
        self.spin_asr_cutoff.valueChanged.connect(
            lambda v: setattr(self.asr, "cutoff", float(v)))
        cut_row.addWidget(cut_caption)
        cut_row.addStretch()
        cut_row.addWidget(self.spin_asr_cutoff)

        self.btn_asr_cal = QPushButton(f"Kalibrierung starten ({ASR_CALIB_S} s)")
        self.btn_asr_cal.clicked.connect(self._start_asr_calibration)

        self.btn_asr_toggle = QPushButton("ASR aktivieren")
        self.btn_asr_toggle.setEnabled(False)
        self.btn_asr_toggle.clicked.connect(self._toggle_asr)

        lay.addWidget(self.asr_status)
        lay.addLayout(cut_row)
        lay.addWidget(self.btn_asr_cal)
        lay.addWidget(self.btn_asr_toggle)
        return box

    def _build_recorder_panel(self):
        box = QGroupBox("Aufzeichnung")
        lay = QVBoxLayout(box)

        self.cb_record = QCheckBox("Mit dem Stream aufzeichnen")
        self.cb_record.setChecked(True)
        self.cb_record.setToolTip(
            "Zeichnet Roh- und Filterstrom auf, solange der EEG-Stream läuft.\n"
            "Trigger und ASR-Zustand werden mitgeschrieben.")
        self.cb_record.toggled.connect(self._on_record_toggled)

        self.rec_status = QLabel("Bereit")
        self.rec_status.setWordWrap(True)
        self.rec_status.setProperty("role", "caption")

        lay.addWidget(self.cb_record)
        lay.addWidget(self.rec_status)
        return box

    def _build_epoch_panel(self):
        box = QGroupBox("Epochen")
        lay = QVBoxLayout(box)

        self.epoch_label = QLabel("Akzeptiert: 0   Abgelehnt: 0")
        self.epoch_label.setProperty("role", "secondary")

        thr_caption = QLabel("Artefakt-Schwelle")
        thr_caption.setProperty("role", "caption")

        thr_row = QHBoxLayout()
        self.thr_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.thr_slider.setRange(20, 300)
        self.thr_slider.setValue(int(self.processor.threshold))
        self.thr_label = QLabel(f"{int(self.processor.threshold)} µV")
        self.thr_label.setProperty("role", "secondary")
        self.thr_slider.valueChanged.connect(self._on_threshold_changed)
        thr_row.addWidget(self.thr_slider, stretch=1)
        thr_row.addWidget(self.thr_label)

        self.btn_reset = QPushButton("Epochen zurücksetzen")
        self.btn_reset.clicked.connect(self._reset_epochs)

        lay.addWidget(self.epoch_label)
        lay.addWidget(thr_caption)
        lay.addLayout(thr_row)
        lay.addWidget(self.btn_reset)
        return box

    def _build_trigger_log(self):
        box = QGroupBox("Trigger-Log")
        lay = QVBoxLayout(box)
        self.trigger_log = QTextEdit()
        self.trigger_log.setReadOnly(True)
        self.trigger_log.setFixedHeight(110)
        lay.addWidget(self.trigger_log)
        return box

    # ── Bluetooth-Panel-Rückmeldung ──────────────────────────────────
    def _on_bt_auto_finished(self, connected: bool, log: str):
        if connected:
            self.unicorn_status.setText("Bluetooth verbunden — bereit zum Streaming-Start")
        else:
            self.unicorn_status.setText("Bluetooth-Verbindung fehlgeschlagen")

    # ── Unicorn Reader ───────────────────────────────────────────────
    def _start_unicorn(self):
        if self._unicorn_reader is not None:
            if self._unicorn_reader.is_paused:
                # Sauber neu anfangen: alte Kurve + Playout-Uhr verwerfen,
                # damit der Rohdaten-Plot nicht die Pausen-Lücke überbrückt.
                self._display_buf.clear()
                self._playout_t = None
                self._playout_wall = None
                self.filter.reset_state()
                self._unicorn_reader.resume()
                self._start_recording()
                self.btn_unicorn_start.setEnabled(False)
                self.btn_unicorn_stop.setEnabled(True)
            return

        self._begin_stream(UnicornReader())

    def _begin_stream(self, reader, playout_rate: float = 1.0):
        """Gemeinsamer Start für Gerät und Wiedergabe: Puffer und Filter
        leeren, Reader anbinden und starten."""
        self._pending.clear()
        self._display_buf.clear()
        self._sample_count = 0
        self._last_rate_check = None
        self._last_rate_count = 0
        self._playout_t    = None
        self._playout_wall = None
        self._playout_rate = playout_rate
        self.filter.reset_state()

        self._unicorn_reader = reader
        reader.samples_received.connect(self._on_unicorn_samples)
        reader.status_changed.connect(self._on_unicorn_status)
        reader.error.connect(self._on_unicorn_error)
        reader.finished.connect(self._on_unicorn_thread_finished)
        reader.start()
        self._start_recording()
        self.btn_unicorn_start.setEnabled(False)
        self.btn_unicorn_stop.setEnabled(True)

    # ── Demo: Aufnahme abspielen ─────────────────────────────────────
    def _is_replaying(self) -> bool:
        return isinstance(self._unicorn_reader, ReplayReader)

    def _choose_and_start_replay(self):
        if self._unicorn_reader is not None and not self._is_replaying():
            self._on_unicorn_status(
                "Das Gerät ist verbunden — die Wiedergabe geht nur ohne "
                "laufende Geräteverbindung (Programm neu starten).")
            return

        root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        start = next((d for d in (os.path.join(root, "recordings"),
                                   os.path.join(root, "data"), root)
                      if os.path.isdir(d)), root)
        path, _ = QFileDialog.getOpenFileName(
            self, "Aufnahme zum Abspielen wählen", start, "CSV (*.csv)")
        if not path:
            return
        self._start_replay(path, self.combo_replay_speed.currentData())

    def _start_replay(self, path: str, speed: float = 1.0):
        if self._is_replaying():          # laufende/pausierte Wiedergabe ablösen
            self._shutdown_unicorn()
            self._unicorn_reader = None

        # Demo startet mit leeren Auswertungen
        self._reset_epochs()

        reader = ReplayReader(path, speed=speed)
        reader.trigger_received.connect(self._on_trigger)
        self._begin_stream(reader, playout_rate=speed)

    def _stop_unicorn(self):
        """Pausiert die Aufnahme — die Verbindung bleibt offen, damit ein
        erneuter Start ohne neuen Bluetooth-Handshake möglich ist."""
        if self._unicorn_reader is None:
            return
        self._unicorn_reader.pause()
        # Playout-Uhr anhalten — sonst läuft sie ohne neue Daten weiter und
        # der eingefrorene Rohdaten-Plot zittert im 0,25-s-Takt hin und her.
        self._playout_t = None
        self._playout_wall = None
        # Ohne Datenstrom kann eine laufende Kalibrierung nie fertig werden
        if self.asr.state == "calibrating":
            self.asr.cancel_calibration()
            self._update_asr_buttons()
        self._stop_recording()
        self.btn_unicorn_stop.setEnabled(False)
        self.btn_unicorn_start.setEnabled(True)

    def _shutdown_unicorn(self):
        """Beendet die Verbindung wirklich (nur beim Schließen des Fensters)."""
        reader = self._unicorn_reader
        if reader is None:
            return
        reader.stop()
        if not reader.wait(2000):
            reader.force_close_port()
            if not reader.wait(1000):
                reader.terminate()
                reader.wait(1000)

    def _on_unicorn_thread_finished(self):
        self._cleanup_unicorn(self.sender())

    def _cleanup_unicorn(self, reader):
        if reader is not self._unicorn_reader:
            return   # veraltetes Signal einer bereits ersetzten Instanz
        self._unicorn_reader = None
        self._playout_rate = 1.0
        self.btn_unicorn_start.setEnabled(True)
        self.btn_unicorn_stop.setEnabled(False)

    def _on_unicorn_status(self, msg: str):
        self.unicorn_status.setStyleSheet("")
        self.unicorn_status.setText(msg)

    def _on_unicorn_error(self, msg: str):
        self.unicorn_status.setStyleSheet(f"color: {status_color('error')};")
        self.unicorn_status.setText(f"Fehler: {msg}")
        if self.asr.state == "calibrating":
            self.asr.cancel_calibration()
            self._update_asr_buttons()
        self._stop_recording()

    def _on_unicorn_samples(self, ts: np.ndarray, data: np.ndarray):
        self._pending.append((ts, data))

    # ── Trigger Reader ───────────────────────────────────────────────
    def _start_trigger(self):
        if self._trigger_reader is not None:
            return
        self._trigger_reader = TriggerReader()
        self._trigger_reader.trigger_received.connect(self._on_trigger)
        self._trigger_reader.status_changed.connect(self._on_trigger_status)
        self._trigger_reader.error.connect(self._on_trigger_error)
        self._trigger_reader.finished.connect(self._on_trigger_thread_finished)
        self._trigger_reader.start()
        self.btn_trigger_start.setEnabled(False)
        self.btn_trigger_stop.setEnabled(True)

    def _stop_trigger(self):
        if self._trigger_reader is None:
            return
        self.btn_trigger_stop.setEnabled(False)
        self._on_trigger_status("Stoppe …")
        reader = self._trigger_reader
        reader.stop()
        QTimer.singleShot(2000, lambda: self._force_close_trigger_if_needed(reader))

    def _force_close_trigger_if_needed(self, reader):
        if reader is not self._trigger_reader or reader.isFinished():
            return
        self._on_trigger_status("Hängt fest — erzwinge Verbindungsabbruch …")
        reader.force_close_port()
        QTimer.singleShot(2000, lambda: self._terminate_trigger_if_needed(reader))

    def _terminate_trigger_if_needed(self, reader):
        if reader is not self._trigger_reader or reader.isFinished():
            return
        reader.terminate()
        reader.wait(1000)
        self._cleanup_trigger(reader)

    def _shutdown_trigger(self):
        reader = self._trigger_reader
        if reader is None:
            return
        reader.stop()
        if not reader.wait(2000):
            reader.force_close_port()
            if not reader.wait(1000):
                reader.terminate()
                reader.wait(1000)

    def _on_trigger_thread_finished(self):
        self._cleanup_trigger(self.sender())

    def _cleanup_trigger(self, reader):
        if reader is not self._trigger_reader:
            return
        self._trigger_reader = None
        self.btn_trigger_start.setEnabled(True)
        self.btn_trigger_stop.setEnabled(False)

    def _on_trigger_status(self, msg: str):
        self.trigger_status.setStyleSheet("")
        self.trigger_status.setText(msg)

    def _on_trigger_error(self, msg: str):
        self.trigger_status.setStyleSheet(f"color: {status_color('error')};")
        self.trigger_status.setText(f"Fehler: {msg}")

    def _on_trigger(self, ts: float, marker: str):
        # Erst alle bereits eingetroffenen Samples verarbeiten, damit der
        # Pre-Trigger-Puffer bis zum Reiz reicht (sonst fehlen bis zu einem
        # Timer-Tick = 40 ms und die Epoche liegt leicht verschoben).
        self._process_new_samples()
        self.processor.on_trigger()
        self.tfr_proc.on_trigger()
        self.raw_plot.add_trigger_marker(0)
        self.recorder.mark_trigger(ts, marker)
        t_str = time.strftime("%H:%M:%S", time.localtime(ts))
        self.trigger_log.append(f"{t_str}  {marker}")

    # ── Aufzeichnung ─────────────────────────────────────────────────
    def _start_recording(self):
        if self._is_replaying():
            self.rec_status.setStyleSheet("")
            self.rec_status.setText("Wiedergabe — keine Aufzeichnung")
            return
        if self.recorder.is_recording or not self.cb_record.isChecked():
            return
        path = self.recorder.start(meta={
            "abtastrate_hz": FS,
            "filter": {
                "highpass_hz": self.filter_panel.spin_hp.value() if self.filter.hp_active else None,
                "lowpass_hz":  self.filter_panel.spin_lp.value() if self.filter.lp_active else None,
                "notch_hz":    self.filter_panel.spin_notch.value() if self.filter.notch_active else None,
            },
            "asr_grenzwert": self.asr.cutoff,
        })
        self.rec_status.setStyleSheet(f"color: {status_color('error')};")
        self.rec_status.setText(f"● Zeichnet auf: {os.path.basename(path)}")

    def _stop_recording(self):
        if not self.recorder.is_recording:
            return
        path = self.recorder.stop()
        self.rec_status.setStyleSheet(f"color: {status_color('ok')};")
        self.rec_status.setText(
            f"✓ Gespeichert: {os.path.basename(path)}\n"
            f"{self.recorder.sample_count} Samples "
            f"({self.recorder.duration_s:.0f} s)")

    def _on_record_toggled(self, checked: bool):
        """Schalter wirkt sofort: einschalten startet bei laufendem Stream
        direkt eine Aufnahme, ausschalten beendet die laufende."""
        if checked:
            if self._unicorn_reader is not None and not self._unicorn_reader.is_paused:
                self._start_recording()
        else:
            self._stop_recording()
            if not self.recorder.is_recording:
                self.rec_status.setStyleSheet("")
                self.rec_status.setText("Aufzeichnung ausgeschaltet")

    # ── ASR-Steuerung ────────────────────────────────────────────────
    def _start_asr_calibration(self):
        # Während der Kalibrierung dient derselbe Button zum Abbrechen —
        # sonst gäbe es keinen Weg zurück, wenn der Stream unterwegs endet.
        if self.asr.state == "calibrating":
            self.asr.cancel_calibration()
            self.recorder.mark_event("asr_kalibrierung_abgebrochen")
            self._update_asr_buttons()
            return

        if self._unicorn_reader is None or self._unicorn_reader.is_paused:
            self.asr_status.setStyleSheet(f"color: {status_color('error')};")
            self.asr_status.setText("Erst den EEG-Stream starten")
            return

        self.asr_status.setStyleSheet("")
        self.recorder.mark_event("asr_kalibrierung_start",
                                  {"grenzwert": self.asr.cutoff,
                                   "dauer_s": ASR_CALIB_S})
        self.asr.start_calibration(duration_s=ASR_CALIB_S)
        self._update_asr_buttons()

    def _update_asr_buttons(self):
        calibrating = self.asr.state == "calibrating"
        self.btn_asr_cal.setText(
            "Kalibrierung abbrechen" if calibrating
            else f"Kalibrierung starten ({ASR_CALIB_S} s)")
        self.btn_asr_cal.setEnabled(True)
        self.btn_asr_toggle.setEnabled(
            not calibrating and self.asr.state in ("ready", "running"))

    def _toggle_asr(self):
        if self.asr.state == "running":
            self.asr.stop_processing()
            self.recorder.mark_event("asr_aus")
            self.btn_asr_toggle.setText("ASR aktivieren")
        elif self.asr.state == "ready":
            self.asr.start_processing()
            self.recorder.mark_event("asr_ein", {"grenzwert": self.asr.cutoff})
            self.btn_asr_toggle.setText("ASR deaktivieren")

    def _on_asr_status(self, msg: str):
        self.asr_status.setText(msg)
        if self.asr.state == "ready" and self._asr_was_calibrating:
            self.recorder.mark_event("asr_kalibrierung_fertig", msg)
        self._asr_was_calibrating = (self.asr.state == "calibrating")
        self._update_asr_buttons()

    # ── Epochen-Steuerung ────────────────────────────────────────────
    def _on_threshold_changed(self, value: int):
        self.processor.threshold = float(value)
        self.thr_label.setText(f"{value} µV")

    def _reset_epochs(self):
        self.processor.reset()
        self.tfr_proc.reset()
        self.tfr_plot.reset()
        # Die ERP-Kurve würde sonst bis zur nächsten Epoche stehen bleiben
        self.erp_plot.update_erp(self.processor.time_axis,
                                  self.processor.erp_mean, 0)
        self._erp_dirty = self._tfr_dirty = False
        self._update_epoch_label()
        self.recorder.mark_event("mittelung_zurueckgesetzt")

    def _update_epoch_label(self):
        self.epoch_label.setText(
            f"Akzeptiert: {self.processor.n_accepted}   "
            f"Abgelehnt: {self.processor.n_rejected}"
        )

    # ── Verarbeitung + Plot-Timer ────────────────────────────────────
    def _start_plot_timer(self):
        self.timer = QTimer()
        self.timer.setInterval(40)   # ~25 fps
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _tick(self):
        self._process_new_samples()
        self._update_raw_plot()
        self._update_stats()

    def _process_new_samples(self):
        if not self._pending:
            return

        batches, self._pending = self._pending, []
        ts_new  = np.concatenate([b[0] for b in batches])
        raw_new = np.concatenate([b[1] for b in batches])
        self._sample_count += len(ts_new)
        self._battery = raw_new[-1, 14]

        # Fortlaufender Filter — nur die neuen Samples
        eeg_new = self.filter.process(raw_new[:, :8])

        # ASR: erst kalibrieren, dann optional korrigieren
        if self.asr.state == "calibrating":
            self.asr.feed_calibration(eeg_new)
        elif self.asr.state == "running":
            eeg_new = self.asr.process(eeg_new)

        # Aufzeichnung: Roh- und Verarbeitungsstrom plus ASR-Zustand
        self.recorder.add_block(ts_new, raw_new[:, :8], eeg_new,
                                 raw_new[:, 15], self.asr.state)

        for t, sample in zip(ts_new, eeg_new):
            self._display_buf.append((t, sample))

        # Prozessoren bekommen ausschließlich neue Samples
        erp_new, erp_accepted = self.processor.feed(eeg_new)
        self.tfr_proc.feed(eeg_new)

        if erp_new:
            if not erp_accepted:
                self.tfr_proc.reject_current()
            else:
                self._erp_dirty = True
                self._refresh_erp_if_visible()
            self._update_epoch_label()

        if self.tfr_proc.new_result and self.tfr_proc.P_total is not None:
            self.tfr_proc.new_result = False
            self._tfr_dirty = True
            self._refresh_tfr_if_visible()

    # ── Plot-Aktualisierung nur für den sichtbaren Tab ───────────────
    def _refresh_erp_if_visible(self):
        if not self._erp_dirty or self.tabs.currentWidget() is not self.erp_plot:
            return
        self._erp_dirty = False
        self.erp_plot.update_erp(self.processor.time_axis,
                                  self.processor.erp_mean,
                                  self.processor.n_accepted)

    def _refresh_tfr_if_visible(self):
        if not self._tfr_dirty or self.tabs.currentWidget() is not self.tfr_plot:
            return
        self._tfr_dirty = False
        self.tfr_plot.update_tfr(self.tfr_proc.P_low, self.tfr_proc.P_high,
                                  self.tfr_proc.f_low, self.tfr_proc.f_high,
                                  self.tfr_proc.t_all, self.tfr_proc.n_epochs)

    def _on_tab_changed(self, _index):
        """Beim Wechsel nachholen, was im Hintergrund übersprungen wurde."""
        self._refresh_erp_if_visible()
        self._refresh_tfr_if_visible()

    def _advance_playout(self):
        """Playout-Uhr: läuft gleichmäßig mit der Wanduhr, bewusst um
        PLAYOUT_LAG_S hinter den zuletzt eingetroffenen Daten. Dadurch
        scrollt die Kurve flüssig, obwohl Bluetooth die Samples schubweise
        liefert. Läuft die Uhr aus dem Ruder (Aussetzer, Pause), wird sie
        auf den Sollabstand nachgezogen."""
        newest = self._display_buf[-1][0]
        target = newest - PLAYOUT_LAG_S
        now = time.time()

        if self._playout_t is None:
            self._playout_t = target
        else:
            self._playout_t += (now - self._playout_wall) * self._playout_rate
            if self._playout_t > newest or abs(self._playout_t - target) > 0.5:
                self._playout_t = target

        self._playout_wall = now
        return self._playout_t

    def _is_streaming(self) -> bool:
        return (self._unicorn_reader is not None
                and not self._unicorn_reader.is_paused)

    def _update_raw_plot(self):
        # Kein aktiver Stream → Plot einfrieren (letztes Bild stehen lassen).
        # Sonst läuft die Playout-Uhr weiter und die Kurve zuckt.
        if not self._is_streaming() or not self._display_buf:
            return
        t_ref = self._advance_playout()

        buf = list(self._display_buf)
        ts   = np.array([b[0] for b in buf])
        data = np.array([b[1] for b in buf])

        # Nur, was die Playout-Uhr schon erreicht hat
        visible = ts <= t_ref
        if visible.sum() < 2:
            return
        self.raw_plot.update_data(ts[visible], data[visible], t_ref=t_ref)

    def _update_stats(self):
        if self._battery is None:
            return
        rate_txt = "–"
        now = time.time()
        if self._last_rate_check is not None:
            dt = now - self._last_rate_check
            dn = self._sample_count - self._last_rate_count
            if dt > 0.5:
                rate_txt = f"{dn / dt:.0f} Hz"
                self._last_rate_check = now
                self._last_rate_count = self._sample_count
                self._last_rate_txt = rate_txt
            else:
                rate_txt = getattr(self, "_last_rate_txt", "–")
        else:
            self._last_rate_check = now
            self._last_rate_count = self._sample_count

        txt = (f"Samples: {self._sample_count}  |  Rate: {rate_txt}  |  "
               f"Batterie: {self._battery:.0f}%")
        reader = self._unicorn_reader
        if reader is not None and reader.dropped_samples:
            txt += f"\nAusfälle: {reader.dropped_samples} Samples"
        self.unicorn_stats.setText(txt)

    def closeEvent(self, event):
        self._shutdown_unicorn()
        self._shutdown_trigger()
        self._stop_recording()   # Datei sauber abschließen
        self.timer.stop()
        event.accept()
