"""Rauchtest: Hauptfenster startet (ohne Gerät), spielt die Beispielaufnahme
ab und der ERP-Prozessor sammelt Epochen. Läuft headless (QT_QPA_PLATFORM=offscreen)."""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from gui.theme import apply_theme
from gui.connection_dev_window import ConnectionDevWindow

app = QApplication(sys.argv)
apply_theme(app)
win = ConnectionDevWindow()
win.show()
win._start_replay("examples/sample_recording/ERP_demo_stimulation.csv", 40.0)


def check():
    n = win.processor.n_accepted
    print(f"Epochen akzeptiert: {n}")
    app.exit(0 if n > 0 else 1)


QTimer.singleShot(9000, check)
sys.exit(app.exec())
