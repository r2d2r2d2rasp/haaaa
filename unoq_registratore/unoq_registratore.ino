// Arduino UNO Q - registratore sensori con pulsante + display OLED a rotazione
//
//  Pulsante      : tra D2 e GND (INPUT_PULLUP, nessuna resistenza esterna necessaria)
//  OLED 0x3C     : SSD1306 128x64 su Wire (porta I2C Grove)
//  AHT20 0x38    : temperatura / umidita'
//  SGP30 0x58    : CO2eq / TVOC
//  Modulino Movement (Qwiic, Wire1): accelerometro + giroscopio
//  Grove Light   : A0
//
//  1a pressione  -> inizia sessione di registrazione (1 campione/s)
//  2a pressione  -> chiude la sessione e la salva
//  Salvataggio   : righe CSV inviate via Bridge al lato Linux (eMMC interna), vedi linux_logger/main.py.
//                  In piu' gli ultimi MAX_SAMPLES campioni restano in RAM e a fine sessione
//                  vengono stampati su seriale (115200) come copia di sicurezza.
#include <Wire.h>
#include <Arduino_Modulino.h>
#include <Arduino_RouterBridge.h>

// ---------------- configurazione ----------------
const uint8_t PIN_BUTTON = 2;            // pulsante verso GND
const uint8_t OLED_ADDR = 0x3C;
const uint32_t SAMPLE_MS = 1000;         // periodo di campionamento
const uint32_t PAGE_MS = 2500;           // tempo di permanenza su ogni pagina
const uint32_t TRANS_MS = 350;           // durata animazione di scorrimento
const uint16_t MAX_SAMPLES = 300;        // copia di sicurezza in RAM

// ---------------- font 5x7 (ASCII 32..90) ----------------
const uint8_t FONT[59][5] = {
  {0x00,0x00,0x00,0x00,0x00},{0x00,0x00,0x5F,0x00,0x00},{0x00,0x07,0x00,0x07,0x00},{0x14,0x7F,0x14,0x7F,0x14},
  {0x24,0x2A,0x7F,0x2A,0x12},{0x23,0x13,0x08,0x64,0x62},{0x36,0x49,0x56,0x20,0x50},{0x00,0x08,0x07,0x03,0x00},
  {0x00,0x1C,0x22,0x41,0x00},{0x00,0x41,0x22,0x1C,0x00},{0x2A,0x1C,0x7F,0x1C,0x2A},{0x08,0x08,0x3E,0x08,0x08},
  {0x00,0x80,0x70,0x30,0x00},{0x08,0x08,0x08,0x08,0x08},{0x00,0x00,0x60,0x60,0x00},{0x20,0x10,0x08,0x04,0x02},
  {0x3E,0x51,0x49,0x45,0x3E},{0x00,0x42,0x7F,0x40,0x00},{0x72,0x49,0x49,0x49,0x46},{0x21,0x41,0x49,0x4D,0x33},
  {0x18,0x14,0x12,0x7F,0x10},{0x27,0x45,0x45,0x45,0x39},{0x3C,0x4A,0x49,0x49,0x31},{0x41,0x21,0x11,0x09,0x07},
  {0x36,0x49,0x49,0x49,0x36},{0x46,0x49,0x49,0x29,0x1E},{0x00,0x00,0x14,0x00,0x00},{0x00,0x40,0x34,0x00,0x00},
  {0x00,0x08,0x14,0x22,0x41},{0x14,0x14,0x14,0x14,0x14},{0x00,0x41,0x22,0x14,0x08},{0x02,0x01,0x59,0x09,0x06},
  {0x3E,0x41,0x5D,0x59,0x4E},{0x7C,0x12,0x11,0x12,0x7C},{0x7F,0x49,0x49,0x49,0x36},{0x3E,0x41,0x41,0x41,0x22},
  {0x7F,0x41,0x41,0x41,0x3E},{0x7F,0x49,0x49,0x49,0x41},{0x7F,0x09,0x09,0x09,0x01},{0x3E,0x41,0x41,0x51,0x73},
  {0x7F,0x08,0x08,0x08,0x7F},{0x00,0x41,0x7F,0x41,0x00},{0x20,0x40,0x41,0x3F,0x01},{0x7F,0x08,0x14,0x22,0x41},
  {0x7F,0x40,0x40,0x40,0x40},{0x7F,0x02,0x1C,0x02,0x7F},{0x7F,0x04,0x08,0x10,0x7F},{0x3E,0x41,0x41,0x41,0x3E},
  {0x7F,0x09,0x09,0x09,0x06},{0x3E,0x41,0x51,0x21,0x5E},{0x7F,0x09,0x19,0x29,0x46},{0x26,0x49,0x49,0x49,0x32},
  {0x03,0x01,0x7F,0x01,0x03},{0x3F,0x40,0x40,0x40,0x3F},{0x1F,0x20,0x40,0x20,0x1F},{0x3F,0x40,0x38,0x40,0x3F},
  {0x63,0x14,0x08,0x14,0x63},{0x03,0x04,0x78,0x04,0x03},{0x61,0x59,0x49,0x4D,0x43}
};

