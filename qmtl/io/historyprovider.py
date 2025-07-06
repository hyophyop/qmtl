from __future__ import annotations

"""QuestDB-backed :class:`~qmtl.sdk.data_io.HistoryProvider` implementation."""

import pandas as pd
import asyncpg

from qmtl.sdk.data_io import HistoryProvider, DataFetcher


class QuestDBLoader(HistoryProvider):
    """HistoryProvider implementation backed by QuestDB."""

    def __init__(
        self,
        dsn: str,
        *,
        table: str | None = None,
        fetcher: DataFetcher | None = None,
    ) -> None:
        self.dsn = dsn
        self._table = table
        self.fetcher = fetcher

    @property
    def table(self) -> str:
        tbl = self._table or getattr(self, "_stream_id", None)
        if tbl is None:
            raise RuntimeError("table not specified and stream not bound")
        return tbl


    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        conn = await asyncpg.connect(dsn=self.dsn)
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

    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        """Return contiguous timestamp ranges available for ``node_id``."""
        conn = await asyncpg.connect(dsn=self.dsn)
        try:
            sql = (
                f"SELECT ts FROM {self.table} "
                "WHERE node_id=$1 AND interval=$2 ORDER BY ts"
            )
            rows = await conn.fetch(sql, node_id, interval)
        finally:
            await conn.close()

        ts_values = [int(r["ts"]) for r in rows]
        if not ts_values:
            return []
        ranges: list[tuple[int, int]] = []
        start = ts_values[0]
        prev = start
        for ts in ts_values[1:]:
            if ts == prev + interval:
                prev = ts
            else:
                ranges.append((start, prev))
                start = ts
                prev = ts
        ranges.append((start, prev))
        return ranges

    async def fill_missing(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        """Insert real rows for any missing timestamps."""

        if self.fetcher is None:
            raise RuntimeError("DataFetcher not configured")

        conn = await asyncpg.connect(dsn=self.dsn)
        try:
            sql_fetch = (
                f"SELECT ts FROM {self.table} "
                "WHERE node_id=$1 AND interval=$2 AND ts >= $3 AND ts <= $4"
            )
            rows = await conn.fetch(sql_fetch, node_id, interval, start, end)
            existing = {int(r["ts"]) for r in rows}

            df = await self.fetcher.fetch(
                start, end, node_id=node_id, interval=interval
            )

            for _, row in df.iterrows():
                ts = int(row.get("ts", 0))
                if ts in existing:
                    continue
                payload = {k: row[k] for k in row.index if k != "ts"}
                columns = ", ".join(payload.keys())
                values = payload.values()
                placeholders = ", ".join(
                    f"${i}" for i in range(4, 4 + len(payload))
                )
                sql_ins = (
                    f"INSERT INTO {self.table}(node_id, interval, ts"
                    + (f", {columns}" if columns else "")
                    + f") VALUES($1, $2, $3"
                    + (f", {placeholders}" if placeholders else "")
                    + ")"
                )
                await conn.execute(
                    sql_ins, node_id, interval, ts, *values
                )
        finally:
            await conn.close()

