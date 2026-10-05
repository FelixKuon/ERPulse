# Projektübergabe

Dieses Dokument ist für alle, die ERPulse weiterentwickeln oder die Messreihe fortsetzen. Die
Nutzer-Sicht steht in der [README](README.md); hier steht, **wie es gebaut ist, warum es so gebaut ist und
was als Nächstes dran wäre.**

## Stand in einem Absatz

Die Live-Anwendung läuft stabil mit dem Unicorn unter macOS (Streaming, Filter, ERP, TFR, ASR, Aufnahme,
Replay). Die Offline-Auswertung ist vollständig und getestet. Windows/Linux: Port-Erkennung und Start
sind vorbereitet und per Unit-Test/CI abgesichert, **aber noch nicht mit echter Hardware erprobt**.
Wissenschaftlich ist die Frage „Latenzunterschied zwischen Körperstellen“ mit den bisherigen Daten
**nicht entschieden** (siehe unten).

## Architektur

```
 Unicorn (BT-SPP) ──► UnicornReader (QThread) ─┐
 CSV-Replay ────────► ReplayReader  (QThread) ─┤ samples_received(ts, data[n,8])
                                                ▼
                              ConnectionDevWindow (gui/connection_dev_window.py)
 Arduino (USB) ─────► TriggerReader (QThread) ──► trigger_received(ts, "TRIGGER:…")
                                                │
        ┌──────────── nur NEUE Samples ─────────┤
        ▼               ▼              ▼        ▼
  RealtimeFilter     ASR (opt.)   ERPProcessor / TFRProcessor    SessionRecorder
  utils/filters.py   core/asr.py  core/*_processor.py            core/session_recorder.py
```

* **Einstieg:** `app.py` → `ConnectionDevWindow`. Alles läuft in einem Prozess, ohne LSL und ohne
  Subprozesse.
* **Reader sind austauschbar** (gleiche Signale): `UnicornReader`, `ReplayReader`. Wer ein anderes
  EEG-Gerät anbinden will, schreibt einen weiteren Reader mit `samples_received(ts, data[n, 8])`,
  `status_changed`, `error` sowie `stop/pause/resume`.
* **Port-Suche:** `core/ports.py` (macOS `UN-…`, Windows per MAC in der Hardware-ID, Arduino per USB-VID).
  Fester Port über `config_local.py`.
* **Bluetooth-Kopplung:** `core/bluetooth_ctl.py` + `gui/bluetooth_panel.py` benutzen `blueutil` und
  sind nur für macOS. Auf Windows/Linux zeigt das Panel stattdessen eine Anleitung und einen
  „Port suchen“-Knopf.

### Der LSL-Altbau

`main.py`, `gui/main_window.py`, `gui/connection_panel.py`, `gui/device_launcher.py`,
`core/lsl_receiver.py` und `devices/*.py` sind der **ältere Aufbau mit LSL und Subprozessen**. Sie bleiben
als Referenz im Repo, werden aber nicht mehr gepflegt (braucht `pylsl`, siehe `requirements-dev.txt`).
Bekanntes Problem dort: `_update_plots()` verarbeitet bei jedem Frame den *ganzen* Ringpuffer neu
(Filter + ERP/TFR + Recorder) – im neuen Fenster werden dagegen nur neue Samples verarbeitet.
Wer aufräumen will: die genannten Dateien nach `legacy/` verschieben bzw. löschen.

## Entscheidungen und Stolperfallen

Das sind die Stellen, an denen früher Zeit verloren ging:

1. **Zeitachse aus dem Sample-Zähler.** Bluetooth liefert Pakete in Schüben; die Ankunftszeit ist
   unbrauchbar. `UnicornReader` rekonstruiert die Zeit aus dem Gerätezähler und interpoliert Lücken
   (bis 0,5 s). Sonst verschieben sich Filterphase und Epochenfenster.
2. **Hängende Ports.** Auf macOS ignoriert ein SPP-Port manchmal den Read-Timeout. Darum gibt es
   `force_close_port()`, das aus einem anderen Thread geschlossen wird. Und: **Pause statt Schließen**
   – das Schließen des Ports reißt dort oft die ganze Bluetooth-Verbindung mit.
3. **macOS-Kopplung nur über die Sequenz** Disconnect → Unpair → Pair → Connect (zweimal). Alles andere war
   unzuverlässig.
4. **Trigger-Semantik:** Das Sample mit `trigger > 0` ist das erste *nach* dem Reiz (t = 0). Der Trigger wird
   nach allen früheren Samples und vor diesem gemeldet.