// ---------------- display SSD1306 ----------------
uint8_t fb[128 * 8];  // framebuffer 128x64
bool oledOk = false;

void oledCmd(uint8_t c) {
  Wire.beginTransmission(OLED_ADDR);
  Wire.write(0x00); Wire.write(c);
  Wire.endTransmission();
}

bool oledInit() {
  Wire.beginTransmission(OLED_ADDR);
  if (Wire.endTransmission() != 0) return false;
  const uint8_t seq[] = {0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14, 0x20, 0x00,
                         0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF};
  for (uint8_t c : seq) oledCmd(c);
  return true;
}

void oledFlush() {
  oledCmd(0x21); oledCmd(0); oledCmd(127);
  oledCmd(0x22); oledCmd(0); oledCmd(7);
  for (uint16_t i = 0; i < sizeof(fb); i += 16) {
    Wire.beginTransmission(OLED_ADDR);
    Wire.write(0x40);
    for (uint8_t k = 0; k < 16; k++) Wire.write(fb[i + k]);
    Wire.endTransmission();
  }
}

inline void px(int x, int y, bool on = true) {
  if (x < 0 || x > 127 || y < 0 || y > 63) return;
  if (on) fb[(y >> 3) * 128 + x] |= (1 << (y & 7));
  else    fb[(y >> 3) * 128 + x] &= ~(1 << (y & 7));
}

void rect(int x, int y, int w, int h, bool fill = true) {
  for (int j = 0; j < h; j++)
    for (int i = 0; i < w; i++)
      if (fill || i == 0 || j == 0 || i == w - 1 || j == h - 1) px(x + i, y + j);
}

void chr(int x, int y, char c, uint8_t s) {
  if (c >= 'a' && c <= 'z') c -= 32;
  if (c < 32 || c > 90) c = '?';
  for (uint8_t col = 0; col < 5; col++) {
    uint8_t b = FONT[c - 32][col];
    for (uint8_t row = 0; row < 8; row++)
      if (b & (1 << row)) rect(x + col * s, y + row * s, s, s);
  }
}

int textW(const char *t, uint8_t s) {
  int n = strlen(t);
  return n ? n * 6 * s - s : 0;
}

void text(int x, int y, const char *t, uint8_t s) {
  for (; *t; t++, x += 6 * s) chr(x, y, *t, s);
}

void textC(int xoff, int y, const char *t, uint8_t s) {  // centrato nella pagina
  text(xoff + (128 - textW(t, s)) / 2, y, t, s);
}

// ---------------- sensori ----------------
ModulinoMovement movement;
bool movOk = false, ahtOk = false, sgpOk = false;

float temp = 0, hum = 0, ax = 0, ay = 0, az = 0, gx = 0, gy = 0, gz = 0;
uint16_t co2 = 400, tvoc = 0;
int luce = 0;

