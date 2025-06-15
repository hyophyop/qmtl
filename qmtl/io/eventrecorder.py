from __future__ import annotations

"""QuestDB-backed :class:`~qmtl.sdk.data_io.EventRecorder` implementation."""

from typing import Any
import asyncpg

from qmtl.sdk.data_io import EventRecorder


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
