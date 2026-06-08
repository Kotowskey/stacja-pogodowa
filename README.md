# Stacja pogodowa IoT — bramka Raspberry Pi

Projekt systemu IoT zgodny z założeniami z `Projekt.pdf`:

- **System IoT** z minimum 3 węzłami i minimum 2 czujnikami (BME680 → temperatura `T`, ciśnienie `p`, wilgotność `H`).
- **Komunikacja:** MQTT (broker Mosquitto) z **szyfrowaniem TLS** (port 8883), payload w formacie JSON.
- **Raspberry Pi 3** pełni rolę **gateway + broker + baza + wizualizacja** z widocznością na zewnątrz (panel webowy w LAN).
- **ESP32** publikuje pomiary przez MQTT over TLS; do testów służy symulator z identycznym protokołem.

```
┌──────────┐  MQTT/TLS  ┌──────────────┐   HTTP/WS   ┌────────────┐
│  ESP32   │──────────► │  Mosquitto   │ ◄─────────► │ Raspberry  │
│ (węzeł)  │  :8883     │   (broker)   │   mqtts     │   Pi GW    │ ──► Web UI / API
└──────────┘  JSON      └──────────────┘             └────────────┘
                                                          │
                                                          ▼
                                                      SQLite DB
```

## Struktura projektu

```
iot/
├── config.yaml                  konfiguracja bramki (MQTT + TLS, baza, web)
├── docker-compose.yml           Mosquitto w kontenerze (dev)
├── mosquitto/
│   ├── config/                  mosquitto.conf, tls.conf, passwd
│   └── certs/                   CA + certyfikat serwera (generowane skryptem)
├── esp32/weather_node/          firmware ESP32 (Arduino IDE, MQTT TLS)
├── raspberry/                   aplikacja Raspberry Pi (FastAPI + MQTT + SQLite)
└── tools/
    ├── generate_mqtt_certs.ps1  generowanie PKI (Windows)
    ├── generate_mqtt_certs.sh   generowanie PKI (Linux / RPi)
    ├── mqtt_passwd.py           generator pliku haseł Mosquitto
    └── simulator.py             symulator 3 węzłów ESP32 (MQTT TLS)
```

## Format wiadomości MQTT

- **Topic:** `weather/<node_id>/data`  (np. `weather/esp32-01/data`)
- **Payload (JSON):**

```json
{
  "node_id": "esp32-01",
  "timestamp": "2026-05-18T12:30:00Z",
  "temperature": 23.5,
  "distance": 42.0,
  "lux": 350.0
}
```

Pole `timestamp` jest opcjonalne — jeśli go nie ma, bramka stempluje pomiar czasem odbioru.
Pole `node_id` w payloadzie jest opcjonalne — alternatywnie brane jest z topicu.

## Szyfrowanie MQTT (TLS)

Komunikacja ESP32 ↔ Raspberry Pi jest szyfrowana warstwą **TLS/SSL** na brokerze Mosquitto (self-signed CA + hasła użytkowników). Schemat zgodny z dokumentacją w `Claude.html`.

| Element | Wartość domyślna (dev) |
|---------|------------------------|
| Port TLS | `8883` |
| Użytkownik ESP32 / symulator | `esp32_user` |
| Użytkownik bramki RPi | `rpi_gateway` |
| Hasło (dev) | `iot-dev-pass` |
| Certyfikat CA | `mosquitto/certs/ca.crt` |

### 1. Wygeneruj certyfikaty i hasła

**Windows (PowerShell):**

```powershell
.\tools\generate_mqtt_certs.ps1
```

**Linux / Raspberry Pi 3:**

```bash
chmod +x tools/generate_mqtt_certs.sh
./tools/generate_mqtt_certs.sh --server-cn raspberrypi.local --san-ip TWOJE_IP
```

Na produkcji ustaw CN/SAN na hostname lub IP Raspberry Pi (wymagane przy łączeniu po IP z ESP32).

### 2. Uruchom brokera

```bash
docker compose up -d mosquitto
```

Broker nasłuchuje na **8883** (TLS + hasło) oraz **1883** (plain, tylko localhost w kontenerze).

### 3. Bramka Raspberry Pi

`config.yaml` domyślnie używa TLS:

```yaml
mqtt:
  host: "localhost"
  port: 8883
  username: "rpi_gateway"
  password: "iot-dev-pass"
  tls:
    enabled: true
    ca_file: "mosquitto/certs/ca.crt"
```

```bash
pip install -r requirements.txt
python -m raspberry.main
```

### 4. Symulator (zamiast ESP32)

```bash
python tools/simulator.py --host localhost --port 8883 --interval 2
```

### 5. ESP32 (Arduino IDE)

1. Otwórz `esp32/weather_node/WeatherNode.ino` w Arduino IDE.
2. Zainstaluj bibliotekę **PubSubClient** (≥ 2.8).
3. Skopiuj `secrets.h.example` → `secrets.h`.
4. Wklej zawartość `mosquitto/certs/ca.crt` do `CA_CERT` w `secrets.h`.
5. Ustaw `MQTT_HOST` na IP Raspberry Pi i `NODE_ID` (np. `esp32-01`).
6. Wgraj firmware — w Serial Monitorze (115200) powinno pojawić się `Polaczono z brokerem (TLS)`.

### Wdrożenie na Raspberry Pi 3 (natywny Mosquitto)

```bash
sudo apt install -y mosquitto mosquitto-clients openssl
./tools/generate_mqtt_certs.sh --server-cn raspberrypi.local --san-ip $(hostname -I | awk '{print $1}')
sudo cp mosquitto/certs/{ca.crt,server.crt,server.key} /etc/mosquitto/certs/
sudo cp mosquitto/config/passwd /etc/mosquitto/passwd
sudo cp mosquitto/config/rpi-tls.conf.example /etc/mosquitto/conf.d/tls.conf
sudo chown mosquitto: /etc/mosquitto/certs/* /etc/mosquitto/passwd
sudo systemctl restart mosquitto
```

Test:

```bash
mosquitto_sub -h localhost -p 8883 \
  --cafile mosquitto/certs/ca.crt \
  -u esp32_user -P iot-dev-pass \
  -t "weather/+/data" -v
```

## Wymagania

- Python 3.10+
- OpenSSL (generowanie certyfikatów)
- Broker Mosquitto (Docker lub natywnie na RPi)
- (opcjonalnie) Docker Compose

## API HTTP

| Metoda | Endpoint | Opis |
|--------|----------|------|
| GET | `/` | Dashboard webowy |
| GET | `/api/health` | Status bramki + MQTT (+ `mqtt_tls`, `mqtt_port`) |
| GET | `/api/nodes` | Lista węzłów + ostatni pomiar |
| GET | `/api/measurements/latest` | Najnowszy pomiar dla każdego węzła |
| GET | `/api/measurements/history?node_id=…&limit=…` | Historia pomiarów |
| WS | `/ws` | Strumień pomiarów na żywo |

## Tryb bez TLS (tylko dev)

Wyłącz TLS w `config.yaml` (`mqtt.tls.enabled: false`, `port: 1883`) i uruchom brokera bez `tls.conf`. Nie używaj tego w sieci produkcyjnej.

## Co dalej

- Podłączenie czujnika **BME680** i **HC-SR04** w firmware ESP32.
- Rotacja certyfikatów (plik CA w SPIFFS lub NVS na ESP32).
- mTLS (certyfikat klienta na ESP32) — opcjonalnie dla wyższego poziomu bezpieczeństwa.
