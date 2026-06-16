from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class MeasurementIn(BaseModel):
    """Pomiar otrzymany z węzła ESP32 przez MQTT (payload JSON).

    Format publikowany przez węzeł:
        {
          "node_id": "esp32-01",
          "timestamp": "2026-05-18T12:30:00Z",
          "temperature": 23.5,
          "distance": 42.0,
          "lux": 350.0
        }
    """

    node_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    temperature: float = Field(..., description="Temperatura [°C]")
    distance: float = Field(..., description="Odległość [cm]")
    lux: float = Field(..., ge=0, description="Natężenie światła [lx]")

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
    distance: float
    lux: float


class NodeInfo(BaseModel):
    id: str
    name: str
    last_seen: Optional[datetime] = None
    last_measurement: Optional[MeasurementOut] = None
