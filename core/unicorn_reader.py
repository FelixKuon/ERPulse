"""
core/unicorn_reader.py — In-Process Serial-Reader für den Unicorn Hybrid
Black. Ersetzt devices/unicorn2lsl.py für den GUI-internen Betrieb (kein
Subprozess, kein LSL) — die Steuerbytes/Handshake-Logik und die Dekodierung
sind 1:1 aus unicorn2lsl.py übernommen. unicorn2lsl.py selbst bleibt
unverändert und weiter eigenständig lauffähig.
"""

import struct
import threading
import time

import numpy as np
import serial
from PyQt6.QtCore import QThread, pyqtSignal

from core.ports import find_unicorn_port   # noqa: F401  (auch von außen importiert)

FSAMPLE     = 250
PACKET_SIZE = 45
BAUDRATE    = 115200
START_ACQ   = bytes([0x61, 0x7C, 0x87])
STOP_ACQ    = bytes([0x63, 0x5C, 0xC5])
# Kurze Pause, bevor der Serial-Port geöffnet wird — direkt nach einem
# frischen Bluetooth-Connect ist die RFCOMM-Verbindung (v. a. auf macOS) oft
# noch nicht wirklich bereit, ein sofortiger Handshake-Versuch schlägt dann fehl.
STARTUP_SETTLE_S = 0.5


