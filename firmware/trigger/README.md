# Trigger-Firmware (Arduino UNO R4 WiFi)

Löst die Reize aus **und** meldet jeden Reiz an ERPulse. Ein Tastendruck startet eine feste Sequenz von
72 Reizen mit pseudozufälligen Pausen (3–7 s); ein zweiter Druck bricht ab. Die 12×8-LED-Matrix zeigt
Status (WLAN, Herzschlag, Countdown, Fortschritt).

## Verdrahtung

| Pin | Funktion |
|---|---|
| **D2** | Taster nach GND (interner Pull-up) – Start/Abbruch |
| **D11** | Reizausgang: 30 ms HIGH-Puls pro Reiz (Relais/Optokoppler zum Reizgerät) |
| D4 | reserviert (zweites Relais, wird nur auf LOW gehalten) |

## Trigger-Protokoll (zu ERPulse)

Pro Reiz eine Textzeile über USB-Serial, 115 200 Baud:

```
TRIGGER:<laufende Nummer ab 1>,<millis() des Arduino>
```

Alle anderen Zeilen (`[SEQ] …`, `[PULSE] …`, `[WiFi] …`) werden von ERPulse als Statusmeldung im
Trigger-Log angezeigt. Optional wird zusätzlich ein UDP-Paket `T<n>,<ms>` an `LAPTOP_IP:LAPTOP_PORT`
geschickt; die aktuelle ERPulse-Version wertet das **nicht** aus (Überbleibsel des früheren LSL-Aufbaus).

## Bauen und flashen

```bash
pip install platformio
cd firmware/trigger
cp include/secrets.example.h include/secrets.h   # optional, nur für WLAN/UDP
pio run -t upload
pio device monitor
```

Ohne `secrets.h` läuft die Firmware im reinen USB-Modus – für ERPulse reicht das.

## Anpassen

* **Pausenfolge:** Array `ISI[]` (Sekunden) in `src/main.cpp`.
* **Pulslänge:** `PULSE_US` (aktuell 30 ms).
* Pausen werden mit `millis()` gemessen, der Pulsausgang kommt unmittelbar *vor* der Trigger-Zeile –
  die Zeile erreicht den Rechner mit USB-Latenz, der Reiz selbst nicht.
