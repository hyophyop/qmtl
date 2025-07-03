from __future__ import annotations

"""QuestDB-backed :class:`~qmtl.sdk.data_io.HistoryProvider` implementation."""

import pandas as pd
import asyncpg

from qmtl.sdk.data_io import HistoryProvider, DataFetcher


class QuestDBLoader:
    """HistoryProvider implementation backed by QuestDB."""

    def __init__(
        self,
        dsn: str | None = None,
        *,
        host: str = "localhost",
        port: int = 8812,
        database: str = "qdb",
        user: str | None = None,
        password: str | None = None,
        table: str = "node_data",
        fetcher: DataFetcher | None = None,
    ) -> None:
        self._dsn_provided = dsn is not None
        self.dsn = dsn or self._make_dsn(host, port, database, user, password)
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table = table
        self.fetcher = fetcher

    @staticmethod
    def _make_dsn(
        host: str, port: int, database: str, user: str | None, password: str | None
    ) -> str:
        auth = ""
        if user:
            auth = user
            if password:
                auth += f":{password}"
            auth += "@"
        return f"postgresql://{auth}{host}:{port}/{database}"

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        conn = await asyncpg.connect(
            **({"dsn": self.dsn} if self._dsn_provided else {
                "host": self.host,
                "port": self.port,
                "database": self.database,
                "user": self.user,
                "password": self.password,
            })
        )
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
        conn = await asyncpg.connect(
            **({"dsn": self.dsn} if self._dsn_provided else {
                "host": self.host,
                "port": self.port,
                "database": self.database,
                "user": self.user,
                "password": self.password,
            })
        )
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

        conn = await asyncpg.connect(
            **({"dsn": self.dsn} if self._dsn_provided else {
                "host": self.host,
                "port": self.port,
                "database": self.database,
                "user": self.user,
                "password": self.password,
            })
        )
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