bool ahtInit() {
  delay(40);
  Wire.beginTransmission(0x38);
  Wire.write(0xBE); Wire.write(0x08); Wire.write(0x00);
  return Wire.endTransmission() == 0;
}

bool ahtRead() {
  Wire.beginTransmission(0x38);
  Wire.write(0xAC); Wire.write(0x33); Wire.write(0x00);
  if (Wire.endTransmission() != 0) return false;
  delay(80);
  if (Wire.requestFrom((uint8_t)0x38, (uint8_t)7) != 7) return false;
  uint8_t d[7];
  for (auto &b : d) b = Wire.read();
  if (d[0] & 0x80) return false;
  uint32_t rh = ((uint32_t)d[1] << 12) | ((uint32_t)d[2] << 4) | (d[3] >> 4);
  uint32_t tp = ((uint32_t)(d[3] & 0x0F) << 16) | ((uint32_t)d[4] << 8) | d[5];
  hum = rh * 100.0f / 1048576.0f;
  temp = tp * 200.0f / 1048576.0f - 50.0f;
  return true;
}

bool sgpInit() {
  Wire.beginTransmission(0x58);
  Wire.write(0x20); Wire.write(0x03);
  return Wire.endTransmission() == 0;
}

bool sgpRead() {
  Wire.beginTransmission(0x58);
  Wire.write(0x20); Wire.write(0x08);
  if (Wire.endTransmission() != 0) return false;
  delay(15);
  if (Wire.requestFrom((uint8_t)0x58, (uint8_t)6) != 6) return false;
  uint8_t d[6];
  for (auto &b : d) b = Wire.read();
  co2 = ((uint16_t)d[0] << 8) | d[1];
  tvoc = ((uint16_t)d[3] << 8) | d[4];
  return true;
}

void readSensors() {
  if (ahtOk) ahtRead();
  if (sgpOk) sgpRead();
  if (movOk && movement.update()) {
    ax = movement.getX(); ay = movement.getY(); az = movement.getZ();
    gx = movement.getRoll(); gy = movement.getPitch(); gz = movement.getYaw();
  }
  luce = analogRead(A0);
}

// ---------------- formattazione senza printf float ----------------
void fmtF(char *out, size_t n, float v, uint8_t dec, bool plus = false) {
  int32_t mul = (dec == 2) ? 100 : 10;
  int32_t x = (int32_t)(v * mul + (v < 0 ? -0.5f : 0.5f));
  bool neg = x < 0;
  if (neg) x = -x;
  const char *sg = neg ? "-" : (plus ? "+" : "");
  if (dec == 2) snprintf(out, n, "%s%ld.%02ld", sg, (long)(x / 100), (long)(x % 100));
  else          snprintf(out, n, "%s%ld.%ld", sg, (long)(x / 10), (long)(x % 10));
}

// ---------------- sessione di registrazione ----------------
struct Sample { uint32_t ms; int16_t t10, h10; uint16_t co2, tvoc; int16_t ax100, ay100, az100, gx10, gy10, gz10; uint16_t luce; };
Sample ram[MAX_SAMPLES];
uint16_t ramCount = 0, ramHead = 0;
bool recording = false;
uint32_t sessionStart = 0, sessionNo = 0, sessionSamples = 0;

void recStart() {
  recording = true;
  sessionNo++;
  sessionStart = millis();
  sessionSamples = 0;
  ramCount = ramHead = 0;
  Bridge.notify("log_start", (int)sessionNo);
  Serial.print("# SESSIONE "); Serial.print(sessionNo); Serial.println(" AVVIATA");
}

