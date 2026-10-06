// AirSense firmware: ESP32 + BME280 (temperature/humidity/pressure) + SGP30 (eCO2/TVOC)
// -> MQTT over TLS (mutual X.509) -> AWS IoT Core.
//
// Reliability features:
//  * readings are buffered in RAM while offline and removed only after the broker ACKs (QoS 1)
//  * Wi-Fi / MQTT reconnect with capped exponential backoff + jitter
//  * no reading is published without a valid NTP timestamp (TLS also needs correct time)
//  * hardware watchdog reboots the board if the loop hangs
//  * SGP30 humidity compensation + baseline persisted in flash across reboots
//  * publish interval and CO2 alert threshold can be changed remotely via the Device Shadow
#include <Adafruit_BME280.h>
#include <Adafruit_SGP30.h>
#include <ArduinoJson.h>
#include <MQTT.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_task_wdt.h>
#include <math.h>
#include <time.h>

#include "backoff.h"
#include "reading.h"
#include "ring_buffer.h"
#include "smoothing.h"
#include "secrets.h"

static const int LED_PIN = 2;                // on-board LED: lit while CO2 is above threshold
static const uint32_t WDT_TIMEOUT_S = 60;
static const size_t BUFFER_SIZE = 360;       // 1 hour of readings at 10 s
static const uint32_t BASELINE_SAVE_MS = 60UL * 60 * 1000;

static char TOPIC_TELEMETRY[96];
static char TOPIC_SHADOW_DELTA[128];
static char TOPIC_SHADOW_UPDATE[128];

WiFiClientSecure net;
MQTTClient mqtt(1024);
Adafruit_BME280 bme;
Adafruit_SGP30 sgp;
Preferences prefs;
RingBuffer<Reading, BUFFER_SIZE> pending;
Backoff wifiBackoff(1000, 60000), mqttBackoff(2000, 120000);
Ema co2Ema(0.3f), tvocEma(0.3f);

uint32_t publishIntervalMs = 10000;   // remotely configurable
uint16_t co2AlertPpm = 1200;          // remotely configurable
uint32_t seq = 0;
uint32_t lastSample = 0, nextWifiTry = 0, nextMqttTry = 0, lastBaselineSave = 0;
bool sgpOk = false, bmeOk = false;

static float rand01() { return (esp_random() % 10000) / 10000.0f; }

// Absolute humidity in mg/m^3, as the SGP30 needs for humidity compensation.
static uint32_t absoluteHumidity(float tempC, float rh) {
  float ah = 216.7f * ((rh / 100.0f) * 6.112f * expf((17.62f * tempC) / (243.12f + tempC)) / (273.15f + tempC));
  return (uint32_t)(1000.0f * ah);
}

static bool timeValid() { return time(nullptr) > 1700000000; }  // after Nov 2023

void reportShadow() {
  char buf[160];
  snprintf(buf, sizeof buf, "{\"state\":{\"reported\":{\"interval_s\":%lu,\"co2_alert_ppm\":%u,\"fw\":\"1.0.0\"}}}",
           (unsigned long)(publishIntervalMs / 1000), co2AlertPpm);
  mqtt.publish(TOPIC_SHADOW_UPDATE, buf, false, 1);
}

void onMessage(String& topic, String& payload) {
  if (topic != TOPIC_SHADOW_DELTA) return;
  JsonDocument doc;
  if (deserializeJson(doc, payload)) return;  // ignore malformed config
  JsonObject s = doc["state"];
  if (s["interval_s"].is<uint32_t>()) {
    uint32_t v = s["interval_s"];
    if (v >= 5 && v <= 3600) publishIntervalMs = v * 1000;  // reject unsafe values
  }
  if (s["co2_alert_ppm"].is<uint16_t>()) {
    uint16_t v = s["co2_alert_ppm"];
    if (v >= 600 && v <= 5000) co2AlertPpm = v;
  }
  prefs.putUInt("interval", publishIntervalMs);
  prefs.putUShort("co2alert", co2AlertPpm);
  reportShadow();
}

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    wifiBackoff.reset();
    return;
  }
  if (millis() < nextWifiTry) return;
  Serial.println("[wifi] connecting");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  nextWifiTry = millis() + wifiBackoff.next(rand01());
}

void ensureMqtt() {
  if (WiFi.status() != WL_CONNECTED || !timeValid()) return;
  if (mqtt.connected()) return;
  if (millis() < nextMqttTry) return;
  Serial.println("[mqtt] connecting");
  if (mqtt.connect(DEVICE_ID)) {
    mqttBackoff.reset();
    mqtt.subscribe(TOPIC_SHADOW_DELTA, 1);
    reportShadow();
    Serial.printf("[mqtt] connected, %u buffered readings to send\n", (unsigned)pending.size());
  } else {
    nextMqttTry = millis() + mqttBackoff.next(rand01());
    Serial.printf("[mqtt] failed (err %d), retry in %lus\n", mqtt.lastError(),
                  (unsigned long)((nextMqttTry - millis()) / 1000));
  }
}