5. **ERP-Fenster live:** −200…800 ms, TFR braucht mehr Vorlauf (Puffer 1500 ms). Live läuft ein
   kausales IIR-Filter, dessen Laufzeit die Kurve gegenüber der Offline-Auswertung (`filtfilt`,
   nullphasig) verschiebt – **Latenzen daher nur offline auswerten.**
6. **ERPProcessor(store_epochs=False)** live, `True` offline (SEM, Einzeltrials, Permutationstests).

### Trigger-Protokoll

Der Arduino sendet je Reiz **eine Textzeile** mit 115 200 Baud über USB-Serial:

```
TRIGGER:<laufende Nummer>,<millis()>
```

Alle anderen Zeilen werden als Statusmeldung im Trigger-Log angezeigt. Die Firmware (UNO R4 WiFi) liegt in
[`firmware/trigger/`](firmware/trigger/README.md); jede andere Firmware muss nur diese Zeile ausgeben.

### Aufnahmeformat

CSV pro Sample (`t, counter, raw_<Kanal>…, flt_<Kanal>…, trigger, asr`) plus JSON mit Metadaten und
Ereignisliste – Details im Kopf von `core/session_recorder.py`. Replay und Offline-Auswertung lesen die
**Rohkanäle**.

## Wissenschaftlicher Stand

Quelle der Wahrheit: [`praesentation/README.md`](praesentation/README.md). Kurz:

* **Belastbar:** Die akustische Dämpfung (Noise-Cancelling) verändert die frühe Antwort deutlich
  (zweimal dasselbe Fenster, zwei Messtage); zwei gedämpfte Kontrollen unterscheiden sich nicht
  → die Verarbeitungskette ist reproduzierbar.
* **Nicht entschieden:** Latenzunterschiede zwischen Körperstellen (Fuß/Oberarm, Oberschenkel/Wade).
  Die Gipfellatenz allein schwankt allein mit der Trigger-Auswahl stark; immer **Kreuzkorrelation und
  Cluster-Test mitberichten**.
* **Zurückgezogen:** Der Applikatorvergleich (Linse vs. Standardkopf) – das Stoßwellengerät hatte
  bei den Vergleichsaufnahmen Probleme, der Vergleich hätte das Gerät statt des Applikators gemessen.
* **Auswertungsprotokoll:** erste 10 Impulse jeder Aufnahme verwerfen (`drop_first=10`), nur lange
  Messungen verwenden.
* **Zwei Faktoren, nicht einer:** Bei der Reihe vom 13.08. unterscheiden sich „keinReiz“ und „nurAkustisch“
  *nur* in der Akustikdämpfung – beide haben keinen Hautreiz. Abbildungen müssen immer beide Faktoren
  beschriften.

## Offene Punkte / nächste Schritte

1. **Windows-Test mit echtem Unicorn** (und ggf. COM-Port-Verhalten bei Wiederverbindung); Rückmeldung
   als Issue.
2. **Versuchsdesign ändern:** Bedingungen *innerhalb einer Aufnahme abwechseln* statt nacheinander
   zu messen. Drift über die Sitzung (Impedanz, Wachheit, Gewöhnung) liegt sonst deckungsgleich auf dem
   Bedingungsunterschied – das bringt mehr als mehr Epochen.
3. **Mehr Epochen:** Unter ~30 Epochen ist eine Amplitudenangabe ohne Kontrolle nicht belastbar
   (`praesentation/…/A4_mittelungsgewinn`).
4. **Applikatorvergleich sauber wiederholen** (Code liegt noch in `figuren_praesentation.py`).
5. **Reizzeitpunkt validieren:** Der Reiz (D11-Puls) und die Trigger-Zeile werden nacheinander ausgelöst; die
   Verzögerung zum tatsächlichen Reiz (Gerät, Applikator) ist nicht gemessen.
6. **Altbau aufräumen** (siehe oben) und optional ein englisches README.
7. **Marker-Zeitstempel:** Trigger tragen die Rechnerzeit beim Eintreffen der Zeile; die Arduino-`millis()`
   werden nicht zur Synchronisation genutzt. Ein fester Versatz/Jitter wäre damit prüfbar.

## Entwickeln

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q              # Unit-Tests (Latenzmaße, Triggerauswahl, Port-Suche)
QT_QPA_PLATFORM=offscreen python tests/smoke_gui.py   # GUI-Rauchtest mit Beispielaufnahme
python figuren_praesentation.py        # Abbildungen neu erzeugen (braucht die Originaldaten)
```

Eigene Messdaten landen in `recordings/` (von Git ignoriert).
