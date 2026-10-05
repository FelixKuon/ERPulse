from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout,
                              QVBoxLayout, QSplitter, QPushButton,
                              QLabel, QGroupBox, QMessageBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
import numpy as np

from core.lsl_receiver   import LSLReceiver
from core.erp_processor  import ERPProcessor
from core.tfr_processor  import TFRProcessor
from core.asr            import ASRCalibrator
from core.data_recorder  import DataRecorder
from utils.filters       import RealtimeFilter
from gui.bluetooth_panel  import BluetoothPanel
from gui.connection_panel import ConnectionPanel
from gui.filter_panel     import FilterPanel
from gui.raw_plot         import RawPlotWidget
from gui.erp_plot         import ERPPlotWidget
from gui.tfr_plot import TFRPlotWidget
from gui.device_launcher import DeviceLauncher
from gui.widgets import NoWheelSlider

EEG_LABELS = ["Fz","C3","Cz","C4","Pz","PO7","Oz","PO8"]

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ERP Viewer — Unicorn EEG")
        self.resize(1400, 900)

        # ── Kern-Objekte ─────────────────────────────────────────
        self.filter    = RealtimeFilter(fs=250)
        self.receiver  = LSLReceiver()
        self.receiver.trigger_received.connect(self._on_trigger)
        self.processor = ERPProcessor(fs=250, pre_ms=200, post_ms=800)
        self.tfr_proc  = TFRProcessor()
        self.asr       = ASRCalibrator(fs=250)
        self.asr.status_callback = self._asr_status
        self.recorder  = DataRecorder()

        self._build_ui()
        self._start_timer()

    # ── UI Aufbau ────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # ── Linke Sidebar ─────────────────────────────────────────
        sidebar = QVBoxLayout()
        sidebar.setSpacing(10)

        self.bt_panel   = BluetoothPanel()
        self.conn_panel = ConnectionPanel(self.receiver, self.asr)
        self.launcher   = DeviceLauncher()
        self.launcher.demo_ready.connect(self._auto_connect)
        self.launcher.unicorn_ready.connect(self.conn_panel.set_unicorn_ready)
        # Workflow-Reihenfolge: erst Bluetooth, dann Prozess starten, dann LSL verbinden
        sidebar.addWidget(self.bt_panel)
        sidebar.addWidget(self.launcher)
        sidebar.addWidget(self.conn_panel)
        self.filter_panel = FilterPanel(self.filter)
        # Defaults kommen aus FilterPanel: Lowpass 40 Hz an, Notch 50 Hz an,
        # Hochpass AUS (bei unseren Messungen eher störend).
        sidebar.addWidget(self.filter_panel)
        sidebar.addWidget(self._build_asr_panel())
        sidebar.addWidget(self._build_epoch_panel())
        sidebar.addWidget(self._build_recorder_panel())
        sidebar.addStretch()

        sidebar_widget = QWidget()
        sidebar_widget.setLayout(sidebar)
        sidebar_widget.setFixedWidth(280)

        # ── Plots (rechts) ────────────────────────────────────────
        self.raw_plot = RawPlotWidget(ch_labels=EEG_LABELS)
        self.erp_plot = ERPPlotWidget(ch_labels=EEG_LABELS)
        self.tfr_plot = TFRPlotWidget(fs=250, ch_labels=EEG_LABELS)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.raw_plot)
        splitter.addWidget(self.erp_plot)
        splitter.addWidget(self.tfr_plot)
        splitter.setSizes([250, 250, 400])


        root.addWidget(sidebar_widget)
        root.addWidget(splitter, stretch=1)

        # Verbindungs-Signal
        self.conn_panel.connected.connect(self._on_connected)

    def _build_asr_panel(self):
        box = QGroupBox("Artifact Subspace Reconstruction")
        lay = QVBoxLayout(box)

        self.asr_status = QLabel("Status: Nicht kalibriert")
        self.asr_status.setWordWrap(True)

        self.btn_asr_cal = QPushButton("Kalibrierung starten (20s)")
        self.btn_asr_cal.setEnabled(False)
        self.btn_asr_cal.clicked.connect(self._start_asr_calibration)

        self.btn_asr_toggle = QPushButton("ASR aktivieren")
        self.btn_asr_toggle.setEnabled(False)
        self.btn_asr_toggle.clicked.connect(self._toggle_asr)

        lay.addWidget(self.asr_status)
        lay.addWidget(self.btn_asr_cal)
        lay.addWidget(self.btn_asr_toggle)
        return box

    def _build_epoch_panel(self):
        box = QGroupBox("Epochen")
        lay = QVBoxLayout(box)

        self.epoch_label = QLabel("Akzeptiert: 0  |  Abgelehnt: 0")

        thr_row = QHBoxLayout()
        thr_row.addWidget(QLabel("Artefakt-Threshold:"))
        self.thr_label = QLabel("100 µV")
        self.thr_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.thr_slider.setRange(20, 300)
        self.thr_slider.setValue(100)
        self.thr_slider.valueChanged.connect(
            lambda v: (setattr(self.processor, 'threshold', float(v)),
                       self.thr_label.setText(f"{v} µV")))
        thr_row.addWidget(self.thr_slider)
        thr_row.addWidget(self.thr_label)

        self.btn_reset = QPushButton("ERP zurücksetzen")
        self.btn_reset.clicked.connect(self._reset_erp)

        lay.addWidget(self.epoch_label)
        lay.addLayout(thr_row)
        lay.addWidget(self.btn_reset)
        return box

    # ── Timer (Echtzeit-Update) ──────────────────────────────────
    def _start_timer(self):
        self.timer = QTimer()
        self.timer.setInterval(40)     # ~25 fps
        self.timer.timeout.connect(self._update_plots)
        self.timer.start()

    def _update_plots(self):
        ts, data = self.receiver.get_eeg_array()
        if data.size == 0:
            return

        # Filter anwenden
        eeg8 = self.filter.process(data[:, :8])

        # Rohdaten aufzeichnen
        if self.recorder.is_recording:
            for sample in eeg8:
                self.recorder.add_sample(sample)

        # ASR anwenden (Kalibrierung + Live)
        if self.asr.state == "calibrating":
            self.asr.feed_calibration(eeg8)
        elif self.asr.state == "running":
            eeg8 = self.asr.process(eeg8)

        self.raw_plot.update_data(ts, eeg8)

        # ERP und TFR mit Samples füttern
        erp_new, erp_accepted = self.processor.feed(eeg8)
        self.tfr_proc.feed(eeg8)

        # TFR-Epoche verwerfen wenn ERP abgelehnt hat
        if erp_new and not erp_accepted:
            self.tfr_proc.reject_current()

        # ERP Plot aktualisieren wenn neue Epoche akzeptiert
        if erp_new and erp_accepted:
            self.erp_plot.update_erp(
                self.processor.time_axis,
                self.processor.erp_mean,
                self.processor.n_accepted
            )
            self.epoch_label.setText(
                f"Akzeptiert: {self.processor.n_accepted}  |  "
                f"Abgelehnt:  {self.processor.n_rejected}"
            )

        # TFR Plot aktualisieren wenn neue Epoche (async via Worker-Signal)
        if self.tfr_proc.new_result and self.tfr_proc.P_total is not None:
            self.tfr_proc.new_result = False  # Flag zurücksetzen
            self.tfr_plot.update_tfr(
                self.tfr_proc.P_low,
                self.tfr_proc.P_high,
                self.tfr_proc.f_low,
                self.tfr_proc.f_high,
                self.tfr_proc.t_all,
                self.tfr_proc.n_epochs
            )

    # ── Callbacks ────────────────────────────────────────────────
    def _on_connected(self, ok: bool):
        if ok:
            self.receiver.start()
            self.btn_asr_cal.setEnabled(True)

    def _auto_connect(self):
        """Wird nach Demo-Start automatisch aufgerufen"""
        self.conn_panel._on_connect()

    def _on_trigger(self, ts: float, marker: str):
        # Trigger an Prozessoren weitergeben — kein Buffer-Index mehr!
        self.processor.on_trigger()
        self.tfr_proc.on_trigger()
        # Trigger-Marker im Raw-Plot (t_rel=0 = jetzt)
        self.raw_plot.add_trigger_marker(0)
        # Trigger aufzeichnen
        self.recorder.add_trigger(int(marker.split(":")[-1].split(",")[0])
                                  if ":" in marker else 1)
        print(f"[Trigger] {marker} — ERP sammelt, TFR sammelt")

    def _start_asr_calibration(self):
        self.asr.start_calibration(duration_s=20)
        self.btn_asr_cal.setEnabled(False)

    def _toggle_asr(self):
        if self.asr.state == "running":
            self.asr.stop_processing()
            self.btn_asr_toggle.setText("ASR aktivieren")
        elif self.asr.state == "ready":
            import threading
            threading.Thread(
                target=self.asr.start_processing, daemon=True
            ).start()
            self.btn_asr_toggle.setText("ASR deaktivieren")

    def _asr_status(self, msg: str):
        self.asr_status.setText(f"Status: {msg}")
        if self.asr.state == "ready":
            self.btn_asr_toggle.setEnabled(True)
            self.btn_asr_cal.setEnabled(True)

    def _reset_erp(self):
        self.processor.reset()
        self.tfr_proc.reset()

    def _build_recorder_panel(self):
        box = QGroupBox("Aufnahme")
        lay = QVBoxLayout(box)

        self.rec_label = QLabel("● Nicht aufzeichnend")
        self.rec_label.setStyleSheet("color: gray;")

        self.btn_rec_start = QPushButton("⏺  Aufnahme starten")
        self.btn_rec_start.setStyleSheet("background: #3a5a2a;")
        self.btn_rec_start.clicked.connect(self._start_recording)

        self.btn_rec_stop = QPushButton("⏹  Aufnahme stoppen")
        self.btn_rec_stop.setStyleSheet("background: #5a2a2a;")
        self.btn_rec_stop.setEnabled(False)
        self.btn_rec_stop.clicked.connect(self._stop_recording)

        self.rec_timer_label = QLabel("00:00")
        self.rec_timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rec_timer_label.setFont(QFont("Menlo", 14))

        # Timer für Aufnahme-Dauer
        self._rec_update_timer = QTimer()
        self._rec_update_timer.setInterval(1000)
        self._rec_update_timer.timeout.connect(self._update_rec_label)

        lay.addWidget(self.rec_label)
        lay.addWidget(self.btn_rec_start)
        lay.addWidget(self.btn_rec_stop)
        lay.addWidget(self.rec_timer_label)
        return box

    def _start_recording(self):
        self.recorder.start()
        self.btn_rec_start.setEnabled(False)
        self.btn_rec_stop.setEnabled(True)
        self.rec_label.setText("● REC")
        self.rec_label.setStyleSheet("color: red; font-weight: bold;")
        self._rec_update_timer.start()

    def _stop_recording(self):
        path = self.recorder.stop()
        self.btn_rec_start.setEnabled(True)
        self.btn_rec_stop.setEnabled(False)
        self.rec_label.setText(f"✓ Gespeichert")
        self.rec_label.setStyleSheet("color: #88ff88;")
        self._rec_update_timer.stop()
        if path:
            QMessageBox.information(self, "Aufnahme gespeichert",
                f"Datei gespeichert:\n{path}\n\n"
                f"Dauer: {self.recorder.duration_s:.1f}s")

    def _update_rec_label(self):
        s = int(self.recorder.duration_s)
        self.rec_timer_label.setText(f"{s//60:02d}:{s%60:02d}")
    
    def closeEvent(self, event):
        self.launcher.stop_all()
        self.receiver.stop()
        self.timer.stop()
        event.accept()

