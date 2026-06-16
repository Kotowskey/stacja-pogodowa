from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import aiosqlite

from .schemas import MeasurementIn, MeasurementOut


_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    temperature REAL    NOT NULL,
    distance    REAL    NOT NULL,
    lux         REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_meas_node_ts
    ON measurements (node_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_meas_ts
    ON measurements (timestamp DESC);
"""


def _row_to_measurement(row: aiosqlite.Row) -> MeasurementOut:
    return MeasurementOut(
        id=row["id"],
        node_id=row["node_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        temperature=row["temperature"],
        distance=row["distance"],
        lux=row["lux"],
    )


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected - wywołaj connect() najpierw")
        return self._conn

    async def insert_measurement(
        self, node_id: str, m: MeasurementIn
    ) -> MeasurementOut:
        conn = self._require_conn()
        ts = m.timestamp or datetime.now(tz=timezone.utc)
        ts_str = ts.astimezone(timezone.utc).isoformat()

        cur = await conn.execute(
            """
            INSERT INTO measurements (node_id, timestamp, temperature, distance, lux)
            VALUES (?, ?, ?, ?, ?)
            """,
            (node_id, ts_str, m.temperature, m.distance, m.lux),
        )
        await conn.commit()
        return MeasurementOut(
            id=cur.lastrowid or 0,
            node_id=node_id,
            timestamp=ts,
            temperature=m.temperature,
            distance=m.distance,
            lux=m.lux,
        )

    async def latest_per_node(self) -> List[MeasurementOut]:
        """Zwraca najnowszy pomiar dla każdego węzła."""
        conn = self._require_conn()
        async with conn.execute(
            """
            SELECT m.*
              FROM measurements m
              JOIN (
                  SELECT node_id, MAX(timestamp) AS max_ts
                    FROM measurements
                   GROUP BY node_id
              ) t ON t.node_id = m.node_id AND t.max_ts = m.timestamp
             ORDER BY m.node_id
            """
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_measurement(r) for r in rows]

    async def history(
        self,
        node_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[MeasurementOut]:
        """Zwraca ostatnie `limit` pomiarów (opcjonalnie filtr po węźle).

        Wynik jest posortowany rosnąco po czasie - wygodne do wykresów.
        """
        conn = self._require_conn()
        if node_id:
            sql = (
                "SELECT * FROM measurements WHERE node_id = ? "
                "ORDER BY timestamp DESC LIMIT ?"
            )
            params: tuple = (node_id, limit)
        else:
            sql = "SELECT * FROM measurements ORDER BY timestamp DESC LIMIT ?"
            params = (limit,)

        async with conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
        items = [_row_to_measurement(r) for r in rows]
        items.reverse()
        return items

    async def distinct_nodes(self) -> List[str]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT DISTINCT node_id FROM measurements ORDER BY node_id"
        ) as cur:
            rows = await cur.fetchall()
        return [r["node_id"] for r in rows]
