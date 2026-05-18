"""Modele Pydantic - format danych przesyłanych przez MQTT i API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class MeasurementIn(BaseModel):
    """Pomiar otrzymany z węzła ESP32 przez MQTT (payload JSON).

    Format publikowany przez węzeł:
        {
          "node_id": "esp32-01",
          "timestamp": "2026-05-18T12:30:00Z",   # opcjonalnie - jeśli brak, ustawiamy po stronie serwera
          "temperature": 23.5,                    # [°C]
          "pressure": 1013.25,                    # [hPa]
          "humidity": 55.3                        # [%]
        }
    """

    node_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    temperature: float = Field(..., description="Temperatura [°C]")
    pressure: float = Field(..., description="Ciśnienie [hPa]")
    humidity: float = Field(..., ge=0, le=100, description="Wilgotność względna [%]")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_ts(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        return v


class MeasurementOut(BaseModel):
    """Pomiar zwracany przez API / wysyłany przez WebSocket."""

    id: int
    node_id: str
    timestamp: datetime
    temperature: float
    pressure: float
    humidity: float


class NodeInfo(BaseModel):
    id: str
    name: str
    last_seen: Optional[datetime] = None
    last_measurement: Optional[MeasurementOut] = None
