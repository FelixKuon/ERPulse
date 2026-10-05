import threading
import numpy as np
from collections import deque
from pylsl import StreamInlet, resolve_byprop
from PyQt6.QtCore import QObject, pyqtSignal

class LSLReceiver(QObject, threading.Thread):
    trigger_received = pyqtSignal(float, str)

    def __init__(self, eeg_buflen=25000, on_trigger=None):
        QObject.__init__(self)
        threading.Thread.__init__(self, daemon=True)
        self.eeg_buffer  = deque(maxlen=eeg_buflen)
        self.on_trigger  = on_trigger
        self._stop_event = threading.Event()
        self.inlet_eeg   = None
        self.inlet_trig  = None
        self.connected   = False

    def connect(self, timeout=10):
        try:
            eeg_s  = resolve_byprop("name", "Unicorn",  timeout=timeout)
            trig_s = resolve_byprop("name", "Trigger",  timeout=timeout)
            if not eeg_s:
                return False, "Unicorn Stream nicht gefunden"
            if not trig_s:
                return False, "Trigger Stream nicht gefunden"
            self.inlet_eeg  = StreamInlet(eeg_s[0],  max_buflen=60)
            self.inlet_trig = StreamInlet(trig_s[0], max_buflen=60)
            self.connected  = True
            return True, "Verbunden"
        except Exception as e:
            return False, str(e)

    def run(self):
        while not self._stop_event.is_set():
            if not self.connected:
                self._stop_event.wait(0.1)
                continue
            chunk, timestamps = self.inlet_eeg.pull_chunk(timeout=0.05, max_samples=50)
            
            if chunk and len(timestamps) > 1:
                # Timestamps gleichmäßig verteilen falls Bursts
                t0, t1 = timestamps[0], timestamps[-1]
                dt = (t1 - t0)
                if dt < 1e-6:  # Burst: alle gleich
                    dt = len(timestamps) / 250.0
                    timestamps = [t0 + i * (dt / len(timestamps))
                                 for i in range(len(timestamps))]

            for s, t in zip(chunk, timestamps):
                self.eeg_buffer.append((t, np.array(s)))
            sample, ts = self.inlet_trig.pull_sample(timeout=0.0)
            if sample:
                print(f"[LSL] Trigger: {sample[0]} @ t={ts:.3f}")
                self.trigger_received.emit(ts, sample[0])

    def stop(self):
        self._stop_event.set()

    def get_eeg_array(self):
        buf = list(self.eeg_buffer)
        if not buf:
            return np.array([]), np.array([])
        ts   = np.array([x[0] for x in buf])
        data = np.array([x[1] for x in buf])
        return ts, data
