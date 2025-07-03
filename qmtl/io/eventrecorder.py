from __future__ import annotations

"""QuestDB-backed :class:`~qmtl.sdk.data_io.EventRecorder` implementation."""

from typing import Any
import asyncpg

from qmtl.sdk.data_io import EventRecorder


class QuestDBRecorder:
    """EventRecorder implementation that writes records to QuestDB."""

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
    ) -> None:
        self._dsn_provided = dsn is not None
        self.dsn = dsn or self._make_dsn(host, port, database, user, password)
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table = table

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

    async def persist(
        self, node_id: str, interval: int, timestamp: int, payload: dict
    ) -> None:
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
