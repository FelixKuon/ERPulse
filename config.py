"""Zentrale Geräte-Konfiguration für das Unicorn EEG-Setup.

Eigene Werte NICHT hier ändern, sondern in `config_local.py` (neben dieser
Datei) ablegen — die wird von Git ignoriert:

    UNICORN_BLUETOOTH_MAC = "aa-bb-cc-dd-ee-ff"
    UNICORN_PORT = "COM5"          # optional: Port fest vorgeben

Bluetooth-MAC-Adresse ermitteln:
  macOS:    blueutil --paired   (oder Systemeinstellungen > Bluetooth)
  Windows:  Einstellungen > Bluetooth & Geräte > Gerät > Weitere Details
            (oder Geräte-Manager > Anschlüsse (COM & LPT) > Eigenschaften)
"""

UNICORN_BLUETOOTH_MAC = ""   # z. B. "60-b6-47-e1-26-63"
UNICORN_PORT = ""            # leer = automatisch suchen
ARDUINO_PORT = ""            # leer = automatisch suchen

try:
    from config_local import *   # noqa: F401,F403
except ImportError:
    pass
