// Diagnostica Arduino UNO Q: Modulino Distance (Qwiic) + Seeed Grove Base Shield (4 periferiche)
// - Scansione I2C su Wire (header Grove/UNO) e Wire1 (connettore Qwiic)
// - Lettura Modulino Distance
// - Lettura grezza dei pin analogici A0-A5 e digitali D2-D8 (porte Grove)
#include <Wire.h>
#include <Arduino_Modulino.h>

ModulinoDistance distance;
bool distanceOk = false;

const uint8_t analogPins[] = {A0, A1, A2, A3, A4, A5};
const uint8_t digitalPins[] = {2, 3, 4, 5, 6, 7, 8};

void scanBus(TwoWire &bus, const char *name) {
  Serial.print("Scan I2C "); Serial.print(name); Serial.print(": ");
  uint8_t found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    bus.beginTransmission(addr);
    if (bus.endTransmission() == 0) {
      Serial.print("0x"); Serial.print(addr, HEX); Serial.print(' ');
      found++;
    }
  }
  if (!found) Serial.print("nessun dispositivo");
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println("=== UNO Q diagnostica ===");

  Wire.begin();
  Wire1.begin();
  scanBus(Wire, "Wire ");
  scanBus(Wire1, "Wire1");

  Modulino.begin();
  distanceOk = distance.begin();
  Serial.print("Modulino Distance: ");
  Serial.println(distanceOk ? "OK" : "NON TROVATO");

  for (uint8_t p : digitalPins) pinMode(p, INPUT);
}

void loop() {
  static uint32_t last = 0;
  if (millis() - last > 2000) {
    last = millis();
    scanBus(Wire, "Wire ");
    scanBus(Wire1, "Wire1");
    if (!distanceOk) { distanceOk = distance.begin(); }
  }
  if (distanceOk && distance.available()) {
    Serial.print("Distanza[mm]="); Serial.print(distance.get());
  } else {
    Serial.print("Distanza[mm]=n/d");
  }

  Serial.print(" | Analog:");
  for (uint8_t p : analogPins) { Serial.print(' '); Serial.print(analogRead(p)); }

  Serial.print(" | Digital D2-D8:");
  for (uint8_t p : digitalPins) { Serial.print(' '); Serial.print(digitalRead(p)); }
  Serial.println();
  delay(1000);
}