void recSample() {
  Sample s{millis() - sessionStart, (int16_t)(temp * 10), (int16_t)(hum * 10), co2, tvoc,
           (int16_t)(ax * 100), (int16_t)(ay * 100), (int16_t)(az * 100),
           (int16_t)(gx * 10), (int16_t)(gy * 10), (int16_t)(gz * 10), (uint16_t)luce};
  ram[ramHead] = s;
  ramHead = (ramHead + 1) % MAX_SAMPLES;
  if (ramCount < MAX_SAMPLES) ramCount++;
  sessionSamples++;

  char line[120];
  snprintf(line, sizeof(line), "%lu,%d,%d,%u,%u,%d,%d,%d,%d,%d,%d,%u",
           (unsigned long)s.ms, s.t10, s.h10, s.co2, s.tvoc, s.ax100, s.ay100, s.az100,
           s.gx10, s.gy10, s.gz10, s.luce);
  Bridge.notify("log_line", String(line));
}

void recStop() {
  recording = false;
  Bridge.notify("log_stop", (int)sessionSamples);
  Serial.print("# SESSIONE "); Serial.print(sessionNo); Serial.print(" CHIUSA, campioni: ");
  Serial.println(sessionSamples);
  Serial.println("# copia RAM (t10/h10 = decimi, acc = centesimi di g, gyro = decimi di dps)");
  Serial.println("ms,t10,h10,co2,tvoc,ax100,ay100,az100,gx10,gy10,gz10,luce");
  uint16_t start = (ramCount < MAX_SAMPLES) ? 0 : ramHead;
  for (uint16_t i = 0; i < ramCount; i++) {
    const Sample &s = ram[(start + i) % MAX_SAMPLES];
    Serial.print(s.ms); Serial.print(','); Serial.print(s.t10); Serial.print(','); Serial.print(s.h10); Serial.print(',');
    Serial.print(s.co2); Serial.print(','); Serial.print(s.tvoc); Serial.print(','); Serial.print(s.ax100); Serial.print(',');
    Serial.print(s.ay100); Serial.print(','); Serial.print(s.az100); Serial.print(','); Serial.print(s.gx10); Serial.print(',');
    Serial.print(s.gy10); Serial.print(','); Serial.print(s.gz10); Serial.print(','); Serial.println(s.luce);
  }
  Serial.println("# FINE");
}

// ---------------- pagine del display ----------------
const uint8_t NPAGES = 8;

void pageValue(int xo, const char *title, const char *val, const char *unit) {
  text(xo + 2, 2, title, 1);
  textC(xo, 20, val, 3);
  textC(xo, 46, unit, 1);
}

void pageAxes(int xo, const char *title, float a, float b, float c, uint8_t dec, const char *u) {
  char buf[16], line[24];
  text(xo + 2, 2, title, 1);
  const char *lab[3] = {"X ", "Y ", "Z "};
  float v[3] = {a, b, c};
  for (int i = 0; i < 3; i++) {
    fmtF(buf, sizeof(buf), v[i], dec, true);
    snprintf(line, sizeof(line), "%s%s", lab[i], buf);
    text(xo + 6, 15 + i * 15, line, 2);
  }
  text(xo + 100, 52, u, 1);
}

void drawPage(uint8_t p, int xo, uint32_t now) {
  char b[20];
  switch (p) {
    case 0: fmtF(b, sizeof(b), temp, 1); pageValue(xo, "TEMPERATURA", b, "GRADI C"); break;
    case 1: fmtF(b, sizeof(b), hum, 1);  pageValue(xo, "UMIDITA", b, "% RH"); break;
    case 2: snprintf(b, sizeof(b), "%u", co2);  pageValue(xo, "CO2 EQ", b, "PPM"); break;
    case 3: snprintf(b, sizeof(b), "%u", tvoc); pageValue(xo, "TVOC", b, "PPB"); break;
    case 4: pageAxes(xo, "ACCELERAZIONE", ax, ay, az, 2, "G"); break;
    case 5: pageAxes(xo, "GIROSCOPIO", gx, gy, gz, 1, "DPS"); break;
    case 6: {
      int pct = luce * 100 / 1023;
      snprintf(b, sizeof(b), "%d%%", pct);
      text(xo + 2, 2, "LUCE", 1);
      textC(xo, 16, b, 3);
      rect(xo + 14, 44, 100, 8, false);
      rect(xo + 14, 44, pct, 8, true);
      break;
    }
    case 7: {
      text(xo + 2, 2, "SESSIONE", 1);
      textC(xo, 16, recording ? "REC" : "STOP", 3);
      snprintf(b, sizeof(b), "N %lu  CAMP %lu", (unsigned long)sessionNo, (unsigned long)sessionSamples);
      textC(xo, 46, b, 1);
      break;
    }
  }
}

