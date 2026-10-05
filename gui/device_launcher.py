import subprocess
import sys
import os
import signal
from PyQt6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QTextEdit, QFileDialog)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

class ProcessWatcher(QThread):
    output   = pyqtSignal(str, str)
    finished = pyqtSignal(str)

    def __init__(self, name, process):
        super().__init__()
        self.name    = name
        self.process = process

    def run(self):
        for line in iter(self.process.stdout.readline, b''):
            self.output.emit(self.name, line.decode(errors="ignore").rstrip())
        self.process.wait()
        self.finished.emit(self.name)


class DeviceLauncher(QGroupBox):
    demo_ready    = pyqtSignal()   # ← wird nach 3s nach Demo-Start emittiert
    unicorn_ready = pyqtSignal(bool)  # ← True: unicorn2lsl.py hat Verbindung bestätigt, False: Prozess gestoppt/beendet

    def __init__(self, parent=None):
        super().__init__("Geräte-Prozesse", parent)
        self._processes = {}
        self._watchers  = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Unicorn LSL ───────────────────────────────────────────
        unicorn_row = QHBoxLayout()
        self.light_unicorn    = self._make_light()
        self.btn_unicorn      = self._make_btn("▶ Unicorn starten", "#2d6a2d",
                                    lambda: self._launch("unicorn", ["devices/unicorn2lsl.py"]))
        self.btn_stop_unicorn = self._make_btn("■", "#6a2d2d",
                                    lambda: self._stop("unicorn"))
        self.btn_stop_unicorn.setFixedWidth(30)
        self.btn_stop_unicorn.setEnabled(False)
        unicorn_row.addWidget(self.light_unicorn)
        unicorn_row.addWidget(self.btn_unicorn)
        unicorn_row.addWidget(self.btn_stop_unicorn)
        layout.addLayout(unicorn_row)

        # ── Trigger Bridge ────────────────────────────────────────
        trigger_row = QHBoxLayout()
        self.light_trigger    = self._make_light()
        self.btn_trigger      = self._make_btn("▶ Trigger Bridge starten", "#2d6a2d",
                                    lambda: self._launch("trigger", ["devices/trigger_bridge.py"]))
        self.btn_stop_trigger = self._make_btn("■", "#6a2d2d",
                                    lambda: self._stop("trigger"))
        self.btn_stop_trigger.setFixedWidth(30)
        self.btn_stop_trigger.setEnabled(False)
        trigger_row.addWidget(self.light_trigger)
        trigger_row.addWidget(self.btn_trigger)
        trigger_row.addWidget(self.btn_stop_trigger)
        layout.addLayout(trigger_row)

        # ── CSV Replay ────────────────────────────────────────────
        replay_row = QHBoxLayout()
        self.light_replay    = self._make_light()
        self.btn_replay      = self._make_btn("▶ CSV Replay", "#2d4a6a",
                                    self._launch_replay)
        self.btn_stop_replay = self._make_btn("■", "#6a2d2d",
                                    lambda: self._stop("replay"))
        self.btn_stop_replay.setFixedWidth(30)
        self.btn_stop_replay.setEnabled(False)
        replay_row.addWidget(self.light_replay)
        replay_row.addWidget(self.btn_replay)
        replay_row.addWidget(self.btn_stop_replay)
        layout.addLayout(replay_row)

        # ── Log-Fenster ───────────────────────────────────────────
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120)
        self.log.setFont(QFont("Menlo", 9))
        self.log.setStyleSheet("background: #1e1e1e; color: #cccccc;")
        layout.addWidget(self.log)

        # ── Alle stoppen ──────────────────────────────────────────
        self.btn_stop_all = QPushButton("■ Alle Prozesse stoppen")
        self.btn_stop_all.setStyleSheet("background: #4a1a1a;")
        self.btn_stop_all.clicked.connect(self.stop_all)
        layout.addWidget(self.btn_stop_all)

    # ── CSV Replay: File-Dialog → Launch ─────────────────────────
    def _launch_replay(self):
        project_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..")
        )
        data_dir = os.path.join(project_root, "data")
        start_dir = data_dir if os.path.isdir(data_dir) else project_root

        path, _ = QFileDialog.getOpenFileName(
            self, "CSV für Demo wählen", start_dir, "CSV Files (*.csv)"
        )
        if not path:
            return

        self._log("replay", f"Starte: {os.path.basename(path)}")
        self._launch("replay", ["devices/csv_replay_lsl.py", path])

        # Signal nach außen damit main_window auto-verbinden kann
        QTimer.singleShot(3000, self.demo_ready)

    # ── Generischer Launch ────────────────────────────────────────
    def _launch(self, name: str, args: list):
        if name in self._processes:
            self._log(name, "Läuft bereits.")
            return

        python = sys.executable
        # args[0] ist immer das Script, args[1:] sind optionale Parameter
        script = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", args[0])
        )
        cmd = [python, "-u", script] + args[1:]   # -u: unbuffered, sonst hängen print()-Zeilen im Pipe-Puffer

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1
            )
        except Exception as e:
            self._log(name, f"FEHLER: {e}")
            return

        self._processes[name] = proc
        self._set_light(name, "orange")

        watcher = ProcessWatcher(name, proc)
        watcher.output.connect(self._log)
        watcher.finished.connect(self._on_finished)
        watcher.start()
        self._watchers[name] = watcher

        self._log(name, f"Gestartet (PID {proc.pid})")
        self._set_buttons(name, running=True)
        QTimer.singleShot(2000, lambda: self._set_light(name, "lime"))

    def _stop(self, name: str):
        proc = self._processes.pop(name, None)
        if proc:
            proc.send_signal(signal.SIGINT)
            self._log(name, "Stopp-Signal gesendet")
        self._set_light(name, "gray")
        self._set_buttons(name, running=False)
        if name == "unicorn":
            self.unicorn_ready.emit(False)

    def stop_all(self):
        for name in list(self._processes.keys()):
            self._stop(name)

    def _on_finished(self, name: str):
        self._processes.pop(name, None)
        self._log(name, "Prozess beendet")
        self._set_light(name, "gray")
        self._set_buttons(name, running=False)
        if name == "unicorn":
            self.unicorn_ready.emit(False)

    def _log(self, name: str, line: str):
        colors = {"unicorn": "#88ccff", "trigger": "#88ffaa", "replay": "#ffcc66"}
        color  = colors.get(name, "#ffffff")
        self.log.append(f'<span style="color:{color}">[{name}]</span> {line}')
        self.log.verticalScrollBar().setValue(
            self.log.verticalScrollBar().maximum()
        )
        if name == "unicorn" and "✓ Unicorn verbunden" in line:
            self.unicorn_ready.emit(True)

    def _set_light(self, name, color):
        widget = {"unicorn": self.light_unicorn,
                  "trigger": self.light_trigger,
                  "replay":  self.light_replay}.get(name)
        if widget:
            widget.setStyleSheet(f"color: {color}; font-size: 16px;")

    def _set_buttons(self, name, running: bool):
        mapping = {
            "unicorn": (self.btn_unicorn,  self.btn_stop_unicorn),
            "trigger": (self.btn_trigger,  self.btn_stop_trigger),
            "replay":  (self.btn_replay,   self.btn_stop_replay),
        }
        if name in mapping:
            start_btn, stop_btn = mapping[name]
            start_btn.setEnabled(not running)
            stop_btn.setEnabled(running)

    def _make_light(self):
        lbl = QLabel("●")
        lbl.setStyleSheet("color: gray; font-size: 16px;")
        lbl.setFixedWidth(20)
        return lbl

    def _make_btn(self, label, color, slot):
        btn = QPushButton(label)
        btn.setStyleSheet(f"background: {color};")
        btn.clicked.connect(slot)
        return btn
