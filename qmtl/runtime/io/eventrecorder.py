from __future__ import annotations

"""QuestDB-backed :class:`~qmtl.runtime.sdk.data_io.EventRecorder` implementation."""

from typing import Any
import asyncpg

from qmtl.runtime.sdk.data_io import EventRecorder


class QuestDBRecorder(EventRecorder):
    """EventRecorder implementation that writes records to QuestDB."""

    def __init__(
        self,
        dsn: str,
        *,
        table: str | None = None,
    ) -> None:
        self.dsn = dsn
        self._table = table

    @property
    def table(self) -> str:
        tbl = self._table or getattr(self, "_stream_id", None)
        if tbl is None:
            raise RuntimeError("table not specified and stream not bound")
        return tbl


    async def persist(
        self, node_id: str, interval: int, timestamp: int, payload: Any
    ) -> None:
        conn = await asyncpg.connect(dsn=self.dsn)
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
