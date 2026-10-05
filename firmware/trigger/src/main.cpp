#include <WiFiS3.h>
#include <WiFiUdp.h>
#include <Arduino_LED_Matrix.h>

// ══ KONFIGURATION ═════════════════════════════════════════════════════════════
// WLAN-Zugang liegt NICHT im Repo: include/secrets.example.h nach
// include/secrets.h kopieren und anpassen. Ohne secrets.h läuft die Firmware
// im reinen USB-Modus (der Trigger geht dann nur über die serielle Leitung).
#if __has_include("secrets.h")
  #include "secrets.h"
#else
  #define WIFI_SSID     ""
  #define WIFI_PASS     ""
  #define LAPTOP_IP     "0.0.0.0"
  #define LAPTOP_PORT   9999
#endif
#define LOCAL_UDP_PORT  2390

#define PIN_BTN     2
#define PIN_RELAY   11
#define PIN_RELAY2  4
// ══════════════════════════════════════════════════════════════════════════════

static const uint32_t PULSE_US    = 30000UL;
static const uint32_t DEBOUNCE_MS =    50UL;
static const uint32_t FLASH_MS    =   150UL;
static const unsigned long COUNTDOWN_MS = 3000UL;

static const int ISI[] = {
    6,7,4,7,6,3,4,5,7,7,4,7,7,5,6,4,5,7,6,7,6,3,6,7,
    6,6,6,5,6,4,6,3,6,7,4,7,6,3,4,5,7,6,7,6,3,6,7,4,
    7,7,5,6,4,5,7,6,7,6,3,6,7,4,7,7,5,6,4,5,7,6,7,6,3,6
};
static const int N_STIM = (int)(sizeof(ISI) / sizeof(ISI[0]));

// ── LED Frames ────────────────────────────────────────────────────────────────
static byte FRM_DISC[8][12] = {
    {0,0,0,0,0,0,0,0,0,0,0,0},
    {0,1,0,0,0,0,0,0,0,0,1,0},
    {0,0,1,0,0,0,0,0,0,1,0,0},
    {0,0,0,1,0,0,0,0,1,0,0,0},
    {0,0,0,0,1,0,0,1,0,0,0,0},
    {0,0,0,1,0,0,0,0,1,0,0,0},
    {0,0,1,0,0,0,0,0,0,1,0,0},
    {0,1,0,0,0,0,0,0,0,0,1,0},
};
static byte FRM_CONN[8][12] = {
    {0,0,0,0,1,1,1,1,0,0,0,0},
    {0,0,1,1,0,0,0,0,1,1,0,0},
    {0,1,0,0,0,0,0,0,0,0,1,0},
    {0,0,0,1,1,0,0,1,1,0,0,0},
    {0,0,0,0,0,1,1,0,0,0,0,0},
    {0,0,0,0,0,0,0,0,0,0,0,0},
    {0,0,0,0,0,1,1,0,0,0,0,0},
    {0,0,0,0,0,0,0,0,0,0,0,0},
};
static byte FRM_TICK[8][12] = {
    {0,0,0,0,0,0,0,0,0,0,0,0},
    {0,0,0,0,0,0,0,0,0,0,0,1},
    {0,0,0,0,0,0,0,0,0,0,1,0},
    {0,0,0,0,0,0,0,0,0,1,0,0},
    {0,1,0,0,0,0,0,0,1,0,0,0},
    {0,0,1,0,0,0,0,1,0,0,0,0},
    {0,0,0,1,0,0,1,0,0,0,0,0},
    {0,0,0,0,1,1,0,0,0,0,0,0},
};
static byte FRM_FLASH[8][12] = {
    {1,1,1,1,1,1,1,1,1,1,1,1},{1,1,1,1,1,1,1,1,1,1,1,1},
    {1,1,1,1,1,1,1,1,1,1,1,1},{1,1,1,1,1,1,1,1,1,1,1,1},
    {1,1,1,1,1,1,1,1,1,1,1,1},{1,1,1,1,1,1,1,1,1,1,1,1},
    {1,1,1,1,1,1,1,1,1,1,1,1},{1,1,1,1,1,1,1,1,1,1,1,1},
};
static byte FRM_BLANK[8][12] = {};
static byte FRM_HEART1[8][12] = {
    {0,0,1,1,0,0,0,1,1,0,0,0},
    {0,1,1,1,1,0,1,1,1,1,0,0},
    {0,1,1,1,1,1,1,1,1,1,0,0},
    {0,0,1,1,1,1,1,1,1,0,0,0},
    {0,0,0,1,1,1,1,1,0,0,0,0},
    {0,0,0,0,1,1,1,0,0,0,0,0},
    {0,0,0,0,0,1,0,0,0,0,0,0},
    {0,0,0,0,0,0,0,0,0,0,0,0},
};
static byte FRM_HEART2[8][12] = {
    {0,0,0,0,0,0,0,0,0,0,0,0},
    {0,0,1,1,0,0,0,1,1,0,0,0},
    {0,0,1,1,1,0,1,1,1,0,0,0},
    {0,0,0,1,1,1,1,1,0,0,0,0},
    {0,0,0,0,1,1,1,0,0,0,0,0},
    {0,0,0,0,0,1,0,0,0,0,0,0},
    {0,0,0,0,0,0,0,0,0,0,0,0},
    {0,0,0,0,0,0,0,0,0,0,0,0},
};
static byte FRM_EXCL[8][12] = {
    {0,0,0,0,0,1,1,0,0,0,0,0},
    {0,0,0,0,0,1,1,0,0,0,0,0},
    {0,0,0,0,0,1,1,0,0,0,0,0},
    {0,0,0,0,0,1,1,0,0,0,0,0},
    {0,0,0,0,0,1,1,0,0,0,0,0},
    {0,0,0,0,0,0,0,0,0,0,0,0},
    {0,0,0,0,0,1,1,0,0,0,0,0},
    {0,0,0,0,0,1,1,0,0,0,0,0},
};

