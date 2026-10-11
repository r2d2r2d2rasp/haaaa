// Arduino UNO Q - lettura sensori e stampa su seriale (115200 baud)
//  Qwiic (Wire1) : Modulino Movement (IMU LSM6DSOX, 0x6A)
//  Grove (Wire)  : 0x38 AHT20 temperatura/umidita'  (identificato dall'indirizzo)
//                  0x58 SGP30 CO2eq/TVOC            (identificato dall'indirizzo)
//                  0x3C display OLED                (non pilotato in questo sketch)
//  A0            : Grove Light Sensor (analogico)
#include <Wire.h>
#include <Arduino_Modulino.h>

ModulinoMovement movement;
bool movOk = false, ahtOk = false, sgpOk = false;

// ---- AHT20 ----
bool ahtInit() {
  delay(40);
  Wire.beginTransmission(0x38);
  Wire.write(0xBE); Wire.write(0x08); Wire.write(0x00);
  if (Wire.endTransmission() != 0) return false;
  delay(10);
  return true;
}

bool ahtRead(float &t, float &h) {
  Wire.beginTransmission(0x38);
  Wire.write(0xAC); Wire.write(0x33); Wire.write(0x00);
  if (Wire.endTransmission() != 0) return false;
  delay(80);
  if (Wire.requestFrom((uint8_t)0x38, (uint8_t)7) != 7) return false;
  uint8_t d[7];
  for (auto &b : d) b = Wire.read();
  if (d[0] & 0x80) return false;  // ancora occupato
  uint32_t rh = ((uint32_t)d[1] << 12) | ((uint32_t)d[2] << 4) | (d[3] >> 4);
  uint32_t tp = ((uint32_t)(d[3] & 0x0F) << 16) | ((uint32_t)d[4] << 8) | d[5];
  h = rh * 100.0f / 1048576.0f;
  t = tp * 200.0f / 1048576.0f - 50.0f;
  return true;
}

// ---- SGP30 ----
bool sgpInit() {
  Wire.beginTransmission(0x58);
  Wire.write(0x20); Wire.write(0x03);  // init_air_quality
  return Wire.endTransmission() == 0;
}

bool sgpRead(uint16_t &co2, uint16_t &tvoc) {
  Wire.beginTransmission(0x58);
  Wire.write(0x20); Wire.write(0x08);  // measure_air_quality
  if (Wire.endTransmission() != 0) return false;
  delay(15);
  if (Wire.requestFrom((uint8_t)0x58, (uint8_t)6) != 6) return false;
  uint8_t d[6];
  for (auto &b : d) b = Wire.read();
  co2  = ((uint16_t)d[0] << 8) | d[1];
  tvoc = ((uint16_t)d[3] << 8) | d[4];
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Wire.begin();
  Wire1.begin();
  Modulino.begin();

  movOk = movement.begin();
  ahtOk = ahtInit();
  sgpOk = sgpInit();

  Serial.println("=== UNO Q sensori ===");
  Serial.print("Movement: "); Serial.println(movOk ? "OK" : "NON TROVATO");
  Serial.print("AHT20 0x38: "); Serial.println(ahtOk ? "OK" : "NON TROVATO");
  Serial.print("SGP30 0x58: "); Serial.println(sgpOk ? "OK" : "NON TROVATO");
}

void loop() {
  // SGP30 va interrogato ogni 1 s; nei primi ~15 s restituisce 400 ppm / 0 ppb
  uint16_t co2 = 0, tvoc = 0;
  float t = 0, h = 0;
  bool s = sgpOk && sgpRead(co2, tvoc);
  bool a = ahtOk && ahtRead(t, h);

  Serial.println("----------------------------------------");
  if (a) { Serial.print("Temp: "); Serial.print(t, 1); Serial.print(" C   Umidita': "); Serial.print(h, 1); Serial.println(" %"); }
  else   Serial.println("Temp/Umidita': n/d");

  if (s) { Serial.print("CO2eq: "); Serial.print(co2); Serial.print(" ppm   TVOC: "); Serial.print(tvoc); Serial.println(" ppb"); }
  else   Serial.println("CO2/TVOC: n/d");

  if (movOk && movement.update()) {
    Serial.print("Accel g  X:"); Serial.print(movement.getX(), 2);
    Serial.print(" Y:"); Serial.print(movement.getY(), 2);
    Serial.print(" Z:"); Serial.println(movement.getZ(), 2);
    Serial.print("Gyro dps R:"); Serial.print(movement.getRoll(), 1);
    Serial.print(" P:"); Serial.print(movement.getPitch(), 1);
    Serial.print(" Y:"); Serial.println(movement.getYaw(), 1);
  } else {
    Serial.println("Movement: n/d");
  }

  // Grove Light Sensor (fotoresistenza): piu' luce = valore piu' alto
  int luce = analogRead(A0);
  float rK = luce > 0 ? (1023.0f - luce) * 10.0f / luce : 9999.0f;  // resistenza LDR in kOhm (formula Seeed)
  Serial.print("Luce A0: "); Serial.print(luce);
  Serial.print(" (");  Serial.print(luce * 100.0f / 1023.0f, 0);
  Serial.print(" %)  R_LDR: "); Serial.print(rK, 1); Serial.println(" kOhm");
  delay(1000);
}
