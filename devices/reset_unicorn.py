# reset_unicorn.py  — einmalig ausführen
import sys, os, serial, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.ports import find_unicorn_port

DEVICE   = find_unicorn_port()
STOP_ACQ = bytes([0x63, 0x5C, 0xC5])
START_ACQ = bytes([0x61, 0x7C, 0x87])

s = serial.Serial(DEVICE, 115200, timeout=3)
print("Sende STOP...")
s.write(STOP_ACQ)
time.sleep(1.5)
s.reset_input_buffer()
print(f"Puffer geleert. Bytes im Buffer: {s.in_waiting}")

print("Sende START...")
s.write(START_ACQ)
resp = s.read(3)
print(f"Response: {resp.hex()!r}")

if resp == b'\x00\x00\x00':
    print("✓ Unicorn bereit!")
else:
    print("✗ Immer noch falsch — Bluetooth trennen und neu verbinden")

s.close()