// ── Globale Objekte ───────────────────────────────────────────────────────────
ArduinoLEDMatrix matrix;
WiFiUDP          udp;

bool wifiOK     = false;
bool seqRunning = false;
int  stimIdx    = 0;

volatile bool btnISR    = false;
bool          btnEvent  = false;
bool          btnLast   = HIGH;
unsigned long btnLastMs = 0;
unsigned long animMs    = 0;
int           animPhase = 0;

// ── ISR ───────────────────────────────────────────────────────────────────────
void BUTTON_ISR() {
    btnISR = true;
}

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────
void showFrame(byte frame[8][12]) {
    frame[0][11] = wifiOK ? 1 : 0;
    matrix.renderBitmap(frame, 8, 12);
}

void serialPrintf(const char* fmt, ...) {
    char buf[128];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);
    Serial.print(buf);
}

void checkButton() {
    bool state = digitalRead(PIN_BTN);
    unsigned long now = millis();
    if (state != btnLast && (now - btnLastMs) > DEBOUNCE_MS) {
        btnLastMs = now;
        btnLast   = state;
        if (state == LOW) btnEvent = true;
    }
}

// ── Start-Animation: Welle von links nach rechts ──────────────────────────────
void playStartAnim() {
    for (int pass = 0; pass < 2; pass++) {
        for (int col = 0; col < 12; col++) {
            byte f[8][12] = {};
            for (int r = 0; r < 8; r++) f[r][col] = 1;
            showFrame(f);
            delay(40);
        }
    }
    // Checkmark kurz zeigen
    showFrame(FRM_TICK);
    delay(600);
}

