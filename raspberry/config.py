from __future__ import annotations

import os
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field


class MqttTlsConfig(BaseModel):
    """TLS/SSL dla połączenia z brokerem Mosquitto (port 8883)."""

    enabled: bool = False
    ca_file: str = "mosquitto/certs/ca.crt"
    certfile: str = ""
    keyfile: str = ""
    # Tylko dev: wyłącza weryfikację certyfikatu (NIE używać w produkcji)
    insecure: bool = False


class MqttConfig(BaseModel):
    host: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    client_id: str = "rpi-gateway"
    topic_subscribe: str = "weather/+/data"
    qos: int = 1
    keepalive: int = 60
    tls: MqttTlsConfig = Field(default_factory=MqttTlsConfig)


class DatabaseConfig(BaseModel):
    path: str = "data/weather.db"
    history_limit: int = 500


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    title: str = "Stacja Pogodowa - IoT"


class NodeConfig(BaseModel):
    id: str
    name: str


class AppConfig(BaseModel):
    mqtt: MqttConfig = Field(default_factory=MqttConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    nodes: List[NodeConfig] = Field(default_factory=list)


def _default_config_path() -> Path:
    # repo root = parent katalogu `raspberry/`
    return Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: str | os.PathLike[str] | None = None) -> AppConfig:
    """Wczytuje konfigurację z pliku YAML.

    Kolejność wyszukiwania: argument `path` > zmienna IOT_CONFIG > config.yaml w repo.
    Brak pliku nie jest błędem - używamy wtedy wartości domyślnych.
    """
    if path is None:
        path = os.environ.get("IOT_CONFIG") or _default_config_path()

    p = Path(path)
    if not p.exists():
        return AppConfig()

    with p.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return AppConfig.model_validate(raw)