bool sample(Reading& r) {
  if (!bmeOk || !timeValid()) return false;
  r.epoch_s = (uint32_t)time(nullptr);
  r.temp_c = bme.readTemperature();
  r.humidity_pct = bme.readHumidity();
  r.pressure_hpa = bme.readPressure() / 100.0f;
  r.co2_ppm = 400;
  r.tvoc_ppb = 0;
  if (sgpOk) {
    sgp.setHumidity(absoluteHumidity(r.temp_c, r.humidity_pct));
    if (sgp.IAQmeasure()) {
      r.co2_ppm = (uint16_t)lroundf(co2Ema.update(sgp.eCO2));
      r.tvoc_ppb = (uint16_t)lroundf(tvocEma.update(sgp.TVOC));
    }
  }
  return plausible(r);
}

// Sends buffered readings oldest-first; a reading is removed only after the broker ACKs it.
void flush() {
  char json[320];
  Reading r;
  int budget = 20;  // don't starve the loop / watchdog when catching up
  while (mqtt.connected() && budget-- > 0 && pending.peek(r)) {
    size_t n = to_json(r, DEVICE_ID, seq, json, sizeof json);
    // n == 0 means the reading can't be serialised; drop it rather than block the queue.
    if (n == 0 || mqtt.publish(TOPIC_TELEMETRY, json, (int)n, false, 1)) {
      pending.pop(r);
      ++seq;
    } else {
      break;  // not acknowledged: keep it and retry later
    }
  }
}

void saveSgpBaseline() {
  uint16_t eco2, tvoc;
  if (sgpOk && sgp.getIAQBaseline(&eco2, &tvoc)) {
    prefs.putUShort("bl_eco2", eco2);
    prefs.putUShort("bl_tvoc", tvoc);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  esp_task_wdt_init(WDT_TIMEOUT_S, true);
  esp_task_wdt_add(NULL);

  snprintf(TOPIC_TELEMETRY, sizeof TOPIC_TELEMETRY, "airsense/%s/telemetry", DEVICE_ID);
  snprintf(TOPIC_SHADOW_DELTA, sizeof TOPIC_SHADOW_DELTA, "$aws/things/%s/shadow/update/delta", DEVICE_ID);
  snprintf(TOPIC_SHADOW_UPDATE, sizeof TOPIC_SHADOW_UPDATE, "$aws/things/%s/shadow/update", DEVICE_ID);

  prefs.begin("airsense", false);
  publishIntervalMs = prefs.getUInt("interval", publishIntervalMs);
  co2AlertPpm = prefs.getUShort("co2alert", co2AlertPpm);

  bmeOk = bme.begin(0x76) || bme.begin(0x77);
  sgpOk = sgp.begin();
  Serial.printf("[sensors] BME280 %s, SGP30 %s\n", bmeOk ? "ok" : "MISSING", sgpOk ? "ok" : "MISSING");
  if (sgpOk && prefs.isKey("bl_eco2")) {
    sgp.setIAQBaseline(prefs.getUShort("bl_eco2"), prefs.getUShort("bl_tvoc"));
  }

  WiFi.mode(WIFI_STA);
  configTime(0, 0, "pool.ntp.org", "time.google.com");

  net.setCACert(AWS_ROOT_CA);
  net.setCertificate(DEVICE_CERT);
  net.setPrivateKey(DEVICE_PRIVATE_KEY);
  mqtt.begin(AWS_IOT_ENDPOINT, 8883, net);
  mqtt.setKeepAlive(60);
  mqtt.setTimeout(5000);  // wait up to 5 s for PUBACK
  mqtt.onMessage(onMessage);
}

void loop() {
  esp_task_wdt_reset();
  ensureWifi();
  ensureMqtt();
  mqtt.loop();

  if (millis() - lastSample >= publishIntervalMs) {
    lastSample = millis();
    Reading r;
    if (sample(r)) {
      if (!pending.push(r)) Serial.println("[buffer] full: dropped oldest reading");
      digitalWrite(LED_PIN, r.co2_ppm >= co2AlertPpm ? HIGH : LOW);
    }
  }
  flush();

  if (millis() - lastBaselineSave >= BASELINE_SAVE_MS) {
    lastBaselineSave = millis();
    saveSgpBaseline();
  }
  delay(10);
}
