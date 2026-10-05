"""Port-Erkennung: Windows (COMx, MAC in der Hardware-ID), macOS, Linux."""
import pathlib
import sys
from types import SimpleNamespace as P

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import core.ports as ports


def _port(device, desc="n/a", hwid="n/a", vid=None):
    return P(device=device, name=device, description=desc, hwid=hwid,
             manufacturer=None, product=None, vid=vid)


def _patch(monkeypatch, plist, mac="60-b6-47-e1-26-63"):
    monkeypatch.setattr(ports.list_ports, "comports", lambda: plist)
    monkeypatch.setattr(ports, "UNICORN_PORT", "")
    monkeypatch.setattr(ports, "UNICORN_BLUETOOTH_MAC", mac)
    monkeypatch.setattr(ports, "ARDUINO_PORT", "")


def test_windows_unicorn_per_mac(monkeypatch):
    _patch(monkeypatch, [
        _port("COM3", "Standardmäßige serielle Verbindung über Bluetooth (COM3)",
              r"BTHENUM\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000\7&2A&0&000000000000_00000000"),
        _port("COM5", "Standardmäßige serielle Verbindung über Bluetooth (COM5)",
              r"BTHENUM\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0002\7&2A&0&60B647E12663_C00000000"),
        _port("COM7", "Arduino Uno (COM7)", r"USB VID:PID=2341:0043", vid=0x2341),
    ])
    assert ports.find_unicorn_port() == "COM5"
    assert ports.find_arduino_port() == "COM7"


def test_macos_unicorn_per_name(monkeypatch):
    _patch(monkeypatch, [
        _port("/dev/cu.UN-20230428", "n/a"),
        _port("/dev/cu.usbmodem1101", "n/a"),
    ], mac="")
    assert ports.find_unicorn_port() == "/dev/cu.UN-20230428"
    assert ports.find_arduino_port() == "/dev/cu.usbmodem1101"


def test_arduino_ignores_bluetooth_ports(monkeypatch):
    _patch(monkeypatch, [_port("COM3", "Bluetooth link", r"BTHENUM\x")])
    try:
        ports.find_arduino_port()
    except RuntimeError:
        return
    raise AssertionError("Bluetooth-Port darf nicht als Arduino gelten")


def test_manual_override(monkeypatch):
    _patch(monkeypatch, [])
    monkeypatch.setattr(ports, "UNICORN_PORT", "COM9")
    assert ports.find_unicorn_port() == "COM9"
