from __future__ import annotations

import asyncio
import json
import logging
import ssl
from pathlib import Path
from typing import Optional

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from .config import MqttConfig
from .database import Database
from .schemas import MeasurementIn
from .websocket_manager import WebSocketManager


log = logging.getLogger(__name__)


class MqttGateway:
    """Bramka MQTT → baza → WebSocket."""

    def __init__(
        self,
        cfg: MqttConfig,
        db: Database,
        ws: WebSocketManager,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._cfg = cfg
        self._db = db
        self._ws = ws
        self._loop = loop
        self._client: Optional[mqtt.Client] = None
        self._connected = asyncio.Event()

    # ------------------------------------------------------------------ public
    def start(self) -> None:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._cfg.client_id or None,
        )
        if self._cfg.username:
            client.username_pw_set(self._cfg.username, self._cfg.password or None)

        if self._cfg.tls.enabled:
            self._configure_tls(client)

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        proto = "mqtts" if self._cfg.tls.enabled else "mqtt"
        log.info(
            "MQTT: łączę z %s://%s:%s (topic=%s)",
            proto,
            self._cfg.host,
            self._cfg.port,
            self._cfg.topic_subscribe,
        )
        client.connect_async(self._cfg.host, self._cfg.port, self._cfg.keepalive)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
            finally:
                self._client.loop_stop()
            self._client = None

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def _resolve_cert_path(self, path: str) -> str:
        p = Path(path)
        if p.is_absolute():
            return str(p)
        repo_root = Path(__file__).resolve().parent.parent
        return str(repo_root / p)

    def _configure_tls(self, client: mqtt.Client) -> None:
        tls = self._cfg.tls
        ca_file = self._resolve_cert_path(tls.ca_file) if tls.ca_file else None
        certfile = self._resolve_cert_path(tls.certfile) if tls.certfile else None
        keyfile = self._resolve_cert_path(tls.keyfile) if tls.keyfile else None

        if ca_file and not Path(ca_file).exists():
            raise FileNotFoundError(
                f"Brak pliku CA dla TLS: {ca_file}. "
                "Uruchom tools/generate_mqtt_certs.ps1 lub .sh"
            )

        client.tls_set(
            ca_certs=ca_file,
            certfile=certfile,
            keyfile=keyfile,
            cert_reqs=ssl.CERT_NONE if tls.insecure else ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        if tls.insecure:
            client.tls_insecure_set(True)
            log.warning("MQTT TLS: tryb insecure (bez weryfikacji certyfikatu)")

    # --------------------------------------------------------------- callbacks
    def _on_connect(self, client: mqtt.Client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            log.info("MQTT: połączono - subskrybuję %s", self._cfg.topic_subscribe)
            client.subscribe(self._cfg.topic_subscribe, qos=self._cfg.qos)
            self._loop.call_soon_threadsafe(self._connected.set)
        else:
            log.error("MQTT: błąd połączenia: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        log.warning("MQTT: rozłączono (reason=%s) - ponowne łączenie...", reason_code)
        self._loop.call_soon_threadsafe(self._connected.clear)

    def _on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        # Topic: weather/<node_id>/data - wyciągamy node_id ze ścieżki
        parts = msg.topic.split("/")
        topic_node_id = parts[1] if len(parts) >= 2 else None

        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            log.warning("Nieprawidłowy payload na %s: %s", msg.topic, exc)
            return

        try:
            measurement = MeasurementIn.model_validate(payload)
        except ValidationError as exc:
            log.warning("Walidacja payloadu na %s nie powiodła się: %s", msg.topic, exc)
            return

        node_id = measurement.node_id or topic_node_id
        if not node_id:
            log.warning("Brak node_id w payloadzie ani w topicu %s", msg.topic)
            return

        # Cała logika async musi przejść do głównego loopa
        asyncio.run_coroutine_threadsafe(
            self._handle_measurement(node_id, measurement), self._loop
        )

    # --------------------------------------------------------------- async pipeline
    async def _handle_measurement(self, node_id: str, m: MeasurementIn) -> None:
        try:
            saved = await self._db.insert_measurement(node_id, m)
        except Exception:
            log.exception("Błąd zapisu pomiaru do bazy")
            return

        log.info(
            "RX %s | T=%.2f°C  d=%.2f cm  L=%.1f lx",
            node_id,
            saved.temperature,
            saved.distance,
            saved.lux,
        )
        await self._ws.broadcast_json(
            {"type": "measurement", "data": saved.model_dump(mode="json")}
        )
