#!/usr/bin/env python3
"""
csv_replay_lsl.py  –  Unicorn CSV Datei → LSL Streams (EEG + Trigger)
Simuliert unicorn2lsl.py + trigger_bridge.py mit aufgezeichneten Daten.

CSV Format (Unicorn Recorder, kein Header):
  Spalten 0-7: EEG µV  |  Spalte 8: Trigger (0 oder Trigger-Nummer)
"""

import os
os.environ["LSLLIB_LOG_LEVEL"] = "3"   # LSL Warnungen unterdrücken

import numpy as np
import time
import argparse
import sys
from pylsl import StreamInfo, StreamOutlet

# ── Einstellungen ─────────────────────────────────────────────────────────────
FS        = 250       # Hz
CHUNK     = 1         # ← 1 Sample pro Push (statt 10 oder 25!)
SLEEP     = 1.0 / FS  # ← exakt 4ms zwischen Samples
SPEED     = 1.0       # 1.0 = Echtzeit, 2.0 = doppelt so schnell

CH_LABELS = ["Fz","C3","Cz","C4","Pz","PO7","Oz","PO8",
             "AccX","AccY","AccZ","GyrX","GyrY","GyrZ","Battery","Counter"]

def load_csv(path: str):
    """Lädt Unicorn CSV (kein Header, 9 Spalten: 8 EEG + Trigger)"""
    print(f"[CSV] Lade {path} ...")
    raw = np.loadtxt(path, delimiter=',')
    print(f"[CSV] {raw.shape[0]} Samples ({raw.shape[0]/FS:.1f}s), "
          f"{raw.shape[1]} Spalten")
    data_eeg = raw[:, :8].copy()
    data_trig = raw[:, 8].copy()

    # DC-Offset entfernen
    baseline = data_eeg[:500].mean(axis=0)
    data_eeg -= baseline

    # Unicorn ADC → µV
    SCALE = 4500000.0 / 50331642.0
    data_eeg *= SCALE
    print(f"[CSV] Skaliert: Ø Amplitude = {data_eeg[:500].std():.1f} µV")
    return data_eeg, data_trig

def find_first_trigger(data: np.ndarray) -> int:
    """Gibt Sample-Index des ersten Triggers zurück"""
    trig_col = data[:, 8]
    hits = np.where(trig_col > 0)[0]
    if len(hits) == 0:
        print("[CSV] Kein Trigger gefunden!")
        return len(data)
    print(f"[CSV] Erster Trigger bei Sample {hits[0]} "
          f"(t={hits[0]/FS:.2f}s) — Wert: {trig_col[hits[0]]:.0f}")
    return hits[0]

def make_eeg_outlet() -> StreamOutlet:
    info = StreamInfo('Unicorn', 'EEG', 16, FS, 'float32', 'unicorn_replay_001')
    chns = info.desc().append_child("channels")
    for label in CH_LABELS:
        ch = chns.append_child("channel")
        ch.append_child_value("label", label)
    return StreamOutlet(info)

def make_trigger_outlet() -> StreamOutlet:
    info = StreamInfo('Trigger', 'Markers', 1, 0, 'string', 'trigger_replay_001')
    return StreamOutlet(info)

def replay(data_eeg: np.ndarray, data_trig: np.ndarray, eeg_outlet: StreamOutlet,
           trig_outlet: StreamOutlet, speed: float = 1.0):
    n_samples = data_eeg.shape[0]
    last_trig = 0

    trig_indices = np.where(data_trig > 0)[0]
    print(f"[CSV] {len(trig_indices)} Trigger gefunden bei Samples: "
          f"{trig_indices[:10].tolist()}...")

    print(f"\n[Replay] Starte — {n_samples} Samples @ {FS}Hz "
          f"(Geschwindigkeit: {speed}x)")
    print("[Replay] Ctrl+C zum Stoppen\n")

    try:
        t_next = time.perf_counter()
        
        for i in range(n_samples):
            eeg_row  = data_eeg[i]
            trig_val = int(round(data_trig[i]))

            sample = eeg_row.tolist() + [0.0]*6 + [100.0] + [float(i)]
            eeg_outlet.push_sample(sample)

            if trig_val > 0 and trig_val != last_trig:
                marker = f"TRIGGER:{trig_val},{i}"
                trig_outlet.push_sample([marker])
                print(f"  ► Trigger {trig_val} @ t={i/FS:.2f}s")
            last_trig = trig_val if trig_val > 0 else 0

            # Präzises Timing: verhindert Drift und Bursts
            t_next += SLEEP / speed
            wait = t_next - time.perf_counter()
            if wait > 0:
                time.sleep(wait)

            if i % (FS * 30) == 0 and i > 0:
                print(f"  t={i/FS:.0f}s / {n_samples/FS:.0f}s")

    except KeyboardInterrupt:
        print("\n[Replay] Gestoppt.")

    print(f"[Replay] Fertig — {n_samples} Samples gesendet.")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unicorn CSV → LSL Replay")
    parser.add_argument("csv", help="Pfad zur CSV Datei")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Wiedergabe-Geschwindigkeit (default: 1.0)")
    parser.add_argument("--asr-only", action="store_true",
                        help="Nur pre-Trigger Daten senden (für ASR Kalibrierung)")
    args = parser.parse_args()

    data_eeg, data_trig = load_csv(args.csv)

    if args.asr_only:
        first_trig = find_first_trigger(np.column_stack((data_eeg, data_trig)))
        print(f"[ASR-Mode] Sende nur die ersten {first_trig} Samples "
              f"({first_trig/FS:.1f}s) für ASR-Kalibrierung")
        data_eeg = data_eeg[:first_trig]
        data_trig = data_trig[:first_trig]

    eeg_outlet = make_eeg_outlet()
    trig_outlet = make_trigger_outlet()
    print("[LSL] Streams bereit — warte 2s auf Subscribers...")
    time.sleep(2.0)

    replay(data_eeg, data_trig, eeg_outlet, trig_outlet, speed=args.speed)
