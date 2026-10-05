#!/usr/bin/env python3
# trigger_bridge.py  –  Arduino USB-Serial → LSL Marker Stream

import sys, os, serial, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.ports import find_arduino_port as find_arduino
from pylsl import StreamInfo, StreamOutlet
import time

# LSL Stream anlegen
info   = StreamInfo("Trigger", "Markers", 1, 0, "string", "unicorn_trigger_arduino")
outlet = StreamOutlet(info)
print("[LSL] Trigger-Stream gestartet")

port = find_arduino()
print(f"[Arduino] Port: {port}")
with serial.Serial(port, 115200, timeout=1) as ser:
    print("[Serial] Verbunden – warte auf Trigger ...")
    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue
            if line.startswith("TRIGGER:"):
                outlet.push_sample([line])
                print(f"[LSL ►] {line}")
            else:
                print(f"[Serial] {line}")   # alle anderen Meldungen anzeigen
        except KeyboardInterrupt:
            print("\n[trigger_bridge] Beendet.")
            break
