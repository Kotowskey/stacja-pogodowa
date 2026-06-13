#!/usr/bin/env bash
# Generuje self-signed PKI (CA + cert serwera) i plik haseł Mosquitto.
# Zgodnie z instrukcją TLS z Claude.html.
#
# Użycie (Linux / Raspberry Pi 3):
#   ./tools/generate_mqtt_certs.sh
#   ./tools/generate_mqtt_certs.sh --server-cn raspberrypi.local --san-ip 192.168.1.100

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

CERTS_DIR="mosquitto/certs"
PASSWD_FILE="mosquitto/config/passwd"
CA_CN="MQTT-CA"
SERVER_CN="localhost"
SAN_IP=""
ESP32_PASS="iot-dev-pass"
GATEWAY_PASS="iot-dev-pass"
DAYS=3650

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-cn) SERVER_CN="$2"; shift 2 ;;
    --san-ip) SAN_IP="$2"; shift 2 ;;
    --certs-dir) CERTS_DIR="$2"; shift 2 ;;
    *) echo "Nieznany argument: $1" >&2; exit 1 ;;
  esac
done

mkdir -p "$CERTS_DIR" "$(dirname "$PASSWD_FILE")"

echo "[certs] CA ($CA_CN)..."
# ca.crt may be committed without ca.key (gitignored); without the key we cannot sign server.crt.
if [[ -f "$CERTS_DIR/ca.crt" && ! -f "$CERTS_DIR/ca.key" ]]; then
  echo "[certs] brak ca.key — usuwam stary ca.crt i generuję CA od nowa..."
  rm -f "$CERTS_DIR/ca.crt" "$CERTS_DIR/ca.srl"
fi
if [[ ! -f "$CERTS_DIR/ca.crt" || ! -f "$CERTS_DIR/ca.key" ]]; then
  openssl genrsa -out "$CERTS_DIR/ca.key" 2048
  openssl req -new -x509 -days "$DAYS" -key "$CERTS_DIR/ca.key" \
    -out "$CERTS_DIR/ca.crt" -subj "/CN=$CA_CN"
fi

echo "[certs] certyfikat serwera (CN=$SERVER_CN)..."
EXT_FILE="$CERTS_DIR/server.ext"
{
  echo "[ v3_req ]"
  echo "subjectAltName = @alt_names"
  echo ""
  echo "[alt_names]"
  echo "DNS.1 = $SERVER_CN"
  echo "DNS.2 = raspberrypi.local"
  if [[ -n "$SAN_IP" ]]; then
    echo "IP.1 = $SAN_IP"
  fi
} > "$EXT_FILE"

openssl genrsa -out "$CERTS_DIR/server.key" 2048
openssl req -new -key "$CERTS_DIR/server.key" -out "$CERTS_DIR/server.csr" \
  -subj "/CN=$SERVER_CN"
openssl x509 -req -in "$CERTS_DIR/server.csr" -CA "$CERTS_DIR/ca.crt" \
  -CAkey "$CERTS_DIR/ca.key" -CAcreateserial -out "$CERTS_DIR/server.crt" \
  -days "$DAYS" -extfile "$EXT_FILE" -extensions v3_req

rm -f "$CERTS_DIR/server.csr" "$EXT_FILE"

echo "[certs] plik haseł MQTT..."
if command -v mosquitto_passwd >/dev/null 2>&1; then
  mosquitto_passwd -b -c "$PASSWD_FILE" esp32_user "$ESP32_PASS"
  mosquitto_passwd -b "$PASSWD_FILE" rpi_gateway "$GATEWAY_PASS"
else
  python3 "$REPO_ROOT/tools/mqtt_passwd.py" -c "$PASSWD_FILE" esp32_user "$ESP32_PASS"
  python3 "$REPO_ROOT/tools/mqtt_passwd.py" "$PASSWD_FILE" rpi_gateway "$GATEWAY_PASS"
fi

echo ""
echo "Gotowe. CA dla ESP32: $CERTS_DIR/ca.crt"
echo "Użytkownicy: esp32_user, rpi_gateway (hasło: $ESP32_PASS)"
