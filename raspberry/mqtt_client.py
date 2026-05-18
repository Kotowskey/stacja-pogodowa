"""Klient MQTT - subskrybuje pomiary z węzłów, zapisuje do bazy
i rozsyła na żywo przez WebSocket.

Używamy paho-mqtt w trybie pętli wątkowej (`loop_start`), a wszystkie operacje
asynchroniczne (zapis do bazy, broadcast) wywołujemy w głównym event-loopie
poprzez `asyncio.run_coroutine_threadsafe`.
"""

from __future__ import annotations

import asyncio
import json
import logging
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

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        log.info(
            "MQTT: łączę z %s:%s (topic=%s)",
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
            "RX %s | T=%.2f°C  p=%.2f hPa  RH=%.1f%%",
            node_id,
            saved.temperature,
            saved.pressure,
            saved.humidity,
        )
        await self._ws.broadcast_json(
            {"type": "measurement", "data": saved.model_dump(mode="json")}
        )
