"""
core/ports.py — plattformunabhängige Suche nach den seriellen Ports von
Unicorn (Bluetooth-SPP) und Arduino (USB).

macOS:   /dev/cu.UN-…  bzw. /dev/cu.usbmodem…
Windows: COMx — der Unicorn erscheint nach dem Koppeln als „Standardmäßige
         serielle Verbindung über Bluetooth“ (ohne „UN-“ im Namen). Erkannt
         wird er daher über die Bluetooth-MAC in der Hardware-ID.
Linux:   /dev/rfcomm0 (nach `rfcomm bind`) bzw. /dev/ttyACM0
"""

import re
from serial.tools import list_ports

try:
    from config import UNICORN_BLUETOOTH_MAC, UNICORN_PORT, ARDUINO_PORT
except ImportError:   # config.py fehlt → alles automatisch
    UNICORN_BLUETOOTH_MAC = UNICORN_PORT = ARDUINO_PORT = ""

UNICORN_PORT_TOKENS = ("un-", "unicorn", "gtec", "g.tec")

# USB-Vendor-IDs gängiger Arduino-Boards und Klone
ARDUINO_VIDS = {
    0x2341,  # Arduino
    0x2A03,  # Arduino (dog hunter)
    0x1A86,  # WCH CH340
    0x0403,  # FTDI
    0x10C4,  # Silicon Labs CP210x
}
ARDUINO_NAME_TOKENS = ("usbmodem", "usbserial", "wchusbserial", "slab_usbtouart",
                       "arduino", "ch340", "ttyacm", "ttyusb")


def _mac_digits(mac: str) -> str:
    return re.sub(r"[^0-9a-f]", "", (mac or "").lower())


def _haystack(p) -> str:
    return " | ".join([
        p.device or "", p.name or "", p.description or "", p.hwid or "",
        getattr(p, "manufacturer", "") or "", getattr(p, "product", "") or "",
    ]).lower()


def find_unicorn_port(mac: str = None) -> str:
    """Sucht den Unicorn-Serial-Port. Reihenfolge: fest konfigurierter Port →
    MAC-Treffer → Namens-Treffer (macOS „UN-…“)."""
    if UNICORN_PORT:
        return UNICORN_PORT

    mac = _mac_digits(mac if mac is not None else UNICORN_BLUETOOTH_MAC)
    ports = list(list_ports.comports())

    if mac:
        by_mac = [p.device for p in ports if mac in _haystack(p).replace(":", "")
                  .replace("-", "")]
        if len(by_mac) >= 1:
            return by_mac[0]

    by_name = [p.device for p in ports
               if any(t in _haystack(p) for t in UNICORN_PORT_TOKENS)]
    if len(by_name) == 1:
        return by_name[0]

    available = [p.device for p in ports]
    if len(by_name) > 1:
        raise RuntimeError(
            f"Mehrere Unicorn-ähnliche Ports gefunden: {by_name} — bitte "
            f"UNICORN_PORT in config_local.py setzen.")
    raise RuntimeError(
        f"Kein Unicorn-Serial-Port gefunden. Verfügbare Ports: {available}. "
        f"Ist das Gerät per Bluetooth gekoppelt? Unter Windows zusätzlich die "
        f"MAC-Adresse in config_local.py eintragen (UNICORN_BLUETOOTH_MAC) "
        f"oder den Port fest vorgeben (UNICORN_PORT = \"COM5\").")


def find_arduino_port() -> str:
    """Sucht den Arduino (USB-Serial) anhand von Vendor-ID bzw. Portname."""
    if ARDUINO_PORT:
        return ARDUINO_PORT

    ports = sorted(list_ports.comports(), key=lambda p: p.device)
    # Bluetooth-Ports (Unicorn) nie als Arduino werten
    ports = [p for p in ports if "bthenum" not in (p.hwid or "").lower()
             and "bluetooth" not in (p.description or "").lower()]
    for p in ports:
        if p.vid in ARDUINO_VIDS:
            return p.device
    for p in ports:
        if any(t in _haystack(p) for t in ARDUINO_NAME_TOKENS):
            return p.device

    available = [p.device for p in ports]
    raise RuntimeError(
        "Kein Arduino gefunden — USB-Kabel und Board prüfen.\n"
        f"Vorhandene Ports: {', '.join(available) if available else 'keine'}\n"
        "Port ggf. fest vorgeben: ARDUINO_PORT in config_local.py.")
