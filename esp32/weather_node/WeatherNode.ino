/**
 * Węzeł pogodowy ESP32 – publikacja pomiarów przez MQTT over TLS.
 * Format zgodny z bramką Raspberry Pi: topic weather/<node_id>/data
 *
 * Biblioteki (Arduino Library Manager): PubSubClient (Nick O'Leary) >= 2.8
 * WiFiClientSecure – wbudowana w ESP32 core.
 *
 * Skopiuj secrets.h.example → secrets.h i wklej certyfikat CA.
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include "secrets.h"

#ifndef NODE_ID
#define NODE_ID MQTT_CLIENT_ID
#endif

WiFiClientSecure tlsClient;
PubSubClient mqttClient(tlsClient);

unsigned long lastPublishMs = 0;
const long publishIntervalMs = 5000;

char topicData[48];

void printTLSError() {
  int err = tlsClient.lastError(nullptr, 0);
  if (err != 0) {
    char errBuf[256];
    tlsClient.lastError(errBuf, sizeof(errBuf));
    Serial.printf("[TLS] Blad %d: %s\n", err, errBuf);
  }
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.printf("[WiFi] Laczenie z %s ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (++attempts > 40) {
      Serial.println("\n[WiFi] BLAD – restart");
      ESP.restart();
    }
  }
  Serial.printf("\n[WiFi] Polaczono, IP: %s\n", WiFi.localIP().toString().c_str());
}

void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.printf("[MQTT] Laczenie z %s:%d (TLS) ...\n", MQTT_HOST, MQTT_PORT);

    if (mqttClient.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASSWORD)) {
      Serial.println("[MQTT] Polaczono z brokerem (TLS)");
    } else {
      Serial.printf("[MQTT] Blad, rc=%d\n", mqttClient.state());
      printTLSError();
      delay(5000);
    }
  }
}

void publishMeasurement() {
  // TODO: podłącz prawdziwe czujniki (BME680, HC-SR04, ...)
  float temperature = 22.0f + (random(0, 100) / 100.0f);
  float distance = 40.0f + (random(0, 200) / 10.0f);
  float lux = 300.0f + random(0, 150);

  char payload[256];
  snprintf(
    payload, sizeof(payload),
    "{\"node_id\":\"%s\",\"temperature\":%.2f,\"distance\":%.2f,\"lux\":%.1f}",
    NODE_ID,
    roundf(temperature * 100.0f) / 100.0f,
    roundf(distance * 100.0f) / 100.0f,
    roundf(lux * 10.0f) / 10.0f
  );

  if (mqttClient.publish(topicData, payload, false)) {
    Serial.printf("[MQTT] -> %s  %s\n", topicData, payload);
  } else {
    Serial.println("[MQTT] Blad publikacji");
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  randomSeed(esp_random());

  snprintf(topicData, sizeof(topicData), "weather/%s/data", NODE_ID);

  connectWiFi();

  tlsClient.setCACert(CA_CERT);
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setBufferSize(512);

  connectMQTT();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  if (!mqttClient.connected()) {
    connectMQTT();
  }
  mqttClient.loop();

  unsigned long now = millis();
  if (now - lastPublishMs >= (unsigned long)publishIntervalMs) {
    lastPublishMs = now;
    publishMeasurement();
  }
}
