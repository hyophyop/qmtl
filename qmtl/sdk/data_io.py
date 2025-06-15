from __future__ import annotations

"""Utilities for loading and persisting node cache data."""

from typing import Protocol, Any
import pandas as pd
import asyncpg


class CacheLoader(Protocol):
    """Interface for loading historical data into node caches."""

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Return data in ``[start, end)`` for ``node_id`` and ``interval``."""
        ...


class EventRecorder(Protocol):
    """Interface for persisting processed node data."""

    async def persist(
        self, node_id: str, interval: int, timestamp: int, payload: Any
    ) -> None:
        """Store ``payload`` for ``(node_id, interval, timestamp)``."""
        ...


class QuestDBLoader:
    """CacheLoader implementation backed by QuestDB."""

    def __init__(self, dsn: str, table: str = "node_data") -> None:
        self.dsn = dsn
        self.table = table

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        conn = await asyncpg.connect(self.dsn)
        try:
            sql = (
                f"SELECT * FROM {self.table} "
                "WHERE node_id=$1 AND interval=$2 AND ts >= $3 AND ts < $4 "
                "ORDER BY ts"
            )
            rows = await conn.fetch(sql, node_id, interval, start, end)
        finally:
            await conn.close()

        return pd.DataFrame([dict(r) for r in rows])


class QuestDBRecorder:
    """EventRecorder implementation that writes records to QuestDB."""

    def __init__(self, dsn: str, table: str = "node_data") -> None:
        self.dsn = dsn
        self.table = table

    async def persist(
        self, node_id: str, interval: int, timestamp: int, payload: dict
    ) -> None:
        conn = await asyncpg.connect(self.dsn)
        try:
            columns = ", ".join(payload.keys())
            values = payload.values()
            placeholders = ", ".join(f"${i}" for i in range(4, 4 + len(payload)))
            sql = (
                f"INSERT INTO {self.table}(node_id, interval, ts"
                + (f", {columns}" if columns else "")
                + f") VALUES($1, $2, $3"
                + (f", {placeholders}" if placeholders else "")
                + ")"
            )
            await conn.execute(sql, node_id, interval, timestamp, *values)
        finally:
            await conn.close()
