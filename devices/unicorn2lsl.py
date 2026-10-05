#!/usr/bin/env python
# unicorn2lsl.py  – macOS M1, Python 3.x

import serial, struct, string, random, time
import numpy as np
from pylsl import StreamInfo, StreamOutlet
from serial.tools import list_ports

# ── Einstellungen ────────────────────────────────────────────────
UNICORN_PORT_TOKENS = ("un-", "unicorn", "gtec", "g.tec")


def find_unicorn_port() -> str:
    """Sucht den Unicorn-Serial-Port automatisch statt einen festen
    Pfad anzunehmen (der Port-Name/-Suffix kann sich je nach Gerät/
    macOS-Pairing ändern)."""
    candidates = []
    for p in list_ports.comports():
        haystack = " | ".join([
            p.device or "", p.name or "", p.description or "",
            p.hwid or "", getattr(p, "manufacturer", "") or "",
            getattr(p, "product", "") or "",
        ]).lower()
        if any(tok in haystack for tok in UNICORN_PORT_TOKENS):
            candidates.append(p.device)

    if len(candidates) == 1:
        return candidates[0]

    available = [p.device for p in list_ports.comports()]
    if len(candidates) > 1:
        raise RuntimeError(
            f"Mehrere Unicorn-ähnliche Ports gefunden: {candidates} "
            f"— bitte einen davon fest in DEVICE eintragen."
        )
    raise RuntimeError(
        f"Kein Unicorn-Serial-Port gefunden. Verfügbare Ports: {available} "
        f"— ist das Gerät via Bluetooth verbunden? (siehe BluetoothPanel)"
    )


DEVICE    = find_unicorn_port()
FSAMPLE   = 250
NCHAN     = 16
TIMEOUT   = 5

START_ACQ = bytes([0x61, 0x7C, 0x87])
STOP_ACQ  = bytes([0x63, 0x5C, 0xC5])
# ────────────────────────────────────────────────────────────────

# ── LSL Outlet VOR Serial anlegen ───────────────────────────────
# (damit pylsl-Initialisierung nicht den Serial-Timeout stört)
uid  = ''.join(random.choice(string.digits) for _ in range(6))
info = StreamInfo('Unicorn', 'EEG', NCHAN, FSAMPLE, 'float32', uid)
chns = info.desc().append_child("channels")
ch_labels = ["Fz","C3","Cz","C4","Pz","PO7","Oz","PO8",
             "AccX","AccY","AccZ","GyrX","GyrY","GyrZ","Battery","Counter"]
for label in ch_labels:
    ch = chns.append_child("channel")
    ch.append_child_value("label", label)
outlet = StreamOutlet(info)
print(f"[LSL] Stream angelegt: {uid}")

# ── Serial verbinden mit robustem Reset ─────────────────────────
s = serial.Serial(DEVICE, 115200, timeout=TIMEOUT)

print("[Serial] Sende STOP (Sicherheits-Reset)...")
s.write(STOP_ACQ)
time.sleep(1.0)
s.reset_input_buffer()

connected = False
for attempt in range(1, 4):
    s.write(START_ACQ)
    resp = s.read(3)
    print(f"[Serial] Versuch {attempt}: {resp.hex()!r}")
    if resp == b'\x00\x00\x00':
        connected = True
        break
    print(f"[Serial] Warte 2s...")
    s.write(STOP_ACQ)
    time.sleep(2.0)
    s.reset_input_buffer()

if not connected:
    s.close()
    del outlet
    raise RuntimeError(
        "Unicorn antwortet nicht.\n"
        "→ Bluetooth trennen, 5s warten, neu verbinden."
    )

print(f"✓ Unicorn verbunden | LSL-Stream: {uid}")

# ── Akquisitions-Loop ────────────────────────────────────────────
try:
    while True:
        payload = s.read(45)

        if len(payload) < 45:
            print("[WARN] Kurzes Paket, überspringe...")
            continue

        if payload[0:2] != b'\xC0\x00' or payload[43:45] != b'\x0D\x0A':
            print("[WARN] Ungültiges Paket, syncing...")
            continue

        battery = 100.0 * float(payload[2] & 0x0F) / 15.0

        eeg = np.zeros(8)
        for ch in range(8):
            raw = struct.unpack('>i', b'\x00' + payload[3+ch*3 : 6+ch*3])[0]
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

        sample = np.concatenate([eeg, accel, gyro, [battery], [counter]])
        outlet.push_sample(sample.tolist())

        if counter % FSAMPLE == 0:
            print(f"  t={counter/FSAMPLE:.0f}s  Batt={battery:.0f}%")

except KeyboardInterrupt:
    print("\n[Serial] Stoppe Akquisition...")
finally:
    s.write(STOP_ACQ)
    time.sleep(0.3)
    s.close()
    del outlet
    print("[Serial] Verbindung getrennt.")
