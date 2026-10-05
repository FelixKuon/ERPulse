"""
core/trigger_reader.py — In-Process Arduino-Trigger-Reader. Ersetzt
devices/trigger_bridge.py für den GUI-internen Betrieb (kein Subprozess,
kein LSL). trigger_bridge.py selbst bleibt unverändert und weiter
eigenständig lauffähig.
"""

import threading
import time

import serial
from PyQt6.QtCore import QThread, pyqtSignal

from core.ports import find_arduino_port   # noqa: F401


class TriggerReader(QThread):
    """Liest Zeilen vom Arduino, erkennt das 'TRIGGER:'-Präfix. Gleiche
    Signalform wie das bisherige LSLReceiver.trigger_received, damit
    ERPProcessor/TFRProcessor.on_trigger() später unverändert weiter
    genutzt werden können."""

    trigger_received = pyqtSignal(float, str)
    status_changed    = pyqtSignal(str)
    error             = pyqtSignal(str)

    def __init__(self, port: str = None):
        super().__init__()
        self._port_override = port
        self._stop_event = threading.Event()
        self._ser = None   # von außen zugreifbar, s. force_close_port()

    def stop(self):
        self._stop_event.set()

    def force_close_port(self):
        """Schließt den Serial-Port von außen (anderer Thread), um einen
        hängenden readline() zu unterbrechen — siehe UnicornReader für den
        Hintergrund."""
        ser = self._ser
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def run(self):
        try:
            port = self._port_override or find_arduino_port()
        except RuntimeError as e:
            self.error.emit(str(e))
            return

        self.status_changed.emit(f"Öffne {port} …")
        try:
            ser = serial.Serial(port, 115200, timeout=1)
        except serial.SerialException as e:
            self.error.emit(f"Port konnte nicht geöffnet werden: {e}")
            return
        self._ser = ser

        self.status_changed.emit("Verbunden — warte auf Trigger …")
        try:
            while not self._stop_event.is_set():
                try:
                    line = ser.readline().decode(errors="ignore").strip()
                except (serial.SerialException, OSError):
                    return   # Port wurde von außen erzwungen geschlossen (stop)
                if not line:
                    continue
                ts = time.time()
                if line.startswith("TRIGGER:"):
                    self.trigger_received.emit(ts, line)
                else:
                    self.status_changed.emit(f"[Arduino] {line}")
        finally:
            try:
                ser.close()
            except Exception:
                pass
            self._ser = None
            self.status_changed.emit("Verbindung geschlossen")