class UnicornReader(QThread):
    """Öffnet den Unicorn-Serial-Port, führt den STOP/START-Handshake aus
    und liest danach fortlaufend Pakete. Meldet neue Samples, Status-
    wechsel und Fehler über Qt-Signale statt über LSL zu publizieren.

    Zeitachse: Bluetooth liefert die Pakete gebündelt (Burst-Delivery), die
    Ankunftszeit ist deshalb ungleichmäßig — das Gerät tastet aber konstant
    mit 250 Hz ab. Die Zeitstempel werden daher aus dem geräteeigenen
    Sample-Counter rekonstruiert statt aus der Ankunftszeit übernommen.
    Lücken im Counter bedeuten echten Samplever­lust und werden durch lineare
    Interpolation aufgefüllt, damit die Abtastrate durchgehend stimmt
    (sonst verschieben sich Filter-Phase und ERP-Epochenfenster).
    """

    samples_received = pyqtSignal(object, object)   # (ts[n], data[n, 16])
    status_changed   = pyqtSignal(str)
    error            = pyqtSignal(str)

    MAX_BAD_READS = 25    # aufeinanderfolgende leere/ungültige Pakete, bis wir abbrechen
    MAX_GAP_FILL  = 125   # bis 0,5 s Ausfall interpolieren, darüber nur zählen
    BATCH_MAX     = 25    # Samples pro Signal-Emission (statt 250 Signale/s)
    BATCH_MAX_S   = 0.02

    def __init__(self, port: str = None, handshake_timeout: float = 5.0):
        super().__init__()
        self._port_override = port
        self._handshake_timeout = handshake_timeout
        self._stop_event   = threading.Event()   # echtes Ende — Port wird geschlossen
        self._pause_event  = threading.Event()   # pausiert — Verbindung bleibt offen
        self._resume_event = threading.Event()   # weckt aus der Pause auf
        self._ser = None   # von außen zugreifbar, s. force_close_port()

        # Zeitachsen-Rekonstruktion
        self._counter0    = None   # Counter-Wert beim Verankern
        self._t0          = None   # Uhrzeit beim Verankern
        self._last_counter = None
        self._last_sample  = None
        self.dropped_samples = 0   # nicht mehr auffüllbare Ausfälle

    def stop(self):
        self._stop_event.set()
        self._resume_event.set()   # falls gerade pausiert: aufwecken, damit stop bemerkt wird

    def pause(self):
        """Stoppt die Aufnahme auf dem Gerät (STOP_ACQ), lässt die
        Bluetooth-/Serial-Verbindung aber offen. Schließen des Ports
        reißt auf macOS oft die ganze Bluetooth-Verbindung mit ab —
        pausieren statt schließen erlaubt einen schnellen Neustart ohne
        neuen Bluetooth-Handshake."""
        self._resume_event.clear()
        self._pause_event.set()

    def resume(self):
        self._pause_event.clear()
        self._resume_event.set()

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def force_close_port(self):
        """Schließt den Serial-Port von außen (anderer Thread). Auf macOS
        kann ein Bluetooth-SPP-Port hängen bleiben und den konfigurierten
        read()-Timeout ignorieren — das Schließen von außen reißt so einen
        hängenden read() zuverlässig ab, statt den Thread für immer
        blockiert zu lassen (was einen Neustart unmöglich machen würde)."""
        ser = self._ser
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def run(self):
        try:
            port = self._port_override or find_unicorn_port()
        except RuntimeError as e:
            self.error.emit(str(e))
            return

        self.status_changed.emit(f"Warte {STARTUP_SETTLE_S:.1f}s, bis die Bluetooth-Verbindung sich setzt …")
        time.sleep(STARTUP_SETTLE_S)
        if self._stop_event.is_set():
            return

        self.status_changed.emit(f"Öffne {port} …")
        try:
            ser = serial.Serial(port, BAUDRATE, timeout=self._handshake_timeout)
        except serial.SerialException as e:
            self.error.emit(f"Port konnte nicht geöffnet werden: {e}")
            return
        self._ser = ser

        try:
            if not self._handshake(ser):
                self.error.emit(
                    "Kein gültiges Handshake-Signal vom Unicorn erhalten "
                    "(Bluetooth evtl. nicht wirklich verbunden — "
                    "Verbindungssequenz erneut ausführen)."
                )
                return

            ser.timeout = 1.0   # kurzer Read-Timeout, damit Stop-/Pause-Flag zeitnah geprüft wird
            while not self._stop_event.is_set():
                self.status_changed.emit("Verbunden — Streaming läuft")
                self._reset_timeline()
                self._stream(ser)
                if self._stop_event.is_set():
                    break
                if self._pause_event.is_set():
                    self._do_pause(ser)
        finally:
            try:
                ser.write(STOP_ACQ)
                time.sleep(0.05)
            except Exception:
                pass
            try:
                ser.close()
            except Exception:
                pass
            self._ser = None
            self.status_changed.emit("Verbindung geschlossen")

    def _handshake(self, ser: "serial.Serial") -> bool:
        try:
            ser.write(STOP_ACQ)
            time.sleep(1.0)
            ser.reset_input_buffer()

            for attempt in range(1, 4):
                if self._stop_event.is_set():
                    return False
                ser.write(START_ACQ)
                resp = ser.read(3)
                self.status_changed.emit(f"Handshake Versuch {attempt}: {resp.hex()!r}")
                if resp == b'\x00\x00\x00':
                    return True
                ser.write(STOP_ACQ)
                time.sleep(2.0)
                ser.reset_input_buffer()
            return False
        except (serial.SerialException, OSError):
            return False   # Port wurde von außen erzwungen geschlossen (stop)

    def _do_pause(self, ser: "serial.Serial"):
        """Wartet in pausiertem Zustand (Verbindung bleibt offen) auf
        resume() oder stop()."""
        self.status_changed.emit("Pausiert — Verbindung bleibt offen")
        try:
            ser.write(STOP_ACQ)
        except Exception:
            pass

        while not self._stop_event.is_set() and self._pause_event.is_set():
            self._resume_event.wait(timeout=0.5)
        if self._stop_event.is_set():
            return

        self.status_changed.emit("Setze Streaming fort …")
        if not self._resume_acq(ser):
            self.error.emit(
                "Fortsetzen fehlgeschlagen — Gerät antwortet nicht mehr. "
                "Bitte Verbindung über Bluetooth neu aufbauen."
            )
            self._stop_event.set()

    def _resume_acq(self, ser: "serial.Serial") -> bool:
        old_timeout = ser.timeout
        ser.timeout = self._handshake_timeout
        try:
            ser.reset_input_buffer()
            ser.write(START_ACQ)
            resp = ser.read(3)
        except (serial.SerialException, OSError):
            return False
        finally:
            try:
                ser.timeout = old_timeout
            except Exception:
                pass
        return resp == b'\x00\x00\x00'

    def _reset_timeline(self):
        """Zeitachse neu verankern (bei Start und nach jedem Resume, da das
        Gerät seinen Sample-Counter mit der Aufnahme neu beginnt)."""
        self._counter0     = None
        self._t0           = None
        self._last_counter = None
        self._last_sample  = None

    def _timeline(self, sample: np.ndarray):
        """Ordnet einem dekodierten Sample seine echte Zeit zu und füllt
        Lücken im Sample-Counter auf. Gibt eine Liste von (ts, sample)
        zurück — normalerweise genau ein Eintrag, bei Ausfall mehrere."""
        counter = int(sample[15])

        if self._counter0 is None or counter <= (self._last_counter or -1):
            self._counter0     = counter
            self._t0           = time.time()
            self._last_counter = counter
            self._last_sample  = sample
            return [(self._t0, sample)]

        gap = counter - self._last_counter - 1
        out = []

        if 0 < gap <= self.MAX_GAP_FILL:
            # Fehlende Samples linear zwischen letztem und aktuellem Wert
            prev = self._last_sample
            for k in range(1, gap + 1):
                frac = k / (gap + 1)
                filled = prev + (sample - prev) * frac
                filled[15] = self._last_counter + k
                out.append((self._ts_for(self._last_counter + k), filled))
        elif gap > self.MAX_GAP_FILL:
            # Zu großer Ausfall: nicht sinnvoll interpolierbar, Zeitachse
            # neu verankern, damit sie nicht dauerhaft verschoben bleibt
            self.dropped_samples += gap
            self._counter0 = counter
            self._t0       = time.time()

        out.append((self._ts_for(counter), sample))
        self._last_counter = counter
        self._last_sample  = sample
        return out

    def _ts_for(self, counter: int) -> float:
        return self._t0 + (counter - self._counter0) / FSAMPLE

    def _stream(self, ser: "serial.Serial"):
        bad_reads = 0
        batch = []
        last_emit = time.time()

        while not self._stop_event.is_set() and not self._pause_event.is_set():
            try:
                payload = ser.read(PACKET_SIZE)
            except (serial.SerialException, OSError):
                if not self._stop_event.is_set():
                    self.error.emit("Verbindung unerwartet verloren.")
                    self._stop_event.set()
                return

            if (len(payload) < PACKET_SIZE
                    or payload[0:2] != b'\xC0\x00'
                    or payload[43:45] != b'\x0D\x0A'):
                bad_reads += 1
                if bad_reads >= self.MAX_BAD_READS:
                    self.error.emit(
                        "Verbindung verloren (wiederholt leere/ungültige Pakete) "
                        "— Bluetooth-Verbindung erneut aufbauen."
                    )
                    self._stop_event.set()
                    return
                continue
            bad_reads = 0

            batch.extend(self._timeline(self._decode(payload)))

            now = time.time()
            if len(batch) >= self.BATCH_MAX or (now - last_emit) >= self.BATCH_MAX_S:
                self._emit_batch(batch)
                batch = []
                last_emit = now

        if batch:
            self._emit_batch(batch)

    def _emit_batch(self, batch: list):
        ts   = np.array([b[0] for b in batch])
        data = np.array([b[1] for b in batch])
        self.samples_received.emit(ts, data)

    @staticmethod
    def _decode(payload: bytes) -> np.ndarray:
        battery = 100.0 * float(payload[2] & 0x0F) / 15.0

        eeg = np.zeros(8)
        for ch in range(8):
            raw = struct.unpack('>i', b'\x00' + payload[3 + ch * 3: 6 + ch * 3])[0]
            if raw & 0x00800000:
                raw -= 0x01000000
            eeg[ch] = float(raw) * 4500000.0 / 50331642.0

        accel = np.array([
            struct.unpack('<h', payload[27:29])[0] / 4096.0,
            struct.unpack('<h', payload[29:31])[0] / 4096.0,
            struct.unpack('<h', payload[31:33])[0] / 4096.0,
        ])
        gyro = np.array([
            struct.unpack('<h', payload[33:35])[0] / 32.8,
            struct.unpack('<h', payload[35:37])[0] / 32.8,
            struct.unpack('<h', payload[37:39])[0] / 32.8,
        ])
        counter = struct.unpack('<L', payload[39:43])[0]

        return np.concatenate([eeg, accel, gyro, [battery], [counter]])
