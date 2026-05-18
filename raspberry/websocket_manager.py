"""Prosty manager połączeń WebSocket - rozsyła wiadomości do wszystkich klientów."""

from __future__ import annotations

import asyncio
import logging
from typing import Set

from fastapi import WebSocket


log = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log.info("WS klient połączony (łącznie: %d)", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        log.info("WS klient rozłączony (łącznie: %d)", len(self._clients))

    async def broadcast_json(self, payload: dict) -> None:
        if not self._clients:
            return
        async with self._lock:
            clients = list(self._clients)

        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
