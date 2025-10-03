from __future__ import annotations

import pandas as pd
import pytest

from qmtl.runtime.io import CcxtQuestDBProvider


class _InMemoryBackend:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, int], dict[int, dict]] = {}

    async def read_range(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        table = self._rows.get((node_id, interval), {})
        data = []
        for ts in sorted(table):
            if start <= ts < end:
                row = {"ts": ts}
                row.update(table[ts])
                data.append(row)
        return pd.DataFrame(data)

    async def write_rows(self, rows: pd.DataFrame, *, node_id: str, interval: int) -> None:
        if rows is None or rows.empty:
            return
        table = self._rows.setdefault((node_id, interval), {})
        for rec in rows.to_dict("records"):
            ts = int(rec["ts"])
            payload = {k: v for k, v in rec.items() if k != "ts"}
            table[ts] = payload

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        table = self._rows.get((node_id, interval), {})
        timestamps = sorted(table)
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


class _StubTradesExchange:
    async def fetch_trades(self, symbol, since=None, limit=None):
        # Return a single trade at 60s
        return [{"timestamp": 60_000, "price": 10.0, "amount": 0.1, "side": "buy"}]

    async def close(self):  # pragma: no cover
        pass


@pytest.mark.asyncio
async def test_ccxt_questdb_provider_from_config_trades(monkeypatch):
    cfg = {
        "mode": "trades",
        "exchange": "binance",
        "symbols": ["BTC/USDT"],
        "questdb": {"dsn": "postgresql://local:8812/qdb", "table": "node_data_trades"},
    }
    provider = CcxtQuestDBProvider.from_config(cfg, exchange=_StubTradesExchange())
    backend = _InMemoryBackend()
    provider.backend = backend  # type: ignore[attr-defined]

    node_id = "trades:binance:BTC/USDT"
    await provider.fill_missing(60, 60, node_id=node_id, interval=1)
    df = await backend.read_range(0, 120, node_id=node_id, interval=1)
    assert df["ts"].tolist() == [60]