// elementi fissi: indicatore REC lampeggiante, tempo sessione, puntini di pagina
void drawOverlay(uint8_t page, uint32_t now) {
  if (recording) {
    uint32_t s = (now - sessionStart) / 1000;
    char t[8];
    snprintf(t, sizeof(t), "%02lu:%02lu", (unsigned long)(s / 60 % 100), (unsigned long)(s % 60));
    text(84, 2, t, 1);
    if ((now / 500) % 2 == 0) {  // pallino pieno lampeggiante
      for (int j = -3; j <= 3; j++)
        for (int i = -3; i <= 3; i++)
          if (i * i + j * j <= 9) px(121 + i, 5 + j);
    } else {
      for (int j = -3; j <= 3; j++)
        for (int i = -3; i <= 3; i++)
          if (i * i + j * j <= 9 && i * i + j * j >= 5) px(121 + i, 5 + j);
    }
  }
  for (uint8_t i = 0; i < NPAGES; i++) {
    int x = 64 - NPAGES * 5 + i * 10 + 3;
    if (i == page) rect(x - 1, 60, 4, 3); else px(x, 61);
  }
}

// ---------------- stato principale ----------------
uint8_t page = 0, prevPage = 0;
uint32_t pageSince = 0, transStart = 0, lastSample = 0, lastFrame = 0;
bool transitioning = false;

bool btnPrev = HIGH;
uint32_t btnChange = 0;

bool buttonPressed(uint32_t now) {  // fronte di discesa con antirimbalzo
  bool v = digitalRead(PIN_BUTTON);
  if (v != btnPrev && now - btnChange > 40) {
    btnChange = now;
    btnPrev = v;
    if (v == LOW) return true;
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  Wire.begin();
  Wire.setClock(400000);
  Wire1.begin();
  Modulino.begin();
  Bridge.begin();

  movOk = movement.begin();
  ahtOk = ahtInit();
  sgpOk = sgpInit();
  oledOk = oledInit();

  Serial.println("=== UNO Q registratore ===");
  Serial.print("Movement "); Serial.print(movOk); Serial.print(" AHT20 "); Serial.print(ahtOk);
  Serial.print(" SGP30 "); Serial.print(sgpOk); Serial.print(" OLED "); Serial.println(oledOk);

  readSensors();
  pageSince = millis();
}

void loop() {
  uint32_t now = millis();

  if (buttonPressed(now)) {
    if (recording) recStop(); else recStart();
    prevPage = page; page = 7;               // mostra subito la pagina sessione
    transitioning = true; transStart = now; pageSince = now;
  }

  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now;
    readSensors();
    if (recording) recSample();
  }

  if (!transitioning && now - pageSince >= PAGE_MS) {
    prevPage = page;
    page = (page + 1) % NPAGES;
    transitioning = true; transStart = now; pageSince = now;
  }

  if (!oledOk) return;
  if (transitioning || now - lastFrame >= 250) {
    lastFrame = now;
    memset(fb, 0, sizeof(fb));
    if (transitioning) {
      uint32_t el = now - transStart;
      if (el >= TRANS_MS) { transitioning = false; drawPage(page, 0, now); }
      else {
        float t = (float)el / TRANS_MS;
        t = 1 - (1 - t) * (1 - t);           // easing out
        int off = (int)(t * 128);
        drawPage(prevPage, -off, now);       // la pagina vecchia esce a sinistra
        drawPage(page, 128 - off, now);      // la nuova entra da destra
      }
    } else {
      drawPage(page, 0, now);
    }
    drawOverlay(page, now);
    oledFlush();
  }
}