// ── Stop-Animation: Alle LEDs aus, Reihe für Reihe ───────────────────────────
void playStopAnim() {
    // Erst alle an
    showFrame(FRM_FLASH);
    delay(200);
    // Dann Zeile für Zeile löschen
    byte f[8][12] = {
        {1,1,1,1,1,1,1,1,1,1,1,1},{1,1,1,1,1,1,1,1,1,1,1,1},
        {1,1,1,1,1,1,1,1,1,1,1,1},{1,1,1,1,1,1,1,1,1,1,1,1},
        {1,1,1,1,1,1,1,1,1,1,1,1},{1,1,1,1,1,1,1,1,1,1,1,1},
        {1,1,1,1,1,1,1,1,1,1,1,1},{1,1,1,1,1,1,1,1,1,1,1,1},
    };
    for (int r = 0; r < 8; r++) {
        for (int c = 0; c < 12; c++) f[r][c] = 0;
        showFrame(f);
        delay(60);
    }
    delay(200);
    showFrame(wifiOK ? FRM_CONN : FRM_DISC);
}

// ── ISI Warte-Funktion mit Animationen ───────────────────────────────────────
// Gibt true zurück wenn Sequenz abgebrochen wurde
bool waitISI(int sIdx) {
    unsigned long waitMs = (unsigned long)ISI[sIdx] * 1000UL;
    unsigned long t0     = millis();

    while (true) {
        unsigned long elapsed   = millis() - t0;
        unsigned long remaining = (elapsed < waitMs) ? (waitMs - elapsed) : 0;
        if (elapsed >= waitMs) break;

        if (remaining <= COUNTDOWN_MS) {
            // ── Countdown: blinkendes ! + Rahmen füllt sich ────────────────
            byte pb[8][12] = {};
            if ((millis() % 500) < 250) memcpy(pb, FRM_EXCL, sizeof(pb));

            int steps = (int)((COUNTDOWN_MS - remaining) * 12 / COUNTDOWN_MS);
            steps = constrain(steps, 0, 11);
            for (int c = 0; c <= steps && c < 12; c++)      pb[0][c] = 1;
            for (int c = 11; c >= (11 - steps) && c >= 0; c--) pb[7][c] = 1;
            showFrame(pb);

        } else {
            // ── Herzschlag + Fortschritt ───────────────────────────────────
            byte pb[8][12] = {};
            uint32_t phase = elapsed % 1200;
            if      (phase < 100) memcpy(pb, FRM_HEART1, sizeof(pb));
            else if (phase < 200) memcpy(pb, FRM_HEART2, sizeof(pb));
            else if (phase < 300) memcpy(pb, FRM_HEART1, sizeof(pb));

            // Untere Zeile: Gesamt-Fortschritt der Sequenz
            int filled = sIdx * 12 / N_STIM;
            for (int c = 0; c < filled && c < 12; c++) pb[7][c] = 1;

            // Obere Zeile: Zeitfortschritt innerhalb dieses ISI
            int dot = constrain((int)(elapsed * 11 / waitMs), 0, 11);
            pb[0][dot] = 1;

            showFrame(pb);
        }

        // Button-Check → Abbruch
        if (btnISR) { btnISR = false; btnEvent = true; }
        checkButton();
        if (btnEvent) {
            btnEvent   = false;
            seqRunning = false;
            playStopAnim();
            Serial.println("[SEQ] Abgebrochen durch Button.");
            return true;
        }

        delay(30);
    }
    return false;
}

