"""
core/bluetooth_ctl.py — gemeinsame blueutil-Logik für BluetoothPanel
(manuelle Einzel-Buttons) und die automatische Connect-Sequenz.

Kein Qt-Widget hier, nur Ausführungslogik + QThread-Worker.
"""

import re
import shutil
import subprocess
import time

from PyQt6.QtCore import QThread, pyqtSignal

# Disconnect/Unpair/Status antworten schnell. Pair/Connect blockieren laut
# manuellen Tests so lange, bis der Vorgang wirklich fertig ist (kein
# Fire-and-Forget) — die brauchen daher deutlich mehr Luft.
BLUEUTIL_TIMEOUT_S = 15
BLUEUTIL_PAIR_TIMEOUT_S = 60
# blueutil kehrt bei Disconnect/Unpair zurück, sobald der Befehl abgesetzt
# ist — der Bluetooth-Daemon braucht danach noch einen Moment, um den
# Zustand wirklich zu übernehmen. Ohne diese Pause laufen die Schritte zu
# schnell hintereinander und die Sequenz schlägt fehl.
STEP_SETTLE_S = 2.0
MAC_RE = re.compile(r'^[0-9A-Fa-f]{12}$|^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$')


def run_blueutil(args: list, timeout: float = BLUEUTIL_TIMEOUT_S) -> tuple:
    """Führt genau einen blueutil-Aufruf aus. Gibt (erfolgreich, Rohausgabe) zurück."""
    blueutil = shutil.which("blueutil")
    if blueutil is None:
        return False, "blueutil nicht gefunden — installieren mit: brew install blueutil"

    try:
        proc = subprocess.run(
            [blueutil] + args,
            capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return False, f"Timeout nach {timeout}s"
    except Exception as e:
        return False, str(e)

    out = (proc.stdout + proc.stderr).strip() or "(keine Ausgabe)"
    return proc.returncode == 0, f"[exit {proc.returncode}] {out}"


class BlueutilWorker(QThread):
    """Führt genau einen blueutil-Befehl in einem separaten Thread aus."""
    result = pyqtSignal(bool, str)   # (erfolgreich, Rohausgabe)

    def __init__(self, args: list):
        super().__init__()
        self.args = args

    def run(self):
        ok, out = run_blueutil(self.args)
        self.result.emit(ok, out)


class AutoConnectWorker(QThread):
    """Deterministische Reset-Sequenz: Disconnect → Unpair → Pair → Connect
    (zweimal). Jeder Schritt wartet auf den vorherigen blueutil-Aufruf (der
    selbst blockiert, bis er fertig ist) plus eine kurze Pause, damit sich
    der Bluetooth-Status setzt. Der erste Connect-Versuch direkt nach Pair
    meldet laut Tests zwar oft Erfolg, stellt die Verbindung aber noch
    nicht wirklich her — ein zweiter Versuch (der manuell reproduzierbare
    Workaround) schließt zuverlässig ab. Kein offener Retry-Loop, genau
    zwei Versuche — bei Fehlschlag einfach per erneutem Klick neu starten."""
    step_changed = pyqtSignal(str)
    finished_ok  = pyqtSignal(bool, str)   # (am Ende wirklich verbunden, Log)

    def __init__(self, mac: str):
        super().__init__()
        self.mac = mac

    def run(self):
        prereq_steps = [
            ("Disconnect", ["--disconnect", self.mac], BLUEUTIL_TIMEOUT_S),
            ("Unpair",     ["--unpair", self.mac],     BLUEUTIL_TIMEOUT_S),
            ("Pair",       ["--pair", self.mac],       BLUEUTIL_PAIR_TIMEOUT_S),
        ]
        log = []
        for i, (label, args, timeout) in enumerate(prereq_steps, start=1):
            hint = " (kann dauern)" if timeout == BLUEUTIL_PAIR_TIMEOUT_S else ""
            self.step_changed.emit(f"Schritt {i}/4: {label} …{hint}")
            ok, out = run_blueutil(args, timeout=timeout)
            log.append(f"{label}: {out}")
            if not ok:
                self.finished_ok.emit(False, "\n".join(log))
                return
            self.step_changed.emit(f"Schritt {i}/4: {label} fertig — kurze Pause …")
            time.sleep(STEP_SETTLE_S)

        connected = False
        for attempt in (1, 2):
            self.step_changed.emit(f"Schritt 4/4: Connect (Versuch {attempt}/2) …")
            ok, out = run_blueutil(["--connect", self.mac], timeout=BLUEUTIL_PAIR_TIMEOUT_S)
            log.append(f"Connect Versuch {attempt}: {out}")
            connected = ok
            if attempt == 1:
                time.sleep(STEP_SETTLE_S)

        self.finished_ok.emit(connected, "\n".join(log))
