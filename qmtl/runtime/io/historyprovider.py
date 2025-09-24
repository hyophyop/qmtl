from __future__ import annotations

"""QuestDB history backend and provider implementations."""

from typing import TYPE_CHECKING

import asyncpg
import pandas as pd

from qmtl.runtime.sdk.data_io import DataFetcher
from qmtl.runtime.sdk.history_provider_facade import AugmentedHistoryProvider

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from qmtl.runtime.sdk.auto_backfill import AutoBackfillStrategy


class QuestDBBackend:
    """QuestDB-backed implementation of :class:`HistoryBackend`."""

    def __init__(
        self,
        dsn: str,
        *,
        table: str | None = None,
    ) -> None:
        self.dsn = dsn
        self._table = table

    # ------------------------------------------------------------------
    def bind_stream(self, stream) -> None:
        self._stream_id = stream.node_id

    # ------------------------------------------------------------------
    @property
    def table(self) -> str:
        table = self._table or getattr(self, "_stream_id", None)
        if table is None:
            raise RuntimeError("table not specified and stream not bound")
        return table

    # ------------------------------------------------------------------
    async def read_range(
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

    # ------------------------------------------------------------------
    async def write_rows(
        self, rows: pd.DataFrame, *, node_id: str, interval: int
    ) -> None:
        if rows is None or rows.empty:
            return

        conn = await asyncpg.connect(dsn=self.dsn)
        try:
            payload_columns = [c for c in rows.columns if c != "ts"]
            for _, row in rows.iterrows():
                if "ts" not in row.index:
                    raise KeyError("row missing 'ts' column")
                ts = int(row["ts"])
                values = [self._normalize_value(row[c]) for c in payload_columns]
                columns_sql = ", ".join(payload_columns)
                placeholders = ", ".join(
                    f"${i}" for i in range(4, 4 + len(payload_columns))
                )
                sql = (
                    f"INSERT INTO {self.table}(node_id, interval, ts"
                    + (f", {columns_sql}" if columns_sql else "")
                    + ") VALUES($1, $2, $3"
                    + (f", {placeholders}" if placeholders else "")
                    + ")"
                )
                await conn.execute(sql, node_id, interval, ts, *values)
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        conn = await asyncpg.connect(dsn=self.dsn)
        try:
            sql = (
                f"SELECT ts FROM {self.table} "
                "WHERE node_id=$1 AND interval=$2 ORDER BY ts"
            )
            rows = await conn.fetch(sql, node_id, interval)
        finally:
            await conn.close()

        timestamps = [int(r["ts"]) for r in rows]
        if not timestamps:
            return []

        ranges: list[tuple[int, int]] = []
        start = prev = timestamps[0]
        for ts in timestamps[1:]:
            if ts == prev + interval:
                prev = ts
            else:
                ranges.append((start, prev))
                start = prev = ts
        ranges.append((start, prev))
        return ranges

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_value(value):
        if hasattr(value, "item"):
            return value.item()
        return value


class QuestDBHistoryProvider(AugmentedHistoryProvider):
    """QuestDB-backed history provider using :class:`AugmentedHistoryProvider`."""

    def __init__(
        self,
        dsn: str,
        *,
        table: str | None = None,
        fetcher: DataFetcher | None = None,
        auto_backfill: "AutoBackfillStrategy" | None = None,
    ) -> None:
        backend = QuestDBBackend(dsn, table=table)
        super().__init__(backend, fetcher=fetcher, auto_backfill=auto_backfill)
        self.dsn = dsn

    # ------------------------------------------------------------------
    @property
    def table(self) -> str:
        return self.backend.table  # type: ignore[return-value]


# Backwards compatibility -------------------------------------------------
QuestDBLoader = QuestDBHistoryProvider


__all__ = ["QuestDBBackend", "QuestDBHistoryProvider", "QuestDBLoader"]

