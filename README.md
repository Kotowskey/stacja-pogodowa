# Stacja pogodowa IoT — bramka Raspberry Pi

Projekt systemu IoT zgodny z założeniami z `Projekt.pdf`:

- **System IoT** z minimum 3 węzłami i minimum 2 czujnikami (BME680 → temperatura `T`, ciśnienie `p`, wilgotność `H`).
- **Komunikacja:** MQTT (broker Mosquitto), payload w formacie JSON.
- **Raspberry Pi** pełni rolę **gateway + baza + wizualizacja** z widocznością na zewnątrz (panel webowy w LAN).
- ESP32 (węzły) zostaną dodane w kolejnym etapie — tymczasem do testów służy symulator publikujący identyczne pakiety.

```
┌──────────┐   MQTT   ┌──────────────┐   HTTP/WS   ┌────────────┐
│  ESP32   │────────► │  Mosquitto   │ ◄─────────► │ Raspberry  │
│ (węzeł)  │ JSON     │   (broker)   │             │   Pi GW    │ ──► Web UI / API
└──────────┘          └──────────────┘             └────────────┘
                                                          │
                                                          ▼
                                                      SQLite DB
```

## Struktura projektu

```
iot/
├── config.yaml                  konfiguracja bramki (MQTT, baza, web, węzły)
├── docker-compose.yml           Mosquitto w kontenerze (dev)
├── mosquitto/config/            konfiguracja brokera
├── requirements.txt             zależności Pythona
├── raspberry/                   aplikacja Raspberry Pi (FastAPI + MQTT + SQLite)
│   ├── main.py                  punkt wejścia (uvicorn)
│   ├── api.py                   REST + WebSocket + UI
│   ├── mqtt_client.py           bramka MQTT → DB → WebSocket
│   ├── database.py              SQLite (aiosqlite)
│   ├── schemas.py               modele Pydantic
│   ├── config.py                ładowanie YAML
│   ├── websocket_manager.py     broadcasting WS
│   ├── templates/index.html     dashboard
│   └── static/{style.css,app.js}
└── tools/
    └── simulator.py             symulator 3 węzłów ESP32
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

## Wymagania

- Python 3.10+ (testowane z 3.13)
- Broker Mosquitto (lokalnie, w Dockerze lub np. na innym hoście)
- (opcjonalnie) Docker / Docker Compose — najszybszy sposób uruchomienia brokera

## Szybki start (środowisko deweloperskie)

### 1. Uruchom brokera Mosquitto

Najprościej w Dockerze:

```bash
docker compose up -d mosquitto
```

Albo zainstaluj Mosquitto lokalnie i wskaż go w `config.yaml` (`mqtt.host`, `mqtt.port`).

### 2. Zainstaluj zależności i uruchom bramkę

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
python -m raspberry.main
```

Bramka:

- nasłuchuje MQTT na topicu z `config.yaml` (`weather/+/data`),
- zapisuje pomiary do SQLite (`data/weather.db`),
- udostępnia dashboard pod **http://localhost:8000** oraz REST/WS dla integracji.

### 3. Uruchom symulator (zamiast ESP32)

```bash
python tools/simulator.py --host localhost --interval 2
```

W dashboardzie pojawią się 3 węzły z aktualizacją w czasie rzeczywistym.

## API HTTP

| Metoda | Endpoint                              | Opis                                              |
|--------|---------------------------------------|---------------------------------------------------|
| GET    | `/`                                   | Dashboard webowy                                  |
| GET    | `/api/health`                         | Status bramki + MQTT                              |
| GET    | `/api/nodes`                          | Lista węzłów + ostatni pomiar każdego z nich      |
| GET    | `/api/measurements/latest`            | Najnowszy pomiar dla każdego węzła                |
| GET    | `/api/measurements/history?node_id=…&limit=…` | Historia pomiarów (do wykresów)         |
| WS     | `/ws`                                 | Strumień pomiarów na żywo (`{type, data}`)        |

## Konfiguracja

Plik `config.yaml` w katalogu głównym repo. Ścieżkę można nadpisać zmienną `IOT_CONFIG`.

```yaml
mqtt:
  host: "localhost"
  port: 1883
  topic_subscribe: "weather/+/data"
database:
  path: "data/weather.db"
  history_limit: 500
web:
  host: "0.0.0.0"   # 0.0.0.0 => dashboard widoczny w sieci LAN
  port: 8000
nodes:
  - { id: "esp32-01", name: "Salon" }
  - { id: "esp32-02", name: "Sypialnia" }
  - { id: "esp32-03", name: "Balkon" }
```

## Co dalej (kolejne etapy projektu)

- Firmware dla ESP32 z czujnikiem **BME680** publikującym do MQTT na opisanym wyżej topicu/payloadzie.
- Drugi czujnik (zgodnie z założeniami min. 2 HW), np. **PMS7003** (pyły) lub **HC-SR04** (dystans).
- Alternatywne formaty payloadu: Protobuf / FlatBuffers / ASCII / binary (zgodnie z `Projekt.pdf`).
- Eksport pomiarów do chmury (np. MQTT bridge lub HTTP push).
```
