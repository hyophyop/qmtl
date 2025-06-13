from __future__ import annotations

"""Backfill data sources."""

from typing import Protocol
import asyncio

import pandas as pd
import asyncpg


class BackfillSource(Protocol):
    """Interface for fetching historical data for nodes."""

    def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        """Return data in [start, end) for the given node and interval."""
        ...


class QuestDBSource:
    """Backfill source backed by QuestDB."""

    def __init__(self, dsn: str, table: str = "node_data") -> None:
        self.dsn = dsn
        self.table = table

    def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        async def _query() -> list[asyncpg.Record]:
            conn = await asyncpg.connect(self.dsn)
            try:
                sql = (
                    f"SELECT * FROM {self.table} "
                    "WHERE node_id=$1 AND interval=$2 AND ts >= $3 AND ts < $4 "
                    "ORDER BY ts"
                )
                return await conn.fetch(sql, node_id, interval, start, end)
            finally:
                await conn.close()

        rows = asyncio.run(_query())
        return pd.DataFrame([dict(r) for r in rows])
