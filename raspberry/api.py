from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import AppConfig, load_config
from .database import Database
from .mqtt_client import MqttGateway
from .schemas import MeasurementOut, NodeInfo
from .websocket_manager import WebSocketManager


log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent


def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    cfg = config or load_config()

    db = Database(cfg.database.path)
    ws_manager = WebSocketManager()
    gateway: Optional[MqttGateway] = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio

        await db.connect()
        log.info("Baza danych otwarta: %s", cfg.database.path)

        loop = asyncio.get_running_loop()
        nonlocal gateway
        gateway = MqttGateway(cfg.mqtt, db, ws_manager, loop)
        gateway.start()
        try:
            yield
        finally:
            if gateway is not None:
                gateway.stop()
            await db.close()

    app = FastAPI(title=cfg.web.title, lifespan=lifespan)
    app.state.config = cfg

    app.mount(
        "/static",
        StaticFiles(directory=str(_HERE / "static")),
        name="static",
    )
    templates = Jinja2Templates(directory=str(_HERE / "templates"))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "title": cfg.web.title,
                "nodes": cfg.nodes,
            },
        )

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "mqtt_connected": bool(gateway and gateway.connected),
            "mqtt_tls": cfg.mqtt.tls.enabled,
            "mqtt_port": cfg.mqtt.port,
            "time": datetime.utcnow().isoformat() + "Z",
        }

    @app.get("/api/nodes", response_model=List[NodeInfo])
    async def list_nodes():
        configured: Dict[str, str] = {n.id: n.name for n in cfg.nodes}
        latest: Dict[str, MeasurementOut] = {
            m.node_id: m for m in await db.latest_per_node()
        }

        result: List[NodeInfo] = []
        for node_id in sorted(set(configured) | set(latest)):
            m = latest.get(node_id)
            result.append(
                NodeInfo(
                    id=node_id,
                    name=configured.get(node_id, node_id),
                    last_seen=m.timestamp if m else None,
                    last_measurement=m,
                )
            )
        return result

    @app.get("/api/measurements/latest", response_model=List[MeasurementOut])
    async def latest():
        return await db.latest_per_node()

    @app.get("/api/measurements/history", response_model=List[MeasurementOut])
    async def history(
        node_id: Optional[str] = Query(None, description="Filtruj po identyfikatorze węzła"),
        limit: int = Query(
            None,
            ge=1,
            le=10000,
            description="Maksymalna liczba zwracanych rekordów",
        ),
    ):
        return await db.history(
            node_id=node_id,
            limit=limit or cfg.database.history_limit,
        )

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws_manager.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await ws_manager.disconnect(ws)

    return app
