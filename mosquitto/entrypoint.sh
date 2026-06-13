#!/bin/ash
set -e

# Windows/macOS bind mounts expose files as world-readable with root ownership.
# Mosquitto 2.x requires passwd and private keys to be owned by mosquitto with
# restrictive permissions — copy from read-only mounts into the container FS.

SRC_CONFIG="${MOSQUITTO_CONFIG_SRC:-/mosquitto/config-src}"
SRC_CERTS="${MOSQUITTO_CERTS_SRC:-/mosquitto/certs-src}"
DEST_CONFIG="/mosquitto/config"
DEST_CERTS="/mosquitto/certs"

mkdir -p "$DEST_CONFIG/conf.d" "$DEST_CERTS"

cp -f "$SRC_CONFIG/mosquitto.conf" "$DEST_CONFIG/"
cp -f "$SRC_CONFIG/passwd" "$DEST_CONFIG/"
if [ -d "$SRC_CONFIG/conf.d" ]; then
	cp -rf "$SRC_CONFIG/conf.d/"* "$DEST_CONFIG/conf.d/"
fi

if [ -d "$SRC_CERTS" ]; then
	for f in "$SRC_CERTS"/*; do
		[ -f "$f" ] || continue
		cp -f "$f" "$DEST_CERTS/"
	done
fi

chown mosquitto:mosquitto "$DEST_CONFIG/passwd"
chmod 700 "$DEST_CONFIG/passwd"

if [ -d "$DEST_CERTS" ]; then
	chown -R mosquitto:mosquitto "$DEST_CERTS"
	for f in "$DEST_CERTS"/*.key; do
		[ -f "$f" ] && chmod 600 "$f"
	done
	for f in "$DEST_CERTS"/*.crt; do
		[ -f "$f" ] && chmod 644 "$f"
	done
fi

PUID="${PUID:-1883}"
PGID="${PGID:-1883}"
if [ "$(id -u)" = '0' ]; then
	[ -d "/mosquitto/data" ] && chown -R "${PUID}:${PGID}" /mosquitto/data || true
fi

exec "$@"
