#include <WiFi.h>
#include <Wire.h>
#include <PubSubClient.h>
#include <SparkFunTMP102.h>
#include <ArduinoJson.h>
#include <time.h>
#include <WiFiClientSecure.h>
#include "secure.h"
// --- Konfiguracja sieci i MQTT ---
const char* WIFI_SSID = "MojaSiecWifi";
const char* WIFI_PASSWORD = "raspberry";
const char* MQTT_HOST = "10.16.232.162";
const uint16_t MQTT_PORT = 8883;
const char* MQTT_CLIENT_ID = "ESP32_Klient_Testowy";
const char* MQTT_CMD_TOPIC = "rpi/komendy";

// --- Węzeł ---
const char* NODE_ID = "esp32-01";
const char* DATA_TOPIC = "weather/esp32-01/data";
// --- Sprzęt ---
const int ALERT_PIN = A3;
const unsigned long PUBLISH_INTERVAL_MS = 2000;

//TMP102 sensor0;
WiFiClientSecure espClient;
PubSubClient client(espClient);

unsigned long lastPublish = 0;
bool ntpSynced = false;

void printTLSError() {
  char errBuf[256];
  int err = espClient.lastError(errBuf, sizeof(errBuf));
  if (err != 0) {
    Serial.printf("[TLS] Blad %d: %s\n", err, errBuf);
  }
}
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  Serial.print("MQTT RX [");
  Serial.print(topic);
  Serial.print("]: ");
  for (unsigned int i = 0; i < length; i++) {
    Serial.print((char)payload[i]);
  }
  Serial.println();
}
void setupWifi() {
  Serial.print("Łączenie z siecią: ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.println("WiFi połączone!");
  Serial.print("Adres IP ESP32: ");
  Serial.println(WiFi.localIP());
}
void setupNtp() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  struct tm timeinfo;
  for (int i = 0; i < 20; i++) {
    if (getLocalTime(&timeinfo)) {
      ntpSynced = true;
      Serial.println("Czas zsynchronizowany (NTP).");
      return;
    }
    delay(500);
  }
  Serial.println("NTP niedostępny — timestamp zostanie pominięty.");
}
bool getIsoTimestamp(char* buffer, size_t bufferSize) {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    return false;
  }
  strftime(buffer, bufferSize, "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
  return true;
}
void reconnectMqtt() {
  while (!client.connected()) {
    Serial.print("Próba połączenia MQTT... ");
    if (client.connect(MQTT_CLIENT_ID,MQTT_USER,
            MQTT_PASSWORD)) {
      Serial.println("połączono!");
      client.subscribe(MQTT_CMD_TOPIC);
    } else {
      Serial.print("błąd, rc=");
      Serial.println(client.state());
      printTLSError();
      delay(5000);
    }
  }
}
void setup() {
  Serial.begin(115200);
  Wire.begin();
  pinMode(ALERT_PIN, INPUT);
  
  setupWifi();
  espClient.setCACert(CA_CERT);

  setupNtp();
  client.setServer(MQTT_HOST, MQTT_PORT);
  client.setCallback(mqttCallback);
  client.setBufferSize(512);
  // if (!sensor0.begin()) {
  //   Serial.println("Błąd: brak połączenia z TMP102.");
  //   Serial.println("Sprawdź okablowanie I2C i adres urządzenia.");
  //   while (true) {
  //     delay(1000);
  //   }
  // }
  // Serial.println("TMP102 gotowy.");
  // sensor0.setConversionRate(2);
  delay(100);
}
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Utracono WiFi — ponowne łączenie...");
    setupWifi();
    if (!ntpSynced) {
      setupNtp();
    }
  }
  if (!client.connected()) {
    reconnectMqtt();
  }
  client.loop();
  // sensor0.wakeup();
  // float temperatureC = sensor0.readTempC();
  // float temperatureF = sensor0.readTempF();
  // sensor0.sleep();
  float temperatureC = 21.37f;
  float temperatureF = 69.67f;
  bool alertPinState = (digitalRead(ALERT_PIN) == LOW);
  Serial.print("Temperatura: ");
  Serial.print(temperatureF);
  Serial.print(" °F / ");
  Serial.print(temperatureC);
  Serial.print(" °C");
  Serial.print(" | alert pin: ");
  Serial.println(alertPinState ? "AKTYWNY" : "OK");
  unsigned long now = millis();
  if (now - lastPublish >= PUBLISH_INTERVAL_MS) {
    lastPublish = now;
    StaticJsonDocument<256> doc;
    doc["node_id"] = NODE_ID;
    doc["temperature"] = round(temperatureC * 100.0) / 100.0;
    // TMP102 mierzy tylko temperaturę. Zamień na odczyt z BME680:
    doc["lux"] = 0;
    doc["distance"] = 0;
    char timestamp[25];
    if (getIsoTimestamp(timestamp, sizeof(timestamp))) {
      doc["timestamp"] = timestamp;
    }
    char jsonBuffer[256];
    serializeJson(doc, jsonBuffer, sizeof(jsonBuffer));
    if (client.publish(DATA_TOPIC, jsonBuffer, false)) {
      Serial.print("Wysłano do ");
      Serial.print(DATA_TOPIC);
      Serial.print(": ");
      Serial.println(jsonBuffer);
    } else {
      Serial.println("Błąd publikacji MQTT.");
    }
  }
}