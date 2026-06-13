#!/usr/bin/env bash
# Sprawdza gotowosc Mosquitto w Dockerze przed docker compose up.
# Uzycie (na Raspberry Pi): ./tools/check_mosquitto_docker.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

CERTS_DIR="mosquitto/certs"
PASSWD_FILE="mosquitto/config/passwd"
CONF_FILE="mosquitto/config/mosquitto.conf"
ERR=0

check_file() {
  local path="$1"
  local label="$2"
  if [[ -f "$path" ]]; then
    echo "[OK] $label: $path"
  else
    echo "[BLAD] Brak $label: $path"
    ERR=1
  fi
}

echo "=== Mosquitto Docker – weryfikacja ==="

check_file "$CERTS_DIR/ca.crt" "certyfikat CA"
check_file "$CERTS_DIR/server.crt" "certyfikat serwera"
if [[ -f "$CERTS_DIR/server.key" ]]; then
  if [[ ! -r "$CERTS_DIR/server.key" ]]; then
    echo "[BLAD] server.key nieczytelny — uruchom: chmod 644 mosquitto/certs/server.key"
    ERR=1
  else
    echo "[OK] server.key czytelny"
  fi
else
  echo "[BLAD] Brak klucza serwera: $CERTS_DIR/server.key"
  ERR=1
fi
check_file "$PASSWD_FILE" "plik haseł"
check_file "$CONF_FILE" "mosquitto.conf"

if [[ -d "mosquitto/config/conf.d" ]] && [[ -n "$(ls -A mosquitto/config/conf.d 2>/dev/null)" ]]; then
  echo "[UWAGA] mosquitto/config/conf.d/ nie jest uzywany w Dockerze."
  echo "        Usun lub przenies te pliki — moga powodowac podwojny listener 8883."
  ERR=1
fi

if grep -qE '^\s*include\b' "$CONF_FILE" 2>/dev/null; then
  echo "[UWAGA] mosquitto.conf uzywa 'include' — w Mosquitto 2.1 w Dockerze to czesto pada."
  echo "        Uzyj jednego pliku mosquitto.conf (jak w repozytorium)."
  ERR=1
fi

if command -v openssl >/dev/null 2>&1 && [[ -f "$CERTS_DIR/server.crt" && -f "$CERTS_DIR/ca.crt" ]]; then
  if openssl verify -CAfile "$CERTS_DIR/ca.crt" "$CERTS_DIR/server.crt" >/dev/null 2>&1; then
    echo "[OK] server.crt podpisany przez ca.crt"
  else
    echo "[BLAD] server.crt NIE pasuje do ca.crt — uruchom ./tools/generate_mqtt_certs.sh"
    ERR=1
  fi
fi

if ss -tln 2>/dev/null | grep -q ':8883 '; then
  echo "[UWAGA] Port 8883 jest zajety na hoście (natywny mosquitto?)."
  echo "        Zatrzymaj: sudo systemctl stop mosquitto"
  ERR=1
fi

if [[ $ERR -ne 0 ]]; then
  echo ""
  echo "Napraw błędy, potem:"
  echo "  ./tools/generate_mqtt_certs.sh --server-cn raspberrypi.local --san-ip TWOJE_IP"
  echo "  docker compose up -d mosquitto"
  echo "  docker logs iot-mosquitto"
  exit 1
fi

echo ""
echo "Gotowe. Uruchom: docker compose up -d mosquitto"
