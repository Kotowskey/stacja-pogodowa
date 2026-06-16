

<div align="center">

# Sprawozdanie z projektu

![pb](https://pb.edu.pl/siw/wp-content/uploads/sites/101/2023/06/Logo-PB-poziome-kolor-czarny-zoom.webp)

**Zaawansowany system monitorowania wnętrza czołgu — bramka Raspberry Pi**

---

**Wykonawcy:** Łukasz Kotowski, Jakub Kiryłowicz, Dawid Szczawiński, Jakub Werykowski

**Przedmiot:** Internet rzeczy (IoT)  

---

</div>

## 1. Wprowadzenie

W ramach projektu z przedmiotu **Internet rzeczy (IoT)** zaprojektowaliśmy i zaimplementowaliśmy zaawansowany system monitorowania wnętrza czołgu oparty na architekturze węzły–bramka. System składa się z co najmniej trzech węzłów pomiarowych (mikrokontrolery ESP32), bramki agregującej dane (Raspberry Pi 3) oraz warstwy wizualizacji dostępnej w sieci lokalnej.

Celem projektu było spełnienie wymagań laboratoryjnych dotyczących:

- minimum **3 węzłów IoT** i **2 czujników** pomiarowych,
- komunikacji **MQTT** z **szyfrowaniem TLS**,
- przechowywania historii pomiarów w bazie danych,
- prezentacji wyników w panelu webowym z aktualizacją na żywo.

## 2. Opis systemu

Zbudowany przez nas system realizuje następujące funkcje:

| Warstwa | Rola | Technologie |
|---------|------|-------------|
| Węzły pomiarowe | Zbieranie danych z czujników, publikacja MQTT | ESP32, Arduino IDE, PubSubClient |
| Broker MQTT | Pośrednictwo w wymianie wiadomości, szyfrowanie TLS | Mosquitto (Docker / natywnie na RPi) |
| Bramka | Subskrypcja pomiarów, zapis do bazy, API HTTP/WS | Raspberry Pi 3, Python, FastAPI |
| Wizualizacja | Dashboard z kartami węzłów i wykresami historii | HTML, CSS, JavaScript, Chart.js |

Węzły ESP32 mierzą m.in. **temperaturę** (czujnik TMP102 / planowany BME680), a w rozszerzonej wersji systemu przewidziano dodatkowo pomiar **odległości** (HC-SR04) oraz **natężenia światła** (LDR). Dane są interpretowane jako parametry środowiskowe kluczowe dla bezpieczeństwa i świadomości sytuacyjnej załogi wewnątrz czołgu. Do testów i demonstracji bez sprzętu przygotowaliśmy **symulator trzech węzłów**, który publikuje dane w identycznym formacie JSON co firmware ESP32.

```
┌──────────┐  MQTT/TLS  ┌──────────────┐   HTTP/WS   ┌────────────┐
│  ESP32   │──────────► │  Mosquitto   │ ◄─────────► │ Raspberry  │
│ (węzeł)  │  :8883     │   (broker)   │   mqtts     │   Pi GW    │ ──► Web UI / API
└──────────┘  JSON      └──────────────┘             └────────────┘
                                                          │
                                                          ▼
                                                      SQLite DB
```
<div align="center">
![https://ibb.co/V0Yd3h68](https://ibb.co/V0Yd3h68)
</div>

## 3. Architektura i struktura repozytorium

Projekt podzieliliśmy na moduły odpowiadające poszczególnym elementom systemu:

```
iot/
├── config.yaml                  konfiguracja bramki (MQTT + TLS, baza, web)
├── docker-compose.yml           Mosquitto w kontenerze (dev)
├── docs/assets/                 materiały dokumentacyjne (logo PB)
├── mosquitto/
│   ├── config/                  mosquitto.conf, conf.d/tls.conf, passwd
│   └── certs/                   CA + certyfikat serwera (generowane skryptem)
├── esp32/weather_node/          firmware ESP32 (Arduino IDE, MQTT TLS)
├── raspberry/                   aplikacja Raspberry Pi (FastAPI + MQTT + SQLite)
└── tools/
    ├── generate_mqtt_certs.ps1  generowanie PKI (Windows)
    ├── generate_mqtt_certs.sh   generowanie PKI (Linux / RPi)
    ├── mqtt_passwd.py           generator pliku haseł Mosquitto
    └── simulator.py             symulator 3 węzłów ESP32 (MQTT TLS)
```

### 3.1. Węzły ESP32

Na każdym węźle zaimplementowaliśmy:

- połączenie Wi-Fi z siecią lokalną,
- synchronizację czasu NTP (timestamp w formacie ISO 8601),
- bezpieczne połączenie MQTT over TLS z weryfikacją certyfikatu CA,
- cykliczną publikację pomiarów co 2 sekundy na topic `weather/<node_id>/data`.

Identyfikatory węzłów skonfigurowaliśmy zgodnie z plikiem `config.yaml`: `esp32-01` (Przedział kierowcy), `esp32-02` (Przedział bojowy), `esp32-03` (Przedział napędowy).

### 3.2. Bramka Raspberry Pi

Aplikacja bramki (Python / FastAPI) realizuje:

- subskrypcję wszystkich węzłów (`weather/+/data`) z QoS 1,
- walidację i zapis pomiarów do bazy **SQLite**,
- REST API do odczytu bieżących i historycznych danych,
- strumień WebSocket (`/ws`) do aktualizacji dashboardu w czasie rzeczywistym,
- panel webowy z kartami węzłów oraz wykresami temperatury, odległości i natężenia światła.

### 3.3. Bezpieczeństwo komunikacji

Zgodnie z wymaganiami projektu zabezpieczyliśmy warstwę transportową protokołu MQTT:

- broker nasłuchuje na porcie **8883** (TLS),
- wygenerowaliśmy własną infrastrukturę PKI (CA + certyfikat serwera),
- włączyliśmy uwierzytelnianie użytkowników Mosquitto (osobne konta dla węzłów i bramki),
- ESP32 weryfikuje certyfikat CA zapisany w pamięci firmware.

| Element | Wartość domyślna (dev) |
|---------|------------------------|
| Port TLS | `8883` |
| Użytkownik ESP32 / symulator | `esp32_user` |
| Użytkownik bramki RPi | `rpi_gateway` |
| Hasło (dev) | `iot-dev-pass` |
| Certyfikat CA | `mosquitto/certs/ca.crt` |

## 4. Format wiadomości MQTT

Ustaliliśmy jednolity format payloadu JSON dla wszystkich węzłów:

- **Topic:** `weather/<node_id>/data` (np. `weather/esp32-01/data`)
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

## 5. Proces wdrożenia i uruchomienia

Poniżej opisujemy kolejne kroki, które wykonaliśmy (lub wykonujemy) przy uruchamianiu systemu.

### 5.1. Generowanie certyfikatów i haseł

**Windows (PowerShell):**

```powershell
.\tools\generate_mqtt_certs.ps1
```

**Linux / Raspberry Pi 3:**

```bash
chmod +x tools/generate_mqtt_certs.sh
./tools/generate_mqtt_certs.sh --server-cn raspberrypi.local --san-ip TWOJE_IP
```

Na produkcji ustawiamy CN/SAN na hostname lub IP Raspberry Pi (wymagane przy łączeniu po IP z ESP32).

### 5.2. Uruchomienie brokera MQTT

Wymagane pliki przed startem: `mosquitto/certs/ca.crt`, `server.crt`, **`server.key`** (generowane skryptem, nie w repozytorium).

```bash
docker compose up -d mosquitto
```

Na Windows/macOS obraz Docker kopiuje certyfikaty i `passwd` do wewnętrznego systemu plików kontenera z poprawnymi uprawnieniami (bind mounty nie obsługują `chmod`/`chown`).

Broker nasłuchuje na **8883** (TLS + hasło) oraz **1883** (plain, tylko localhost w kontenerze).

### 5.3. Uruchomienie bramki Raspberry Pi

Domyślna konfiguracja w `config.yaml` używa TLS:

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

Panel webowy jest dostępny pod adresem `http://<IP_RPi>:8000`.

### 5.4. Symulator węzłów (testy bez ESP32)

Do weryfikacji całego łańcucha bez fizycznych mikrokontrolerów używamy symulatora:

```bash
python tools/simulator.py --host localhost --port 8883 --interval 2
```

Symulator emuluje trzy węzły z lekko różniącymi się profilami pomiarowymi (temperatura, odległość, lux).

### 5.5. Wgranie firmware na ESP32

1. Otwieramy `esp32/weather_node/WeatherNode.ino` w Arduino IDE.
2. Instalujemy bibliotekę **PubSubClient** (≥ 2.8) oraz **ArduinoJson**.
3. Kopiujemy `secrets.h.example` → `secrets.h` (lub edytujemy `secure.h`).
4. Wklejamy zawartość `mosquitto/certs/ca.crt` do `CA_CERT`.
5. Ustawiamy `MQTT_HOST` na IP Raspberry Pi oraz `NODE_ID` (np. `esp32-01`).
6. Wgrywamy firmware — w Serial Monitorze (115200) powinno pojawić się potwierdzenie połączenia z brokerem (TLS).

### 5.6. Wdrożenie natywne na Raspberry Pi 3

Na docelowym urządzeniu zainstalowaliśmy Mosquitto bezpośrednio w systemie:

```bash
sudo apt install -y mosquitto mosquitto-clients openssl
./tools/generate_mqtt_certs.sh --server-cn raspberrypi.local --san-ip $(hostname -I | awk '{print $1}')
sudo cp mosquitto/certs/{ca.crt,server.crt,server.key} /etc/mosquitto/certs/
sudo cp mosquitto/config/passwd /etc/mosquitto/passwd
sudo cp mosquitto/config/rpi-tls.conf.example /etc/mosquitto/conf.d/tls.conf
sudo chown mosquitto: /etc/mosquitto/certs/* /etc/mosquitto/passwd
sudo systemctl restart mosquitto
```

Test subskrypcji:

```bash
mosquitto_sub -h localhost -p 8883 \
  --cafile mosquitto/certs/ca.crt \
  -u esp32_user -P iot-dev-pass \
  -t "weather/+/data" -v
```

## 6. API HTTP bramki

Zaimplementowaliśmy następujące endpointy:

| Metoda | Endpoint | Opis |
|--------|----------|------|
| GET | `/` | Dashboard webowy |
| GET | `/api/health` | Status bramki + MQTT (`mqtt_tls`, `mqtt_port`) |
| GET | `/api/nodes` | Lista węzłów + ostatni pomiar |
| GET | `/api/measurements/latest` | Najnowszy pomiar dla każdego węzła |
| GET | `/api/measurements/history?node_id=…&limit=…` | Historia pomiarów |
| WS | `/ws` | Strumień pomiarów na żywo |

## 7. Wymagania środowiskowe

- Python 3.10+
- OpenSSL (generowanie certyfikatów)
- Broker Mosquitto (Docker lub natywnie na RPi)
- (opcjonalnie) Docker Compose
- Arduino IDE + biblioteki ESP32 (dla węzłów fizycznych)

## 8. Wyniki i wnioski

W ramach projektu udało nam się zrealizować kompletny łańcuch IoT: od węzłów pomiarowych, przez zabezpieczony broker MQTT, po bramkę z bazą danych i interfejsem użytkownika. System spełnia wymagania dotyczące liczby węzłów, szyfrowanej komunikacji oraz wizualizacji danych dla zaawansowanego monitorowania wnętrza czołgu w sieci lokalnej.

**Osiągnięte cele:**

- działająca komunikacja MQTT over TLS między węzłami a bramką,
- zapis i odczyt historii pomiarów w SQLite,
- dashboard webowy z aktualizacją WebSocket i wykresami,
- symulator umożliwiający testy bez sprzętu,
- skrypty automatyzujące generowanie certyfikatów i haseł.

**Możliwe kierunki rozwoju:**

- podłączenie czujnika **BME680** (temperatura, wilgotność, ciśnienie) oraz **HC-SR04** w firmware ESP32,
- rotacja certyfikatów (plik CA w SPIFFS lub NVS na ESP32),
- mTLS (certyfikat klienta na ESP32) dla wyższego poziomu bezpieczeństwa,
- alerty przy przekroczeniu progów (np. pin ALERT na TMP102).

> **Uwaga (tryb dev):** wyłączenie TLS w `config.yaml` (`mqtt.tls.enabled: false`, `port: 1883`) i uruchomienie brokera bez `tls.conf` jest możliwe wyłącznie lokalnie.

---

<div align="center">


</div>