// ── WiFi ──────────────────────────────────────────────────────────────────────
void wifiTryConnect() {
    if (WiFi.status() == WL_NO_MODULE) return;
    if (WIFI_SSID[0] == '\0') { Serial.println("[WiFi] Keine secrets.h - USB-Only"); return; }
    serialPrintf("[WiFi] Versuche '%s' ...\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    unsigned long start = millis();
    while (millis() - start < 5000) {
        if (WiFi.status() == WL_CONNECTED) {
            wifiOK = true;
            udp.begin(LOCAL_UDP_PORT);
            char ip[20];
            WiFi.localIP().toString().toCharArray(ip, sizeof(ip));
            serialPrintf("[WiFi] Verbunden  IP=%s\n", ip);
            return;
        }
        delay(100);
    }
    WiFi.disconnect();
    serialPrintf("[WiFi] Timeout (Status=%d) - USB-Only\n", WiFi.status());
}

void wifiReconnectCheck() {
    static unsigned long last = 0;
    if (millis() - last < 30000) return;
    last = millis();
    if (!seqRunning && WiFi.status() != WL_CONNECTED) {
        wifiOK = false;
        wifiTryConnect();
    }
}

// ── Trigger senden ────────────────────────────────────────────────────────────
void firePulse(int idx) {
    serialPrintf("[PULSE] #%02d  t=%lu ms\n", idx + 1, millis());
    digitalWrite(PIN_RELAY, HIGH);
    delayMicroseconds(PULSE_US);
    digitalWrite(PIN_RELAY, LOW);
}

void sendTrigger(int idx) {
    serialPrintf("TRIGGER:%d,%lu\n", idx + 1, millis());
    if (wifiOK) {
        IPAddress ip; ip.fromString(LAPTOP_IP);
        char msg[32];
        snprintf(msg, sizeof(msg), "T%d,%lu", idx + 1, millis());
        udp.beginPacket(ip, LAPTOP_PORT);
        udp.write((const uint8_t*)msg, strlen(msg));
        udp.endPacket();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);
    matrix.begin();
    showFrame(FRM_DISC);

    pinMode(PIN_RELAY,  OUTPUT); digitalWrite(PIN_RELAY,  LOW);
    pinMode(PIN_RELAY2, OUTPUT); digitalWrite(PIN_RELAY2, LOW);
    pinMode(PIN_BTN,    INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_BTN), BUTTON_ISR, FALLING);

    Serial.println("\n[BOOT] Unicorn Trigger - UNO R4 WiFi");
    serialPrintf("[BOOT] %s | N_STIM=%d | BTN=D%d | RELAY=D%d\n",
                 __DATE__, N_STIM, PIN_BTN, PIN_RELAY);
    Serial.println("[BOOT] Druecke Button zum Starten / nochmal zum Abbrechen");

    wifiTryConnect();
    showFrame(wifiOK ? FRM_CONN : FRM_DISC);
}

// ─────────────────────────────────────────────────────────────────────────────
void loop() {
    wifiReconnectCheck();

    if (btnISR) { btnISR = false; btnEvent = true; }
    checkButton();

    // ── IDLE: wartet auf ersten Button-Druck ─────────────────────────────────
    if (!seqRunning) {
        // X blinkt wenn kein WiFi, WiFi-Icon wenn verbunden
        if (wifiOK) {
            showFrame(FRM_CONN);
        } else {
            unsigned long now = millis();
            if (now - animMs > 500) {
                animMs = now;
                animPhase ^= 1;
                if (animPhase) showFrame(FRM_DISC);
                else           showFrame(FRM_BLANK);
            }
        }

        if (btnEvent) {
            btnEvent = false;
            // Start-Animation abspielen
            playStartAnim();
            seqRunning = true;
            stimIdx    = 0;
            int total = 0;
            for (int i = 0; i < N_STIM; i++) total += ISI[i];
            serialPrintf("[SEQ] START - %d Stimuli, ~%d s\n", N_STIM, total);
            if (!wifiOK) Serial.println("[SEQ] USB-Only Modus");
        }
        return;
    }

    // ── SEQUENZ ABGESCHLOSSEN ─────────────────────────────────────────────────
    if (stimIdx >= N_STIM) {
        seqRunning = false;
        playStopAnim();
        Serial.println("[SEQ] Sequenz abgeschlossen.");
        return;
    }

    // ── NÄCHSTER STIMULUS ─────────────────────────────────────────────────────
    serialPrintf("[SEQ] Stimulus %02d/%02d  ISI=%ds\n",
                 stimIdx + 1, N_STIM, ISI[stimIdx]);

    if (waitISI(stimIdx)) return;   // true = abgebrochen

    // ── TRIGGER ───────────────────────────────────────────────────────────────
    firePulse(stimIdx);
    sendTrigger(stimIdx);

    showFrame(FRM_FLASH);
    delay(FLASH_MS);

    stimIdx++;
}
